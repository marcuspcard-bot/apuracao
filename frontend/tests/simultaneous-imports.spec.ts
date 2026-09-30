import { test, expect, type Page, type Browser } from '@playwright/test'
import path from 'node:path'

const api = 'http://127.0.0.1:8001'

async function prepare(page: Page, section: string) {
  await page.goto('/importar')
  await page
    .getByLabel('Arquivo PDF')
    .setInputFiles(path.resolve(`../.artifacts/simultaneo-${section}.pdf`))
  await expect(
    page.getByText('Dados validados.', { exact: true }),
  ).toBeVisible()
}

async function operators(browser: Browser, baseURL: string | undefined) {
  const contexts = await Promise.all(
    Array.from({ length: 5 }, () => browser.newContext({ baseURL })),
  )
  return {
    pages: await Promise.all(contexts.map((context) => context.newPage())),
    close: () => Promise.all(contexts.map((context) => context.close())),
  }
}

test('cinco navegadores independentes importam cinco PDFs sem misturar seções ou votos', async ({
  browser,
  baseURL,
  request,
}) => {
  test.setTimeout(90000)
  const before = await (await request.get(`${api}/api/acompanhamento`)).json()
  const users = await operators(browser, baseURL)
  try {
    await Promise.all(
      users.pages.map((page, i) => prepare(page, `030${i + 1}`)),
    )
    const previewsOnly = await (
      await request.get(`${api}/api/acompanhamento`)
    ).json()
    expect(previewsOnly.boletins).toBe(before.boletins)
    const results = await Promise.all(
      users.pages.map(async (page) => {
        const response = page.waitForResponse((r) =>
          r.url().endsWith('/api/boletins/confirmar'),
        )
        await page
          .getByRole('button', { name: 'Salvar boletim', exact: true })
          .click()
        const saved = await response
        expect(saved.status()).toBe(201)
        await expect(
          page.getByText('Boletim salvo com sucesso.', { exact: false }),
        ).toBeVisible()
        return saved.json() as Promise<{ id: string }>
      }),
    )
    expect(new Set(results.map((r) => r.id)).size).toBe(5)
    for (const [i, result] of results.entries()) {
      const detail = await (
        await request.get(`${api}/api/boletins/${result.id}`)
      ).json()
      expect(detail.dados.secao).toBe(`030${i + 1}`)
      expect(detail.dados.zona).toBe('0013')
      expect(
        detail.cargos.find((c: { nome: string }) => c.nome === 'PRESIDENTE')
          .candidatos[0].votos,
      ).toBe(30)
      await expect(
        users.pages[i].getByRole('link', { name: 'Ver boletim', exact: true }),
      ).toHaveAttribute('href', `/boletins/${result.id}`)
    }
    const after = await (await request.get(`${api}/api/acompanhamento`)).json()
    expect(after.boletins - before.boletins).toBe(5)
    expect(after.secoes_apuradas - before.secoes_apuradas).toBe(7)
    const votes = (data: typeof after) =>
      data.cargos
        .find((c: { nome: string }) => c.nome === 'PRESIDENTE')
        ?.candidatos.find((c: { numero: string }) => c.numero === '13')
        ?.votos ?? 0
    expect(votes(after) - votes(before)).toBe(150)
  } finally {
    await users.close()
  }
})

test('cinco computadores com o mesmo PDF salvam uma vez e os demais recebem duplicidade', async ({
  browser,
  baseURL,
  request,
}) => {
  test.setTimeout(90000)
  const before = await (await request.get(`${api}/api/acompanhamento`)).json()
  const users = await operators(browser, baseURL)
  try {
    await Promise.all(users.pages.map((page) => prepare(page, '0310')))
    const statuses = await Promise.all(
      users.pages.map(async (page) => {
        const response = page.waitForResponse((r) =>
          r.url().endsWith('/api/boletins/confirmar'),
        )
        await page
          .getByRole('button', { name: 'Salvar boletim', exact: true })
          .click()
        const status = (await response).status()
        if (status === 201) {
          await expect(
            page.getByText('Boletim salvo com sucesso.', { exact: false }),
          ).toBeVisible()
        } else {
          await expect(page.getByRole('alert')).toContainText(
            'Este arquivo já foi importado anteriormente.',
          )
          await expect(
            page.getByRole('button', { name: 'Verificar salvamento' }),
          ).toHaveCount(0)
        }
        return status
      }),
    )
    expect(statuses.sort()).toEqual([201, 409, 409, 409, 409])
    const after = await (await request.get(`${api}/api/acompanhamento`)).json()
    expect(after.boletins - before.boletins).toBe(1)
  } finally {
    await users.close()
  }
})

test('resposta perdida após commit recupera o recibo sem repetir a gravação', async ({
  page,
  request,
}) => {
  const before = await (await request.get(`${api}/api/acompanhamento`)).json()
  let posts = 0
  await page.route('**/api/boletins/confirmar', async (route) => {
    posts += 1
    const saved = await route.fetch()
    expect(saved.status()).toBe(201)
    await route.abort('failed')
  })
  await prepare(page, '0320')
  await page
    .getByRole('button', { name: 'Salvar boletim', exact: true })
    .click()
  await expect(
    page.getByText('Boletim salvo com sucesso.', { exact: false }),
  ).toBeVisible()
  expect(posts).toBe(1)
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByRole('link', { name: 'Ver boletim', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Seção 0320', exact: true }),
  ).toBeVisible()
  const after = await (await request.get(`${api}/api/acompanhamento`)).json()
  expect(after.boletins - before.boletins).toBe(1)
})

test('conexão indisponível preserva prévia e só verifica, sem reenviar automaticamente', async ({
  page,
}, testInfo) => {
  let disconnected = true
  let lookupFailed = true
  let posts = 0
  let lookups = 0
  await page.route('**/api/boletins/confirmar', (route) => {
    posts += 1
    return disconnected ? route.abort('failed') : route.continue()
  })
  await page.route('**/api/boletins/por-hash/*', (route) => {
    lookups += 1
    return lookupFailed
      ? route.fulfill({ status: 503, json: { detail: 'Indisponível' } })
      : route.continue()
  })
  await prepare(page, '0321')
  await page
    .getByRole('button', { name: 'Salvar boletim', exact: true })
    .click()
  await expect(page.getByRole('alert')).toContainText(
    'O boletim pode ter sido salvo.',
  )
  expect(posts).toBe(1)
  expect(lookups).toBe(1)
  await expect(
    page.getByText('Dados validados.', { exact: true }),
  ).toBeVisible()
  lookupFailed = false
  await page.getByRole('button', { name: 'Verificar salvamento' }).click()
  await expect(page.getByRole('alert')).toContainText(
    'O boletim pode ter sido salvo.',
  )
  expect(posts).toBe(1)
  expect(lookups).toBe(2)
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true)
    await page.screenshot({
      path: testInfo.outputPath(`confirmacao-incerta-${width}.png`),
      fullPage: true,
    })
  }
  disconnected = false
  await page
    .getByRole('button', { name: 'Salvar boletim', exact: true })
    .click()
  await expect(
    page.getByText('Boletim salvo com sucesso.', { exact: false }),
  ).toBeVisible()
  expect(posts).toBe(2)
})
