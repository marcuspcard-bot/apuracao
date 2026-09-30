import { test, expect, type Page } from '@playwright/test'
import path from 'node:path'
import type { Disclosure, ScreenConfig } from '../src/types/telao'

function disclosure(count = 5): Disclosure {
  const offices = [
    'DEPUTADO ESTADUAL',
    'DEPUTADO FEDERAL',
    'SENADOR',
    'SENADOR',
    'GOVERNADOR',
  ]
  return {
    municipio: 'BACABAL',
    uf: 'MA',
    zona: '0013',
    eleicao_data: '2026-10-04',
    eleicao_turno: 1,
    boletins_recebidos: 87,
    secoes_representadas: 103,
    total_secoes_esperadas: 334,
    ultima_atualizacao: '2026-10-04T21:43:12Z',
    ultima_importacao: '2026-10-04T21:43:10Z',
    cards_por_pagina: 6,
    tempo_rotacao_segundos: 10,
    ativo: true,
    versao: 1,
    candidatos: Array.from({ length: count }, (_, i) => ({
      id: `candidate-${i + 1}`,
      ordem: i + 1,
      cargo: offices[i % offices.length],
      numero: String(12345 + i),
      nome: `CANDIDATO DE TESTE ${i + 1}`,
      votos: i === 0 ? 0 : 12458 + i,
    })),
  }
}

async function mockEvents(page: Page) {
  await page.addInitScript(() => {
    const streams: EventTarget[] = []
    Object.assign(window, {
      screenStreams: streams,
      dispatchScreenEvent: () =>
        streams.forEach((s) =>
          s.dispatchEvent(
            new MessageEvent('update', { data: '{"revision":1}' }),
          ),
        ),
      EventSource: class extends EventTarget {
        constructor() {
          super()
          streams.push(this)
        }
        close() {
          streams.splice(streams.indexOf(this), 1)
        }
      },
    })
  })
}

async function changed(page: Page) {
  await page.evaluate(() =>
    (
      window as unknown as { dispatchScreenEvent: () => void }
    ).dispatchScreenEvent(),
  )
}

async function expectFitted(page: Page) {
  await expect
    .poll(() =>
      page.evaluate(() => {
        const footer = document
          .querySelector('.disclosure-footer')!
          .getBoundingClientRect()
        const issues: string[] = []
        if (document.documentElement.scrollWidth > innerWidth)
          issues.push('horizontal overflow')
        if (footer.bottom > innerHeight + 1)
          issues.push('footer outside viewport')
        document.querySelectorAll<HTMLElement>('.screen-fit').forEach((el) => {
          if (
            el.scrollWidth > el.clientWidth + 1 ||
            el.scrollHeight > el.clientHeight + 1
          )
            issues.push(`text overflow: ${el.textContent}`)
        })
        document.querySelectorAll('.disclosure-candidate').forEach((el) => {
          if (el.getBoundingClientRect().bottom > footer.top + 1)
            issues.push('card overlaps footer')
        })
        return issues
      }),
    )
    .toEqual([])
}

test('configuração sem login, ordem manual, SSE real e votos após confirmação do PDF', async ({
  page,
  context,
  request,
}) => {
  test.setTimeout(60000)
  await page.goto('/importar')
  await page
    .locator('input[type=file]')
    .setInputFiles(path.resolve('../.artifacts/bacabal-telao-0009.pdf'))
  await expect(
    page.getByText('Dados validados.', { exact: true }),
  ).toBeVisible()
  await page
    .getByRole('button', { name: 'Salvar boletim', exact: true })
    .click()
  await expect(
    page.getByText('Boletim salvo com sucesso.', { exact: false }),
  ).toBeVisible()

  await page.goto('/configuracao-telao')
  await expect(
    page.getByRole('heading', { name: 'Configuração do telão' }),
  ).toBeVisible()
  await expect(page.locator('input[type=password]')).toHaveCount(0)
  for (const [cargo, numero] of [
    ['GOVERNADOR', '13'],
    ['PRESIDENTE', '13'],
    ['PRESIDENTE', '22'],
    ['DEPUTADO FEDERAL', '0123'],
  ]) {
    await page.getByLabel('Cargo', { exact: true }).selectOption(cargo)
    await page.getByLabel('Pesquisar candidato').fill(numero)
    await page
      .getByRole('button', { name: new RegExp(`^Adicionar ${numero} -`) })
      .click()
  }
  await expect(page.locator('.screen-selection-list > li')).toHaveCount(4)
  await page.getByRole('button', { name: 'Mover 0123 para cima' }).click()
  await expect(
    page.locator('.screen-selection-list > li').nth(2),
  ).toContainText('DEPUTADO FEDERAL')
  await page.getByRole('button', { name: 'Remover 0123 do telão' }).click()
  const save = page.getByRole('button', {
    name: 'Salvar configuração do telão',
  })
  await save.click()
  await expect(
    page.getByText('Configuração do telão salva com sucesso.'),
  ).toBeVisible()
  await page.reload()
  await expect(page.locator('.screen-selection-list > li')).toHaveCount(3)
  const initialResponse = await request.get(
    'http://127.0.0.1:8001/api/divulgacao',
  )
  const initial: Disclosure = await initialResponse.json()
  expect(initial.candidatos.map((c) => [c.cargo, c.numero])).toEqual([
    ['GOVERNADOR', '13'],
    ['PRESIDENTE', '13'],
    ['PRESIDENTE', '22'],
  ])
  const votes = initial.candidatos[1].votos
  const popupPromise = page.waitForEvent('popup')
  await page.getByRole('link', { name: 'Visualizar telão' }).click()
  const screen = await popupPromise
  await screen.clock.install()
  try {
    await expect(screen.locator('.disclosure-candidate')).toHaveCount(3)
    await expect(
      screen.locator('.vote-value .screen-text-value').nth(2),
    ).toHaveText('0')
    await expect(screen.locator('nav, input, .app-header')).toHaveCount(0)
    await expect(screen.locator('body')).not.toContainText('%')
    // Saving configuration emits a real SSE event, before the 10-second polling interval.
    await page.getByLabel('Exibir 22 - CANDIDATO SEM VOTOS').uncheck()
    await save.click()
    await expect(
      page.getByText('Configuração do telão salva com sucesso.'),
    ).toBeVisible()
    await screen.clock.runFor(1500)
    await expect(screen.locator('.disclosure-candidate')).toHaveCount(2)
    const invalid = await request.put(
      'http://127.0.0.1:8001/api/telao/config',
      { data: {} },
    )
    expect(invalid.status()).toBe(422)

    const importer = await context.newPage()
    try {
      await importer.goto('/importar')
      await importer
        .locator('input[type=file]')
        .setInputFiles(path.resolve('../.artifacts/bacabal-telao-0010.pdf'))
      await expect(
        importer.getByText('Dados validados.', { exact: true }),
      ).toBeVisible()
      await screen.clock.runFor(11000)
      await expect(
        screen.locator('.vote-value .screen-text-value').nth(1),
      ).toHaveText(votes.toLocaleString('pt-BR'))
      await importer
        .getByRole('button', { name: 'Salvar boletim', exact: true })
        .click()
      await expect(
        importer.getByText('Boletim salvo com sucesso.', { exact: false }),
      ).toBeVisible()
      await screen.clock.runFor(11000)
      await expect(
        screen.locator('.vote-value .screen-text-value').nth(1),
      ).toHaveText((votes + 30).toLocaleString('pt-BR'))
      await expect(screen.locator('.screen-candidate-office')).toHaveText([
        'GOVERNADOR',
        'PRESIDENTE',
      ])
    } finally {
      await importer.close()
    }
  } finally {
    await screen.close()
  }
})

test('eventos com debounce, polling sem Realtime e falhas preservam os últimos votos', async ({
  page,
}) => {
  await page.clock.install()
  await mockEvents(page)
  const data = disclosure(2)
  let calls = 0
  let fail = false
  await page.route('**/api/divulgacao', (route) => {
    calls += 1
    return route.fulfill(
      fail ? { status: 503, json: { detail: 'Indisponível' } } : { json: data },
    )
  })
  await page.goto('/divulgacao')
  await expect(
    page.locator('.vote-value .screen-text-value').first(),
  ).toHaveText('0')
  const initialCalls = calls
  data.candidatos[0].votos = 1200
  data.candidatos[1].votos = 99999
  for (let i = 0; i < 5; i++) {
    await changed(page)
    await page.clock.runFor(100)
  }
  await page.clock.runFor(500)
  expect(calls).toBe(initialCalls)
  await page.clock.runFor(300)
  await expect(
    page.locator('.vote-value .screen-text-value').first(),
  ).toHaveText('1.200')
  expect(calls).toBe(initialCalls + 1)
  await expect(page.locator('.screen-candidate-number')).toHaveText([
    '12345',
    '12346',
  ])
  fail = true
  await page.clock.runFor(11000)
  await expect(
    page.getByText(
      'Não foi possível atualizar os dados. Tentando novamente...',
    ),
  ).toBeVisible()
  await expect(
    page.locator('.vote-value .screen-text-value').first(),
  ).toHaveText('1.200')
  fail = false
  data.candidatos[0].votos = 1300
  await page.clock.runFor(11000)
  await expect(
    page.locator('.vote-value .screen-text-value').first(),
  ).toHaveText('1.300')
  await expect(
    page.getByText(
      'Não foi possível atualizar os dados. Tentando novamente...',
    ),
  ).toHaveCount(0)
  await expect(page.locator('.disclosure-candidate')).toHaveCount(2)
  await page.goto('/importar')
  expect(
    await page.evaluate(
      () =>
        (window as unknown as { screenStreams: unknown[] }).screenStreams
          .length,
    ),
  ).toBe(0)
})

test('rotação automática mantém ordem, volta ao início e tela cheia funciona', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1920, height: 1080 })
  await page.clock.install()
  await mockEvents(page)
  await page.route('**/api/divulgacao', (route) =>
    route.fulfill({ json: disclosure(12) }),
  )
  await page.goto('/divulgacao')
  await expect(page.locator('.disclosure-candidate')).toHaveCount(6)
  await expect(page.locator('.screen-page')).toHaveText('Página 1 / 2')
  await page.clock.runFor(10000)
  await expect(page.locator('.screen-page')).toHaveText('Página 2 / 2')
  await expect(page.locator('.screen-candidate-number').first()).toHaveText(
    '12351',
  )
  await page.clock.runFor(10000)
  await expect(page.locator('.screen-page')).toHaveText('Página 1 / 2')
  await page.getByRole('button', { name: 'Tela cheia', exact: true }).click()
  await expect
    .poll(() => page.evaluate(() => Boolean(document.fullscreenElement)))
    .toBe(true)
  await expectFitted(page)
  await page.getByRole('button', { name: 'Sair da tela cheia' }).click()
  await expect
    .poll(() => page.evaluate(() => Boolean(document.fullscreenElement)))
    .toBe(false)
})

test('estados de erro inicial, sem candidatos, sem boletins e divulgação pausada', async ({
  page,
}) => {
  await page.clock.install()
  await mockEvents(page)
  let fail = true
  const data = disclosure(0)
  data.boletins_recebidos = data.secoes_representadas = 0
  data.total_secoes_esperadas = null
  await page.route('**/api/divulgacao', (route) =>
    route.fulfill(fail ? { status: 503, json: {} } : { json: data }),
  )
  await page.goto('/divulgacao')
  await expect(
    page.getByText(
      'Não foi possível atualizar os dados. Tentando novamente...',
    ),
  ).toBeVisible()
  fail = false
  await page.clock.runFor(11000)
  await expect(
    page.getByText('Nenhum candidato configurado para o telão.'),
  ).toBeVisible()
  await expect(
    page.getByText('Aguardando recebimento dos boletins.'),
  ).toBeVisible()
  await expect(
    page.getByText('SEÇÕES REPRESENTADAS', { exact: true }),
  ).toBeVisible()
  data.candidatos = disclosure(1).candidatos
  await changed(page)
  await page.clock.runFor(1000)
  await expect(page.locator('.vote-value .screen-text-value')).toHaveText('0')
  data.ativo = false
  await changed(page)
  await page.clock.runFor(1000)
  await expect(page.getByText('Divulgação pausada.')).toBeVisible()
  await expect(page.locator('.disclosure-candidate')).toHaveCount(0)
})

test('telão cabe em TV, 4K, notebook, tablet e celular com nomes e votos extensos', async ({
  page,
}, testInfo) => {
  await mockEvents(page)
  let data = disclosure(5)
  data.candidatos[0].nome = 'MARIA DA CONCEIÇÃO ALBUQUERQUE DOS SANTOS E SILVA'
  data.candidatos[1].votos = 1234567890
  await page.route('**/api/divulgacao', (route) =>
    route.fulfill({ json: data }),
  )
  for (const [width, height] of [
    [1920, 1080],
    [1366, 768],
    [3840, 2160],
    [768, 1024],
    [390, 844],
    [320, 700],
  ]) {
    await page.setViewportSize({ width, height })
    await page.goto('/divulgacao')
    await expect(page.locator('.disclosure-candidate').first()).toBeVisible()
    await expectFitted(page)
    for (const row of await page
      .locator('.vote-value')
      .evaluateAll((elements) =>
        elements.map((el) => {
          const value = el.querySelector('.screen-text-value')!
          const label = el.querySelector('.screen-text-suffix')!
          return {
            valueSize: parseFloat(getComputedStyle(value).fontSize),
            labelSize: parseFloat(getComputedStyle(label).fontSize),
            separated:
              label.getBoundingClientRect().left >
              value.getBoundingClientRect().right,
            label: label.textContent,
          }
        }),
      )) {
      expect(row.label).toBe('VOTOS')
      expect(row.labelSize).toBeCloseTo(row.valueSize * 0.4, 1)
      expect(row.separated).toBe(true)
    }
    if (width >= 1100) {
      expect(
        await page
          .locator('.vote-value')
          .first()
          .evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
      ).toBeGreaterThanOrEqual(48)
    }
    await expect(page.locator('body')).not.toContainText('%')
    await expect(
      page.getByText('Consulte a Justiça Eleitoral para o resultado oficial.'),
    ).toBeVisible()
    await page.screenshot({
      path: testInfo.outputPath(`telao-${width}.png`),
      fullPage: true,
    })
  }
  await page.setViewportSize({ width: 3840, height: 2160 })
  for (const count of [1, 2, 3, 6, 12]) {
    data = disclosure(count)
    data.cards_por_pagina = 12
    await page.goto('/divulgacao')
    await expect(page.locator('.disclosure-candidate')).toHaveCount(count)
    await expectFitted(page)
  }
})

test('telão reajusta o texto quando uma fonte termina de carregar sem redimensionar a caixa', async ({
  page,
}) => {
  await mockEvents(page)
  const data = disclosure(4)
  data.tempo_rotacao_segundos = 300
  data.candidatos[0].nome = 'MARIA DA CONCEIÇÃO ALBUQUERQUE DOS SANTOS E SILVA'
  data.candidatos[1].votos = 1234567890
  await page.route('**/api/divulgacao', (route) =>
    route.fulfill({ json: data }),
  )
  await page.setViewportSize({ width: 768, height: 1024 })
  await page.goto('/divulgacao')
  await expect(page.locator('.disclosure-candidate')).toHaveCount(4)
  await page.evaluate(() => document.fonts.ready)
  await expectFitted(page)
  const sizes = await page
    .locator('.screen-fit')
    .evaluateAll((elements) =>
      elements.map((el) => [el.clientWidth, el.clientHeight]),
    )
  await page.evaluate(() => {
    document.querySelectorAll<HTMLElement>('.screen-fit').forEach((el) => {
      el.style.fontFamily = 'monospace'
    })
    document.fonts.dispatchEvent(new Event('loadingdone'))
  })
  await expectFitted(page)
  expect(
    await page
      .locator('.screen-fit')
      .evaluateAll((elements) =>
        elements.map((el) => [el.clientWidth, el.clientHeight]),
      ),
  ).toEqual(sizes)
})

test('configuração responsiva preserva as alterações quando outro operador salva primeiro', async ({
  page,
}, testInfo) => {
  const publicData = disclosure(3)
  const config: ScreenConfig = {
    ...publicData,
    municipio_codigo: '07234',
    updated_at: null,
    cargos: ['DEPUTADO ESTADUAL', 'DEPUTADO FEDERAL', 'SENADOR'],
    candidatos: publicData.candidatos.map((c) => ({
      ...c,
      candidato_id: c.id,
      ativo: true,
    })),
  }
  await page.route('**/api/telao/config', (route) =>
    route.fulfill(
      route.request().method() === 'PUT'
        ? {
            status: 409,
            json: {
              detail:
                'A configuração foi alterada por outra pessoa. Recarregue antes de salvar.',
            },
          }
        : { json: config },
    ),
  )
  await page.route('**/api/telao/candidatos-disponiveis?*', (route) =>
    route.fulfill({ json: { candidatos: [], tem_mais: false } }),
  )
  await page.goto('/configuracao-telao')
  await page.getByLabel('Cards por página').fill('2')
  await page
    .getByRole('button', { name: 'Salvar configuração do telão' })
    .click()
  await expect(page.getByRole('alert')).toContainText(
    'alterada por outra pessoa',
  )
  await expect(page.getByLabel('Cards por página')).toHaveValue('2')
  await expect(page.locator('.screen-selection-list > li')).toHaveCount(3)
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true)
    await page.screenshot({
      path: testInfo.outputPath(`config-${width}.png`),
      fullPage: true,
    })
  }
})
