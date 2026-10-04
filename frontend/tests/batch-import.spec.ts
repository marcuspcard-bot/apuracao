import { test, expect } from '@playwright/test'
import path from 'node:path'

const pdf = path.resolve('../Xangai_(ZZ)_-_0001_-_0483.pdf')
test('limita a dez PDFs e salva os válidos mesmo quando um arquivo falha', async ({
  page,
}) => {
  let previews = 0
  let confirmations = 0
  await page.route('**/api/boletins/preview', async (route) => {
    previews++
    if (previews === 1) {
      await route.fulfill({
        status: 422,
        json: { detail: 'PDF inválido no lote' },
      })
    } else {
      await route.fulfill({
        json: {
          status: 'OK',
          hash: String(previews).padStart(64, '0'),
          arquivo_nome: `BU-${previews}.pdf`,
          preview_token: `token-${previews}`,
          expires_in: 900,
          problemas: [],
          dados: {
            eleicao: {
              descricao: 'Eleição teste',
              turno: 1,
              data: '2026-10-04',
            },
            municipio: { codigo: '1', nome: 'Município teste' },
            zona: '1',
            secao: String(previews),
            local_votacao: null,
            quantidade_secoes_agregadas: 0,
            total_secoes_representadas: 1,
            secoes_agregadas: [],
            eleitores: { aptos: 10, comparecimento: 10, faltosos: 0 },
            urna: {},
            cargos: [],
            assinatura_qrcode: null,
            codigo_carga: null,
          },
        },
      })
    }
  })
  await page.route('**/api/boletins/confirmar', async (route) => {
    confirmations++
    await route.fulfill({ status: 201, json: { id: `salvo-${confirmations}` } })
  })
  await page.goto('/importar')
  await page.locator('input[type=file]').setInputFiles(Array(11).fill(pdf))
  await expect(page.getByRole('alert')).toContainText('Selecione até 10 PDFs')
  expect(previews).toBe(0)
  await page.locator('input[type=file]').setInputFiles(Array(10).fill(pdf))
  await expect(
    page.getByRole('heading', { name: 'Importar Boletins de Urna' }),
  ).toBeVisible()
  await expect(
    page.getByText('PDF inválido no lote', { exact: true }),
  ).toBeVisible()
  const saveAll = page.getByRole('button', {
    name: 'Salvar todos os boletins válidos',
  })
  await expect(saveAll).toBeEnabled({ timeout: 30000 })
  await saveAll.click()
  await expect(
    page.getByText('9 de 10 boletins salvos', { exact: false }),
  ).toBeVisible()
  expect(previews).toBe(10)
  expect(confirmations).toBe(9)
})
