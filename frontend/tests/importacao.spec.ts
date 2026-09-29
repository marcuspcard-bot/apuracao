import { test, expect } from './fixtures'
import path from 'node:path'

const pdf = path.resolve('../Xangai_(ZZ)_-_0001_-_0483.pdf')

test('abertura do PDF permite repetir a busca da URL após falha', async ({
  page,
}) => {
  let attempts = 0
  await page.route(
    '**/api/boletins/00000000-0000-0000-0000-000000000000/pdf',
    async (route) => {
      attempts++
      await route.fulfill(
        attempts === 1
          ? {
              status: 502,
              json: {
                detail:
                  'Não foi possível abrir o PDF original. Tente novamente.',
              },
            }
          : {
              status: 200,
              json: {
                url: 'http://localhost:5174/pdf-original-teste',
                expires_in: 60,
              },
            },
      )
    },
  )
  await page.route('**/pdf-original-teste', (route) =>
    route.fulfill({ path: pdf, contentType: 'application/pdf' }),
  )
  await page.goto('/boletins/00000000-0000-0000-0000-000000000000/pdf')
  await expect(page.getByRole('alert')).toContainText(
    'Não foi possível abrir o PDF original.',
  )
  const response = page.waitForResponse('**/pdf-original-teste')
  await page.getByRole('button', { name: 'Tentar novamente' }).click()
  expect((await response).status()).toBe(200)
  expect(attempts).toBe(2)
})

test('PDF real: prévia, confirmação, listagem, detalhes e duplicidade em desktop e celular', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/')
  await expect(
    page.getByRole('heading', { name: 'Importar Boletim de Urna' }),
  ).toBeVisible()
  await expect(page.locator('.reference img')).toBeVisible()
  expect(
    await page
      .locator('.reference img')
      .evaluate((img: HTMLImageElement) => img.naturalWidth),
  ).toBeGreaterThan(0)
  await page.screenshot({
    path: '../.artifacts/importar-desktop.png',
    fullPage: true,
  })
  await page.locator('input[type=file]').setInputFiles(pdf)
  await expect(
    page.getByText('Dados validados.', { exact: true }),
  ).toBeVisible()
  await expect(page.getByText('JAIR BOLSONARO', { exact: true })).toBeVisible()
  await expect(page.getByText('JOÃO AMOÊDO', { exact: true })).toBeVisible()
  await expect(page.getByText('01586544', { exact: true })).toBeVisible()
  await expect(
    page
      .locator('.data-grid > div')
      .filter({
        has: page.getByText('Total de seções representadas', { exact: true }),
      })
      .locator('dd'),
  ).toHaveText('5')
  await page.screenshot({
    path: '../.artifacts/preview-desktop.png',
    fullPage: true,
  })
  await page
    .getByRole('button', { name: 'Salvar boletim', exact: true })
    .click()
  await expect(
    page.getByText('Boletim salvo com sucesso.', { exact: false }),
  ).toBeVisible()
  await page.getByRole('link', { name: 'Ver boletim', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Seção 0483', exact: true }),
  ).toBeVisible()
  const detailUrl = page.url()
  const popupPromise = page.waitForEvent('popup')
  const originalPromise = page
    .context()
    .waitForEvent('response', (response) =>
      response.url().includes('/test-pdf/'),
    )
  const pdfLink = page.getByRole('link', { name: 'Ver PDF original' })
  await expect(pdfLink).toHaveAttribute('rel', 'noopener noreferrer')
  await pdfLink.click()
  const popup = await popupPromise
  const original = await originalPromise
  expect(original.status()).toBe(200)
  expect(original.headers()['content-type']).toContain('application/pdf')
  await expect(page).toHaveURL(detailUrl)
  await popup.close()
  await page
    .getByRole('link', { name: 'Boletins importados', exact: true })
    .click()
  await expect(
    page.getByRole('cell', { name: '0483', exact: true }),
  ).toBeVisible()
  await page.screenshot({
    path: '../.artifacts/boletins-desktop.png',
    fullPage: true,
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(detailUrl)
  await expect(page.getByText('JAIR BOLSONARO')).toBeVisible()
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
  await page.screenshot({
    path: '../.artifacts/detalhes-mobile.png',
    fullPage: true,
  })
  await page.goto('/importar')
  await page.screenshot({
    path: '../.artifacts/importar-mobile.png',
    fullPage: true,
  })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
  await page.locator('input[type=file]').setInputFiles(pdf)
  await expect(page.getByRole('alert')).toContainText(
    'Este arquivo já foi importado anteriormente.',
  )
})

test('arquivo inválido e inconsistência impedem a confirmação', async ({
  page,
}) => {
  await page.goto('/importar')
  await page.locator('input[type=file]').setInputFiles({
    name: 'arquivo.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('invalid'),
  })
  await expect(page.getByRole('alert')).toContainText(
    'Selecione um arquivo PDF válido.',
  )
  await page.locator('input[type=file]').setInputFiles({
    name: 'invalido.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('bad'),
  })
  await expect(page.getByRole('alert')).toContainText('PDF inválido.')
  await expect(
    page.getByRole('button', { name: 'Salvar boletim', exact: true }),
  ).toHaveCount(0)
  await page
    .locator('input[type=file]')
    .setInputFiles(path.resolve('../.artifacts/inconsistente.pdf'))
  await expect(page.getByRole('alert')).toContainText(
    'Este boletim possui inconsistências e não poderá ser salvo.',
  )
  await expect(
    page.getByRole('button', { name: 'Salvar boletim', exact: true }),
  ).toBeDisabled()
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click()
  await expect(
    page.getByRole('button', { name: 'Selecionar PDF', exact: true }),
  ).toBeVisible()
})

test('múltiplos cargos e legenda: preview e detalhes preservam cada resultado', async ({
  page,
}) => {
  await page.goto('/importar')
  await page
    .locator('input[type=file]')
    .setInputFiles(path.resolve('../.artifacts/multicargos.pdf'))
  await expect(
    page.getByText('Dados validados.', { exact: true }),
  ).toBeVisible()
  const offices = [
    'DEPUTADO FEDERAL',
    'DEPUTADO ESTADUAL',
    'DEPUTADO DISTRITAL',
    'SENADOR',
    'GOVERNADOR',
    'PRESIDENTE',
  ]
  async function checkOffices() {
    await expect(page.locator('.results-section')).toHaveCount(6)
    for (const office of offices)
      await expect(
        page.getByRole('heading', { name: office, exact: true }),
      ).toBeVisible()
    const federal = page.getByRole('region', {
      name: 'DEPUTADO FEDERAL',
      exact: true,
    })
    await expect(
      federal.getByRole('cell', { name: '0123', exact: true }),
    ).toBeVisible()
    await expect(
      federal.getByText('ANA CLÁUDIA', { exact: true }),
    ).toBeVisible()
    await expect(federal.getByText('KÁTIA RIBEIRO')).toHaveCount(0)
    await expect(
      federal
        .locator('.totals > div')
        .filter({ has: page.getByText('Votos de legenda', { exact: true }) })
        .locator('dd'),
    ).toHaveText('2')
    const state = page.getByRole('region', {
      name: 'DEPUTADO ESTADUAL',
      exact: true,
    })
    await expect(
      state.getByText('ÉRICA DOS SANTOS', { exact: true }),
    ).toBeVisible()
    await expect(state.locator('tbody tr')).toHaveCount(3)
    const senate = page.getByRole('region', { name: 'SENADOR', exact: true })
    await expect(senate.locator('.total-highlight dd')).toHaveText('77')
  }
  await checkOffices()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({
    path: '../.artifacts/multicargos-mobile.png',
    fullPage: true,
  })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
  await page
    .getByRole('button', { name: 'Salvar boletim', exact: true })
    .click()
  await page.getByRole('link', { name: 'Ver boletim', exact: true }).click()
  await checkOffices()
  await page.reload()
  await expect(page.locator('.results-section')).toHaveCount(6)
})

test('total ausente mostra inconsistência e não inventa zero', async ({
  page,
}) => {
  await page.goto('/importar')
  await page
    .locator('input[type=file]')
    .setInputFiles(path.resolve('../.artifacts/total-ausente.pdf'))
  await expect(page.getByRole('alert')).toContainText(
    'total apurado do cargo SENADOR',
  )
  const senate = page.getByRole('region', { name: 'SENADOR', exact: true })
  await expect(senate.locator('.total-highlight dd')).toHaveText(
    'Não identificado',
  )
  await expect(
    page.getByRole('button', { name: 'Salvar boletim', exact: true }),
  ).toBeDisabled()
})

test('vagas de senador permanecem separadas após salvar', async ({ page }) => {
  await page.goto('/importar')
  await page
    .locator('input[type=file]')
    .setInputFiles(path.resolve('../.artifacts/vagas-senador.pdf'))
  await expect(
    page.getByText('Dados validados.', { exact: true }),
  ).toBeVisible()
  await expect(page.locator('.results-section')).toHaveCount(1)
  await expect(
    page.getByRole('heading', { name: '1ª VAGA', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: '2ª VAGA', exact: true }),
  ).toBeVisible()
  await page
    .getByRole('button', { name: 'Salvar boletim', exact: true })
    .click()
  await page.getByRole('link', { name: 'Ver boletim', exact: true }).click()
  await expect(page.locator('.seat-result')).toHaveCount(2)
  await expect(
    page
      .getByRole('region', { name: 'SENADOR / 1ª VAGA', exact: true })
      .locator('.total-highlight dd'),
  ).toHaveText('77')
  await expect(
    page
      .getByRole('region', { name: 'SENADOR / 2ª VAGA', exact: true })
      .locator('.total-highlight dd'),
  ).toHaveText('77')
})

test('seção sem quantidade nem lista de agregadas pode ser conferida e salva', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/importar')
  await page
    .locator('input[type=file]')
    .setInputFiles(path.resolve('../.artifacts/sem-agregadas.pdf'))
  await expect(
    page.getByText('Dados validados.', { exact: true }),
  ).toBeVisible()
  async function checkSection() {
    await expect(page.locator('.aggregated')).toContainText(
      'Seções agregadas (0)',
    )
    await expect(page.locator('.aggregated')).toContainText('Nenhuma')
    await expect(
      page
        .locator('.data-grid > div')
        .filter({ has: page.getByText('Seção', { exact: true }) })
        .locator('dd'),
    ).toHaveText('0123')
    await expect(
      page
        .locator('.data-grid > div')
        .filter({
          has: page.getByText('Total de seções representadas', { exact: true }),
        })
        .locator('dd'),
    ).toHaveText('1')
  }
  await checkSection()
  await page.screenshot({
    path: '../.artifacts/sem-agregadas-mobile.png',
    fullPage: true,
  })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
  await page
    .getByRole('button', { name: 'Salvar boletim', exact: true })
    .click()
  await page.getByRole('link', { name: 'Ver boletim', exact: true }).click()
  await checkSection()
})

test('quantidade divergente de agregadas bloqueia salvar', async ({ page }) => {
  await page.goto('/importar')
  await page
    .locator('input[type=file]')
    .setInputFiles(path.resolve('../.artifacts/agregadas-inconsistentes.pdf'))
  await expect(page.getByRole('alert')).toContainText(
    'Quantidade de seções agregadas informada no boletim não corresponde à quantidade identificada.',
  )
  await expect(
    page.getByRole('button', { name: 'Salvar boletim', exact: true }),
  ).toBeDisabled()
})
