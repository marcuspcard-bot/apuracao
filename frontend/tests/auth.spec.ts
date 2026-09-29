import { test, expect } from '@playwright/test'
test.use({ extraHTTPHeaders: {} })
test('login, senha incorreta, recarga e saída', async ({ page }) => {
  await page.goto('/importar')
  await expect(
    page.getByRole('heading', { name: 'Acesso administrativo' }),
  ).toBeVisible()
  await page.getByLabel('E-mail', { exact: true }).fill('admin@example.test')
  await page.getByLabel('Senha', { exact: true }).fill('wrong')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('inválidos')
  await page.getByLabel('Senha', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(
    page.getByRole('button', { name: 'Sair', exact: true }),
  ).toBeVisible()
  await page.reload()
  await expect(
    page.getByRole('button', { name: 'Sair', exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Sair', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Acesso administrativo' }),
  ).toBeVisible()
  await page.goto('/divulgacao')
  await expect(
    page.getByRole('heading', { name: 'Acesso administrativo' }),
  ).toHaveCount(0)
})
