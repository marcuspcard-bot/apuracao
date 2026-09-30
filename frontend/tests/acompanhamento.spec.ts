import { test, expect } from '@playwright/test'
import path from 'node:path'

function overview(votes = 30) {
  return {
    eleicao: { ano: 2026, turno: 1, data: '2026-10-04' },
    eleicao_configurada: { ano: 2026, turno: 1, data: '2026-10-04' },
    datas_disponiveis: [{ data: '2026-10-04', boletins: 2 }],
    consultado_em: '2026-10-04T21:00:00Z',
    ultima_importacao: '2026-10-04T20:00:00Z',
    boletins: 2,
    secoes_apuradas: 3,
    secoes_esperadas: null,
    secoes_pendentes: null,
    secoes_principais_apuradas: 2,
    secoes_principais_esperadas: null,
    secoes_principais_pendentes: null,
    cargos: [
      {
        nome: 'PRESIDENTE',
        boletins: 2,
        candidatos: [
          {
            numero: '01',
            nome: 'CANDIDATO TESTE',
            nomes: ['CANDIDATO TESTE'],
            votos: votes,
            vagas: [],
          },
        ],
      },
      {
        nome: 'GOVERNADOR',
        boletins: 1,
        candidatos: [
          {
            numero: '01',
            nome: 'OUTRO CANDIDATO',
            nomes: ['OUTRO CANDIDATO'],
            votos: 7,
            vagas: [],
          },
        ],
      },
    ],
    secoes: [
      {
        zona: '0013',
        secao: '0001',
        tipo: 'PRINCIPAL',
        secao_principal: '0001',
        boletim_id: 'one',
      },
      {
        zona: '0013',
        secao: '0002',
        tipo: 'AGREGADA',
        secao_principal: '0001',
        boletim_id: 'one',
      },
      {
        zona: '0066',
        secao: '0003',
        tipo: 'PRINCIPAL',
        secao_principal: '0003',
        boletim_id: 'two',
      },
    ],
  }
}

test('visão geral vazia consulta API real sem misturar outros municípios', async ({
  page,
}) => {
  await page.goto('/acompanhamento')
  await expect(
    page.getByRole('heading', { name: 'Bacabal / MA' }),
  ).toBeVisible()
  await expect(
    page.getByText('Ainda não há resultados de Bacabal para esta eleição.'),
  ).toBeVisible()
  await expect(
    page.getByText('Não informado. Lista de seções ainda não importada.'),
  ).toBeVisible()
})

test('candidato, filtros, atualização automática e recuperação de erro', async ({
  page,
}) => {
  await page.clock.install()
  let votes = 30
  let fail = false
  await page.route('**/api/acompanhamento', (route) =>
    route.fulfill(
      fail
        ? {
            status: 503,
            json: { detail: 'Falha no banco de dados. Tente novamente.' },
          }
        : { json: overview(votes) },
    ),
  )
  await page.goto('/acompanhamento')
  await page.getByLabel('Cargo', { exact: true }).selectOption('PRESIDENTE')
  await page.getByLabel('Candidato', { exact: true }).selectOption('01')
  await expect(page.locator('.candidate-votes strong')).toHaveText('30')
  await expect(
    page.getByRole('region', { name: 'Seções apuradas', exact: true }),
  ).toHaveCount(0)
  await expect(page.getByLabel('Seção dos votos')).toHaveValue('')
  votes = 45
  await page.clock.runFor(11000)
  await expect(page.locator('.candidate-votes strong')).toHaveText('45')
  fail = true
  await page.clock.runFor(11000)
  await expect(page.getByRole('alert')).toContainText(
    'última consulta bem-sucedida',
  )
  await expect(page.locator('.candidate-votes strong')).toHaveText('45')
  fail = false
  await page.getByRole('button', { name: 'Atualizar acompanhamento' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByLabel('Cargo', { exact: true }).selectOption('GOVERNADOR')
  await expect(page.getByLabel('Candidato', { exact: true })).toHaveValue('')
  await page.getByLabel('Candidato', { exact: true }).selectOption('01')
  await expect(page.locator('.candidate-votes strong')).toHaveText('7')
})

test('visão geral em desktop e celular sem overflow', async ({
  page,
}, testInfo) => {
  const data = overview()
  data.datas_disponiveis.push({ data: '2026-10-02', boletins: 1 })
  await page.route('**/api/acompanhamento', (route) =>
    route.fulfill({ json: data }),
  )
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/acompanhamento')
    await expect(
      page.getByRole('link', { name: 'Ver boletins de 02/10/2026' }),
    ).toBeVisible()
    await page.getByLabel('Cargo', { exact: true }).selectOption('PRESIDENTE')
    await page.getByLabel('Candidato', { exact: true }).selectOption('01')
    await expect(page.locator('.candidate-votes strong')).toHaveText('30')
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true)
    await page.screenshot({
      path: testInfo.outputPath(`overview-${width}.png`),
      fullPage: true,
    })
  }
})

test('trocar a data limpa os votos anteriores mesmo se a nova consulta falhar', async ({
  page,
}) => {
  let fail = true
  const dates = [
    { data: '2026-10-04', boletins: 2 },
    { data: '2026-10-02', boletins: 1 },
  ]
  await page.route(/\/api\/acompanhamento(\?.*)?$/, (route) => {
    const alternate =
      new URL(route.request().url()).searchParams.get('data') === '2026-10-02'
    if (alternate && fail)
      return route.fulfill({
        status: 503,
        json: { detail: 'Falha na consulta da data selecionada.' },
      })
    const data = overview(alternate ? 9 : 30)
    data.datas_disponiveis = dates
    if (alternate) {
      data.eleicao.data = '2026-10-02'
      data.boletins = 1
      data.secoes_principais_apuradas = 1
      data.cargos.forEach((office) => {
        office.boletins = 1
      })
    }
    return route.fulfill({ json: data })
  })
  await page.goto('/acompanhamento')
  await page.getByLabel('Cargo', { exact: true }).selectOption('PRESIDENTE')
  await page.getByLabel('Candidato', { exact: true }).selectOption('01')
  await expect(page.locator('.candidate-votes strong')).toHaveText('30')
  await page.getByLabel('Data da eleição').selectOption('2026-10-02')
  await expect(page.getByRole('alert')).toContainText(
    'Falha na consulta da data selecionada.',
  )
  await expect(page.locator('.candidate-votes')).toHaveCount(0)
  await expect(page.locator('.overview-metrics')).toHaveCount(0)
  fail = false
  await page.getByRole('button', { name: 'Atualizar acompanhamento' }).click()
  await expect(page.getByLabel('Data da eleição')).toHaveValue('2026-10-02')
  await expect(page.getByLabel('Cargo', { exact: true })).toHaveValue('')
  await page.getByLabel('Cargo', { exact: true }).selectOption('PRESIDENTE')
  await page.getByLabel('Candidato', { exact: true }).selectOption('01')
  await expect(page.locator('.candidate-votes strong')).toHaveText('9')
  await page.getByRole('link', { name: 'Voltar a 04/10/2026' }).click()
  await expect(page.getByLabel('Data da eleição')).toHaveValue('2026-10-04')
  await expect(page.getByLabel('Cargo', { exact: true })).toHaveValue('')
  await expect(page.locator('.candidate-votes')).toHaveCount(0)
})

test('atualização aguarda a resposta anterior antes de agendar outra consulta', async ({
  page,
}) => {
  await page.clock.install()
  let calls = 0
  let pending: Promise<void> | null = null
  let release = () => {}
  await page.route('**/api/acompanhamento', async (route) => {
    calls += 1
    if (pending) await pending
    await route.fulfill({ json: overview() })
  })
  await page.goto('/acompanhamento')
  await expect(page.getByText('Conectado', { exact: true })).toBeVisible()
  const initialCalls = calls
  pending = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.clock.runFor(11000)
  await expect.poll(() => calls).toBe(initialCalls + 1)
  await page.clock.runFor(7000)
  expect(calls).toBe(initialCalls + 1)
  await expect(
    page.getByRole('button', { name: 'Atualizar acompanhamento' }),
  ).toBeDisabled()
  release()
  await expect(page.getByText('Conectado', { exact: true })).toBeVisible()
  await page.clock.runFor(9000)
  expect(calls).toBe(initialCalls + 1)
  await page.clock.runFor(1500)
  await expect.poll(() => calls).toBe(initialCalls + 2)
})

test('todas as seções são acessíveis no filtro de votos sem a tabela antiga', async ({
  page,
}) => {
  const data = overview()
  data.secoes = Array.from({ length: 43 }, (_, i) => ({
    zona: i < 40 ? '0013' : '0066',
    secao: String(i + 1).padStart(4, '0'),
    tipo: 'PRINCIPAL',
    secao_principal: String(i + 1).padStart(4, '0'),
    boletim_id: `test-${i}`,
  }))
  data.boletins = data.secoes_apuradas = data.secoes.length
  data.secoes_principais_apuradas = data.secoes.length
  await page.route('**/api/acompanhamento', (route) =>
    route.fulfill({ json: data }),
  )
  await page.goto('/acompanhamento')
  await expect(
    page.getByRole('region', { name: 'Seções apuradas', exact: true }),
  ).toHaveCount(0)
  const sections = page.getByLabel('Seção dos votos')
  await expect(sections.locator('option')).toHaveCount(44)
  await sections.selectOption('66:43')
  await expect(sections).toHaveValue('66:43')
  await expect(sections.locator('option:checked')).toHaveText(
    'Seção 0043 · Zona 0066',
  )
})

test('votos alternam entre todas, principal, agregada e isolada, com atualização automática', async ({
  page,
}) => {
  await page.clock.install()
  let groupVotes = 10
  await page.route('**/api/acompanhamento', (route) =>
    route.fulfill({ json: overview(groupVotes + 20) }),
  )
  await page.route('**/api/acompanhamento/votos-secao?*', (route) => {
    const params = new URL(route.request().url()).searchParams
    expect(params.get('data')).toBe('2026-10-04')
    const data = overview()
    const selected = data.secoes.find(
      (s) => s.zona === params.get('zona') && s.secao === params.get('secao'),
    )!
    const votos = selected.boletim_id === 'one' ? groupVotes : 20
    return route.fulfill({
      json: {
        boletins: 1,
        secoes: data.secoes.filter((s) => s.boletim_id === selected.boletim_id),
        cargos: [
          {
            ...data.cargos[0],
            boletins: 1,
            candidatos: [{ ...data.cargos[0].candidatos[0], votos }],
          },
        ],
      },
    })
  })
  await page.goto('/acompanhamento')
  await page.getByLabel('Cargo', { exact: true }).selectOption('PRESIDENTE')
  await page.getByLabel('Candidato', { exact: true }).selectOption('01')
  await expect(page.locator('.candidate-votes strong')).toHaveText('30')
  await page.getByLabel('Seção dos votos').selectOption('13:1')
  await expect(page.locator('.candidate-votes strong')).toHaveText('10')
  await expect(page.locator('.candidate-group')).toHaveText(
    'BU da seção 0001 (agregadas: 0002). Votos conjuntos.',
  )
  await expect(
    page.getByRole('link', { name: 'Ver boletim', exact: true }),
  ).toHaveAttribute('href', '/boletins/one')
  await page.getByLabel('Seção dos votos').selectOption('13:2')
  await expect(page.locator('.candidate-votes strong')).toHaveText('10')
  await expect(page.locator('.candidate-votes')).toContainText('votos no grupo')
  groupVotes = 15
  await page.clock.runFor(11000)
  await expect(page.locator('.candidate-votes strong')).toHaveText('15')
  await page.getByLabel('Seção dos votos').selectOption('66:3')
  await expect(page.locator('.candidate-votes strong')).toHaveText('20')
  await expect(page.locator('.candidate-votes')).toContainText('votos na seção')
  await expect(page.locator('.candidate-group')).toHaveCount(0)
  await expect(
    page.locator('.overview-metrics > div').first().locator('dd'),
  ).toHaveText('2')
  await page.getByLabel('Seção dos votos').selectOption('')
  await expect(page.locator('.candidate-votes strong')).toHaveText('35')
  await expect(page.locator('.candidate-scope')).toHaveText('Todas as seções')
})

test('filtro distingue zero votos de candidato, cargo e boletim ausentes', async ({
  page,
}) => {
  const data = overview()
  data.secoes.push(
    ...['0004', '0005'].map((secao) => ({
      zona: '0013',
      secao,
      secao_principal: secao,
      tipo: 'PRINCIPAL',
      boletim_id: secao,
    })),
  )
  await page.route('**/api/acompanhamento', (route) =>
    route.fulfill({
      json: {
        ...data,
        lista_secoes_importada: true,
        grupos_secoes: [
          {
            zona: '0013',
            secao_principal: '0006',
            status: 'PENDENTE',
            agregadas: [],
            principal: {
              numero: '0006',
              apurada: false,
              boletim_id: null,
              secao_principal_bu: null,
              vinculo_divergente: false,
            },
          },
        ],
      },
    }),
  )
  await page.route('**/api/acompanhamento/votos-secao?*', (route) => {
    const secao = new URL(route.request().url()).searchParams.get('secao')
    const candidate = { ...data.cargos[0].candidatos[0], votos: 0 }
    const office = { ...data.cargos[0], candidatos: [candidate] }
    if (secao === '0004') office.candidatos = []
    if (secao === '0005') office.nome = 'GOVERNADOR'
    return route.fulfill({
      json:
        secao === '0006'
          ? { boletins: 0, secoes: [], cargos: [] }
          : {
              boletins: 1,
              secoes: data.secoes.filter((s) => s.secao === secao),
              cargos: [office],
            },
    })
  })
  await page.goto('/acompanhamento')
  await page.getByLabel('Cargo', { exact: true }).selectOption('PRESIDENTE')
  await page.getByLabel('Candidato', { exact: true }).selectOption('01')
  await page.getByLabel('Seção dos votos').selectOption('13:1')
  await expect(page.locator('.candidate-votes strong')).toHaveText('0')
  await page.getByLabel('Seção dos votos').selectOption('13:4')
  await expect(
    page.getByText('Este candidato não consta no boletim desta seção.'),
  ).toBeVisible()
  await expect(page.locator('.candidate-votes')).toHaveCount(0)
  await page.getByLabel('Seção dos votos').selectOption('13:5')
  await expect(
    page.getByText('Este cargo não consta no boletim desta seção.'),
  ).toBeVisible()
  await expect(page.locator('.candidate-votes')).toHaveCount(0)
  await page.getByLabel('Seção dos votos').selectOption('13:6')
  await expect(page.getByText('Aguardando boletim desta seção.')).toBeVisible()
  await expect(page.locator('.candidate-votes')).toHaveCount(0)
  await page.getByLabel('Seção dos votos').selectOption('')
  await expect(page.locator('.candidate-votes strong')).toHaveText('30')
})

test('troca de seção cancela resposta antiga e falhas não reutilizam votos de outro filtro', async ({
  page,
}) => {
  await page.clock.install()
  let fail = false
  let calls = 0
  let finished = false
  let release = () => {}
  const pending = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/acompanhamento', (route) =>
    route.fulfill({ json: overview() }),
  )
  await page.route('**/api/acompanhamento/votos-secao?*', async (route) => {
    calls += 1
    const first = calls === 1
    if (first) await pending
    if (fail)
      return route.fulfill({
        status: 503,
        json: { detail: 'Falha na consulta de votos.' },
      })
    const secao = new URL(route.request().url()).searchParams.get('secao')
    const data = overview()
    await route.fulfill({
      json: {
        boletins: 1,
        secoes: data.secoes.filter((s) => s.secao === secao),
        cargos: [
          {
            ...data.cargos[0],
            candidatos: [
              {
                ...data.cargos[0].candidatos[0],
                votos: secao === '0001' ? 10 : 20,
              },
            ],
          },
        ],
      },
    })
    if (first) finished = true
  })
  await page.goto('/acompanhamento')
  await page.getByLabel('Cargo', { exact: true }).selectOption('PRESIDENTE')
  await page.getByLabel('Candidato', { exact: true }).selectOption('01')
  await page.getByLabel('Seção dos votos').selectOption('13:1')
  await expect(page.getByText('Consultando votos da seção...')).toBeVisible()
  await expect(page.locator('.candidate-votes')).toHaveCount(0)
  await page.clock.runFor(11000)
  expect(calls).toBe(1)
  await page.getByLabel('Seção dos votos').selectOption('66:3')
  await expect(page.locator('.candidate-votes strong')).toHaveText('20')
  release()
  await expect.poll(() => finished).toBe(true)
  await expect(page.locator('.candidate-votes strong')).toHaveText('20')
  fail = true
  await page.getByRole('button', { name: 'Atualizar acompanhamento' }).click()
  await expect(page.getByRole('alert')).toContainText(
    'última consulta bem-sucedida desta seção',
  )
  await expect(page.locator('.candidate-votes strong')).toHaveText('20')
  await page.getByLabel('Seção dos votos').selectOption('13:1')
  await expect(page.getByRole('alert')).toContainText(
    'Falha na consulta de votos.',
  )
  await expect(page.locator('.candidate-votes')).toHaveCount(0)
  fail = false
  await page.getByRole('button', { name: 'Atualizar acompanhamento' }).click()
  await expect(page.locator('.candidate-votes strong')).toHaveText('10')
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('dois PDFs confirmados atualizam o painel aberto sem contar prévias ou duplicidades', async ({
  page,
  context,
}) => {
  await page.clock.install()
  await page.goto('/acompanhamento')
  const metric = (name: string) =>
    page
      .locator('.overview-metrics > div')
      .filter({ has: page.getByText(name, { exact: true }) })
      .locator('dd')
  await expect(metric('Boletins salvos')).toHaveText('0')
  const registry = page.getByRole('region', {
    name: 'Seções pendentes',
    exact: true,
  })
  await registry.getByLabel('Lista de seções em CSV').setInputFiles({
    name: 'secoes.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(
      'zona;secao_principal;secoes_agregadas\n0013;0001;0002 0003\n0013;0004;\n',
    ),
  })
  await expect(
    registry.getByText('Conferir lista', { exact: true }),
  ).toBeVisible()
  await expect(metric('Seções principais pendentes')).toHaveText(
    'Não informado',
  )
  await registry
    .getByRole('button', { name: 'Salvar lista', exact: true })
    .click()
  await expect(metric('Seções principais esperadas')).toHaveText('2')
  await expect(metric('Seções principais pendentes')).toHaveText('2')
  await expect(
    registry.getByRole('img', { name: 'Pendente - seção 0001', exact: true }),
  ).toBeVisible()
  await expect(
    registry.getByRole('img', { name: 'Pendente - seção 0004', exact: true }),
  ).toBeVisible()
  const importer = await context.newPage()
  try {
    for (const [index, section] of ['0001', '0004'].entries()) {
      await importer.goto('/importar')
      await importer
        .locator('input[type=file]')
        .setInputFiles(
          path.resolve(`../.artifacts/bacabal-sintetico-${section}.pdf`),
        )
      await expect(
        importer.getByText('Dados validados.', { exact: true }),
      ).toBeVisible()
      await page.clock.runFor(11000)
      await expect(metric('Boletins salvos')).toHaveText(String(index))
      await expect(
        registry.getByRole('img', {
          name: `Pendente - seção ${section}`,
          exact: true,
        }),
      ).toBeVisible()
      await importer
        .getByRole('button', { name: 'Salvar boletim', exact: true })
        .click()
      await expect(
        importer.getByText('Boletim salvo com sucesso.', { exact: false }),
      ).toBeVisible()
      await page.clock.runFor(11000)
      await expect(metric('Boletins salvos')).toHaveText(String(index + 1))
      await expect(
        registry.getByRole('img', {
          name: `Apurada - seção ${section}`,
          exact: true,
        }),
      ).toBeVisible()
      await expect(metric('Seções principais pendentes')).toHaveText(
        index === 0 ? '1' : '0',
      )
      await expect(
        registry.getByRole('img', {
          name: 'Apurada - seção 0002',
          exact: true,
        }),
      ).toBeVisible()
      await expect(
        registry.getByRole('img', {
          name: 'Apurada - seção 0003',
          exact: true,
        }),
      ).toBeVisible()
      await expect(metric('Seções principais apuradas')).toHaveText(
        String(index + 1),
      )
      if (index === 0) {
        await page
          .getByLabel('Cargo', { exact: true })
          .selectOption('PRESIDENTE')
        await page.getByLabel('Candidato', { exact: true }).selectOption('13')
      }
      await expect(page.locator('.candidate-votes strong')).toHaveText(
        String(30 * (index + 1)),
      )
    }
    await page.getByLabel('Seção dos votos').selectOption('13:2')
    await expect(page.locator('.candidate-votes strong')).toHaveText('30')
    await expect(
      page.getByText(
        'BU da seção 0001 (agregadas: 0002, 0003). Votos conjuntos.',
      ),
    ).toBeVisible()
    await expect(page.locator('.candidate-votes')).toContainText(
      'votos no grupo',
    )
    await page.getByLabel('Seção dos votos').selectOption('13:4')
    await expect(page.locator('.candidate-votes strong')).toHaveText('30')
    await expect(page.locator('.candidate-votes')).toContainText(
      'votos na seção',
    )
    await page.getByLabel('Seção dos votos').selectOption('')
    await expect(page.locator('.candidate-votes strong')).toHaveText('60')
    await expect(metric('Seções principais pendentes')).toHaveText('0')
    await importer.goto('/importar')
    await importer
      .locator('input[type=file]')
      .setInputFiles(path.resolve('../.artifacts/bacabal-sintetico-0001.pdf'))
    await expect(importer.getByRole('alert')).toContainText(
      'Este arquivo já foi importado anteriormente.',
    )
    await page.clock.runFor(11000)
    await expect(metric('Boletins salvos')).toHaveText('2')
    await expect(page.locator('.candidate-votes strong')).toHaveText('60')
  } finally {
    await importer.close()
  }
})

test('BU de outra data aparece no aviso e pode ser consultado sem misturar eleições', async ({
  page,
  context,
}, testInfo) => {
  await page.clock.install()
  await page.goto('/acompanhamento')
  const metric = (name: string) =>
    page
      .locator('.overview-metrics > div')
      .filter({ has: page.getByText(name, { exact: true }) })
      .locator('dd')
  await expect(page.getByText('Conectado', { exact: true })).toBeVisible()
  const initialCount = await metric('Boletins salvos').innerText()
  const importer = await context.newPage()
  try {
    await importer.goto('/importar')
    await importer
      .locator('input[type=file]')
      .setInputFiles(path.resolve('../.artifacts/bacabal-outra-data.pdf'))
    await expect(
      importer.getByText('Dados validados.', { exact: true }),
    ).toBeVisible()
    await page.clock.runFor(11000)
    await expect(
      page.getByRole('link', { name: 'Ver boletins de 02/10/2026' }),
    ).toHaveCount(0)
    await importer
      .getByRole('button', { name: 'Salvar boletim', exact: true })
      .click()
    await expect(
      importer.getByText('Boletim salvo com sucesso.', { exact: false }),
    ).toBeVisible()
    await page.clock.runFor(11000)
    await expect(
      page.getByText('1 boletim salvo em outra data', { exact: true }),
    ).toBeVisible()
    await expect(metric('Boletins salvos')).toHaveText(initialCount)
    await page.getByRole('link', { name: 'Ver boletins de 02/10/2026' }).click()
    await expect(page).toHaveURL(/\/acompanhamento\?data=2026-10-02$/)
    await expect(page.getByLabel('Data da eleição')).toHaveValue('2026-10-02')
    await expect(metric('Boletins salvos')).toHaveText('1')
    await expect(metric('Seções principais apuradas')).toHaveText('1')
    await expect(metric('Seções principais pendentes')).toHaveText(
      'Não informado',
    )
    await expect(page.getByLabel('Lista de seções em CSV')).toHaveCount(0)
    await expect(
      page.getByText('Sem cadastro de seções para esta data.'),
    ).toBeVisible()
    await page.getByLabel('Cargo', { exact: true }).selectOption('PRESIDENTE')
    await page.getByLabel('Candidato', { exact: true }).selectOption('13')
    await expect(page.locator('.candidate-votes strong')).toHaveText('30')
    await page.getByLabel('Seção dos votos').selectOption('13:165')
    await expect(page.locator('.candidate-votes strong')).toHaveText('30')
    await expect(page.locator('.candidate-group')).toContainText(
      'BU da seção 0002 (agregadas: 0165, 0167, 0168, 0169)',
    )
    await page.getByLabel('Cargo', { exact: true }).selectOption('GOVERNADOR')
    await expect(page.getByLabel('Candidato', { exact: true })).toHaveValue('')
    await page.getByLabel('Candidato', { exact: true }).selectOption('13')
    await expect(page.locator('.candidate-votes strong')).toHaveText('7')
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 900 })
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true)
      await page.screenshot({
        path: testInfo.outputPath(`other-date-${width}.png`),
        fullPage: true,
      })
    }
    await page.getByLabel('Data da eleição').selectOption('2026-10-04')
    await expect(metric('Boletins salvos')).toHaveText(initialCount)
    await expect(page.getByLabel('Cargo', { exact: true })).toHaveValue('')
    await expect(page.getByLabel('Lista de seções em CSV')).toHaveCount(1)
    await page.goBack()
    await expect(page.getByLabel('Data da eleição')).toHaveValue('2026-10-02')
    await page.reload()
    await expect(page.getByLabel('Data da eleição')).toHaveValue('2026-10-02')
    await expect(metric('Boletins salvos')).toHaveText('1')
  } finally {
    await importer.close()
  }
})

test('círculos, agregadas, filtros e lista responsiva', async ({
  page,
}, testInfo) => {
  const member = (numero: string, apurada: boolean) => ({
    numero,
    apurada,
    boletim_id: apurada ? 'test-bulletin' : null,
    secao_principal_bu: apurada ? '0001' : null,
    vinculo_divergente: false,
  })
  const data = {
    ...overview(),
    lista_secoes_importada: true,
    secoes_esperadas: 30,
    secoes_pendentes: 2,
    secoes_principais_esperadas: 3,
    secoes_principais_apuradas: 2,
    secoes_principais_pendentes: 1,
    grupos_secoes: [
      {
        zona: '0013',
        secao_principal: '0001',
        principal: member('0001', true),
        agregadas: [member('0002', false), member('0003', true)],
        status: 'PARCIAL',
      },
      {
        zona: '0013',
        secao_principal: '0004',
        principal: member('0004', false),
        agregadas: [],
        status: 'PENDENTE',
      },
      {
        zona: '0066',
        secao_principal: '0005',
        principal: member('0005', true),
        agregadas: Array.from({ length: 25 }, (_, i) =>
          member(String(i + 6).padStart(4, '0'), true),
        ),
        status: 'APURADA',
      },
    ],
  }
  await page.route('**/api/acompanhamento', (route) =>
    route.fulfill({ json: data }),
  )
  await page.goto('/acompanhamento')
  const registry = page.getByRole('region', {
    name: 'Seções pendentes',
    exact: true,
  })
  await expect(
    registry.getByRole('img', { name: 'Pendente - seção 0002', exact: true }),
  ).toHaveCSS('background-color', 'rgb(196, 61, 61)')
  await expect(
    registry.getByRole('img', { name: 'Apurada - seção 0001', exact: true }),
  ).toHaveCSS('background-color', 'rgb(35, 133, 83)')
  await expect(registry.getByText('Parcial', { exact: true })).toBeVisible()
  await registry.getByRole('button', { name: 'Pendentes', exact: true }).click()
  await expect(registry.locator('.section-status-row')).toHaveCount(2)
  await registry.getByRole('button', { name: 'Apuradas', exact: true }).click()
  await expect(registry.locator('.section-status-row')).toHaveCount(1)
  await registry.getByRole('button', { name: 'Todas', exact: true }).click()
  await registry.getByLabel('Buscar seção na lista').fill('0002')
  await expect(registry.locator('.section-status-row')).toHaveCount(1)
  await expect(registry.locator('.section-status-row')).toContainText('0001')
  await registry.getByLabel('Buscar seção na lista').fill('')
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true)
    await registry.screenshot({
      path: testInfo.outputPath(`registry-${width}.png`),
    })
  }
})

test('resumo conta 253 principais sem acrescentar 81 agregadas', async ({
  page,
}, testInfo) => {
  await page.clock.install()
  let aggregateNumber = 254
  const member = (number: number) => ({
    numero: String(number).padStart(4, '0'),
    apurada: false,
    boletim_id: null as string | null,
    secao_principal_bu: null as string | null,
    vinculo_divergente: false,
  })
  const groups = Array.from({ length: 253 }, (_, index) => ({
    zona: '0013',
    secao_principal: String(index + 1).padStart(4, '0'),
    principal: member(index + 1),
    agregadas: Array.from({ length: index < 17 ? 2 : index < 64 ? 1 : 0 }, () =>
      member(aggregateNumber++),
    ),
    status: 'PENDENTE',
  }))
  const data = {
    ...overview(),
    boletins: 0,
    cargos: [],
    secoes: [] as ReturnType<typeof overview>['secoes'],
    secoes_apuradas: 0,
    secoes_esperadas: 334,
    secoes_pendentes: 334,
    secoes_principais_esperadas: 253,
    secoes_principais_apuradas: 0,
    secoes_principais_pendentes: 253,
    lista_secoes_importada: true,
    grupos_secoes: groups,
  }
  await page.route('**/api/acompanhamento', (route) =>
    route.fulfill({ json: data }),
  )
  await page.goto('/acompanhamento')
  const metric = (name: string) =>
    page
      .locator('.overview-metrics > div')
      .filter({ has: page.getByText(name, { exact: true }) })
      .locator('dd')
  await expect(metric('Seções principais esperadas')).toHaveText('253')
  await expect(metric('Seções principais pendentes')).toHaveText('253')
  await expect(metric('Seções principais apuradas')).toHaveText('0')
  const registry = page.getByRole('region', {
    name: 'Seções pendentes',
    exact: true,
  })
  await expect(registry.getByText('253 grupos', { exact: true })).toBeVisible()
  await expect(
    registry.getByRole('img', { name: 'Pendente - seção 0254', exact: true }),
  ).toBeVisible()
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true)
    await page.screenshot({
      path: testInfo.outputPath(`principals-${width}.png`),
      fullPage: true,
    })
  }
  const first = groups[0]
  first.status = 'APURADA'
  for (const section of [first.principal, ...first.agregadas]) {
    section.apurada = true
    section.boletim_id = 'first'
    section.secao_principal_bu = first.secao_principal
  }
  data.boletins = data.secoes_principais_apuradas = 1
  data.secoes_principais_pendentes = 252
  data.secoes_apuradas = 3
  data.secoes_pendentes = 331
  data.secoes = [first.principal, ...first.agregadas].map((section) => ({
    zona: first.zona,
    secao: section.numero,
    secao_principal: first.secao_principal,
    tipo: section.numero === first.secao_principal ? 'PRINCIPAL' : 'AGREGADA',
    boletim_id: 'first',
  }))
  await page.clock.runFor(11000)
  await expect(metric('Seções principais apuradas')).toHaveText('1')
  await expect(metric('Seções principais pendentes')).toHaveText('252')
  await expect(metric('Seções principais esperadas')).toHaveText('253')
  await expect(
    page.getByRole('region', { name: 'Seções apuradas', exact: true }),
  ).toHaveCount(0)
  await expect(
    registry.getByRole('img', { name: 'Apurada - seção 0254', exact: true }),
  ).toBeVisible()
})
