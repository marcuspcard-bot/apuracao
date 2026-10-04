import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const server = 'http://127.0.0.1:8001'

test('digitação parcial com foto e substituição por PDF sem duplicar votos', async ({
  page,
  request,
}) => {
  const pdfPath = path.resolve('../.artifacts/simultaneo-0321.pdf')
  const previewResponse = await request.post(`${server}/api/boletins/preview`, {
    multipart: {
      file: {
        name: 'bu.pdf',
        mimeType: 'application/pdf',
        buffer: await readFile(pdfPath),
      },
    },
  })
  expect(previewResponse.ok()).toBeTruthy()
  const { dados } = await previewResponse.json()
  const office = dados.cargos[0]
  const candidate = office.candidatos[0]
  await page.goto('/importar')
  await page
    .getByRole('link', {
      name: 'Digitar candidatos específicos e anexar fotos do BU',
    })
    .click()
  await page
    .getByLabel('Eleição', { exact: true })
    .fill(dados.eleicao.descricao)
  await page
    .getByLabel('Data da eleição', { exact: true })
    .fill(dados.eleicao.data)
  await page.getByLabel('Município', { exact: true }).fill(dados.municipio.nome)
  await page.getByLabel('Código TSE do município').fill(dados.municipio.codigo)
  await page.getByLabel('Zona', { exact: true }).fill(dados.zona)
  await page.getByLabel('Seção principal', { exact: true }).fill(dados.secao)
  await page.getByLabel('Cargo do candidato 1').selectOption(office.nome)
  await page.getByLabel('Número do candidato 1').fill(candidate.numero)
  await page.getByLabel('Nome do candidato 1').fill(candidate.nome)
  await page
    .getByLabel('Votos do candidato 1')
    .fill(String(candidate.votos + 5))
  await page
    .getByLabel('Fotos do BU')
    .setInputFiles(path.resolve('../.artifacts/foto-candidato.png'))
  await page.getByRole('button', { name: 'Tentar ler texto das fotos' }).click()
  await expect(
    page.getByLabel('Texto reconhecido — confira com a foto'),
  ).toBeVisible({ timeout: 20000 })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy()
  await page
    .getByRole('button', { name: 'Conferir lançamento', exact: true })
    .click()
  await expect(
    page.getByRole('heading', {
      name: 'Confira com o boletim antes de salvar',
    }),
  ).toBeVisible()
  await page
    .getByRole('button', { name: 'Confirmar lançamento parcial' })
    .click()
  await expect(
    page.getByRole('link', { name: 'Substituir por PDF' }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Abrir PDF das fotos do BU' }),
  ).toBeVisible()
  const manualId = page.url().split('/').pop()!
  await page.getByRole('link', { name: 'Substituir por PDF' }).click()
  await page.locator('input[type=file]').setInputFiles(pdfPath)
  await expect(
    page.getByRole('heading', { name: 'Conferir votos antes da substituição' }),
  ).toBeVisible()
  await page
    .getByRole('button', { name: 'Confirmar substituição pelo PDF' })
    .click()
  await page.getByRole('link', { name: 'Ver boletim', exact: true }).click()
  await expect(
    page.getByRole('link', { name: 'Ver PDF original' }),
  ).toBeVisible()
  await expect(page.getByText(/Lançamento manual substituído em/)).toBeVisible()
  const pdfId = page.url().split('/').pop()!
  const details = await (
    await request.get(`${server}/api/boletins/${pdfId}`)
  ).json()
  expect(details.origem).toBe('PDF')
  expect(
    details.cargos[0].candidatos.find(
      (c: { numero: string }) => c.numero === candidate.numero,
    ).votos,
  ).toBe(candidate.votos)
  expect(details.historico_manual[0].boletim.id).toBe(manualId)
  expect(details.tem_foto).toBe(true)
  expect(
    (await request.get(`${server}/api/boletins/${manualId}`)).status(),
  ).toBe(404)
})

test('campo vazio não vira zero na revisão', async ({ page }) => {
  await page.goto('/digitar')
  await page.getByLabel('Zona', { exact: true }).fill('13')
  await page.getByLabel('Seção principal', { exact: true }).fill('9999')
  await page
    .getByRole('button', { name: 'Conferir lançamento', exact: true })
    .click()
  await expect(page.getByRole('alert')).toContainText(
    'Informe os votos de pelo menos um candidato.',
  )
  await page.getByLabel('Número do candidato 1').fill('1234')
  await page.getByLabel('Nome do candidato 1').fill('Candidato de teste')
  await page.getByLabel('Votos do candidato 1').fill('0')
  await page.getByRole('button', { name: 'Adicionar candidato' }).click()
  await page
    .getByRole('button', { name: 'Conferir lançamento', exact: true })
    .click()
  await expect(page.locator('tbody tr')).toHaveCount(1)
  await expect(page.locator('tbody tr td').last()).toHaveText('0')
})
