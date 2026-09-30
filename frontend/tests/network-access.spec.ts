import { expect, test } from '@playwright/test'

test('telão usa API pública e operadores usam a API própria, sem chaves no navegador', async ({ page }) => {
  const requests: Array<{ url: string; headers: Record<string, string> }> = []
  page.on('request', (request) => {
    if (request.url().includes('/api/')) {
      requests.push({ url: request.url(), headers: request.headers() })
    }
  })
  const publicResponse = page.waitForResponse(
    (response) => response.url() === 'http://localhost:8001/api/divulgacao',
  )
  await page.goto('/divulgacao')
  expect((await publicResponse).status()).toBe(200)
  await expect.poll(() => requests.some((request) => request.url === 'http://localhost:8001/api/divulgacao/eventos')).toBe(true)

  const privateResponse = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return url.origin === 'http://127.0.0.1:8001' && url.pathname === '/api/boletins'
  })
  await page.goto('/boletins')
  expect((await privateResponse).status()).toBe(200)
  for (const request of requests) {
    expect(request.headers).not.toHaveProperty('x-operator-proxy-key')
    expect(request.headers).not.toHaveProperty('authorization')
  }
  await expect(page.locator('input[type="password"]')).toHaveCount(0)
})
