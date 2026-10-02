import { test, expect } from '@playwright/test'

test('páginas abrem diretamente e após recarga sem login ou tokens', async ({
  page,
}, testInfo) => {
  const requests: { url: string; authorization?: string; admin?: string }[] = []
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/')) {
      requests.push({
        url: request.url(),
        authorization: request.headers().authorization,
        admin: request.headers()['x-telao-admin'],
      })
    }
  })
  for (const [url, title] of [
    ['/', 'Importar Boletim de Urna'],
    ['/importar', 'Importar Boletim de Urna'],
    ['/boletins', 'Boletins importados'],
    ['/configuracao-telao', 'Configuração do telão'],
    ['/divulgacao', 'Eleições 2026 · Bacabal-MA'],
    ['/acompanhamento', 'Bacabal / MA'],
  ]) {
    await page.goto(url)
    await expect(
      page.getByRole('heading', { name: title, exact: true }),
    ).toBeVisible()
    await expect(
      page.locator('input[type="password"], input[type="email"]'),
    ).toHaveCount(0)
    await expect(
      page.getByRole('button', { name: /^(Entrar|Sair)$/ }),
    ).toHaveCount(0)
    await expect(
      page.getByRole('heading', { name: 'Acesso administrativo' }),
    ).toHaveCount(0)
    await expect(page.getByRole('alert')).toHaveCount(0)
  }
  await page.reload()
  await expect(
    page.getByRole('heading', { name: 'Bacabal / MA', exact: true }),
  ).toBeVisible()
  await expect(page.getByText('Conectado', { exact: true })).toBeVisible()
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true)
    await page.screenshot({
      path: testInfo.outputPath(`sem-login-${width}.png`),
      fullPage: true,
    })
  }
  expect(requests.length).toBeGreaterThan(0)
  expect(requests.some((request) => request.url.includes('/api/auth/'))).toBe(
    false,
  )
  expect(
    requests.some((request) => request.authorization || request.admin),
  ).toBe(false)
})

test('sessão antiga é descartada sem afetar outros dados da aba', async ({
  page,
}) => {
  await page.addInitScript(() => {
    sessionStorage.setItem(
      'apuracao.admin.session',
      JSON.stringify({
        token: 'obsolete-token',
        expiresAt: Date.now() + 3600000,
      }),
    )
    sessionStorage.setItem('unrelated-preference', 'keep')
  })
  const response = page.waitForResponse(
    (response) => new URL(response.url()).pathname === '/api/boletins',
  )
  await page.goto('/boletins')
  expect((await response).status()).toBe(200)
  await expect(
    page.getByRole('heading', { name: 'Boletins importados' }),
  ).toBeVisible()
  expect(
    await page.evaluate(() => sessionStorage.getItem('apuracao.admin.session')),
  ).toBeNull()
  expect(
    await page.evaluate(() => sessionStorage.getItem('unrelated-preference')),
  ).toBe('keep')
})

test('acesso funciona mesmo com armazenamento do navegador indisponível', async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'sessionStorage', {
      get() {
        throw new DOMException('Disabled', 'SecurityError')
      },
    })
  })
  await page.goto('/importar')
  await expect(
    page.getByRole('heading', { name: 'Importar Boletim de Urna' }),
  ).toBeVisible()
  await page.getByRole('link', { name: 'Visão geral' }).click()
  await expect(page.getByText('Conectado', { exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})
