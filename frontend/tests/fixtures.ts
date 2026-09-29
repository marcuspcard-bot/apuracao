import { test as base, expect, type BrowserContext } from '@playwright/test'
export { expect }
export type { Page, Browser } from '@playwright/test'
export async function adminSession(context: BrowserContext) {
  await context.addInitScript(() =>
    sessionStorage.setItem(
      'apuracao.admin.session',
      JSON.stringify({
        token: 'isolated-test-admin-token',
        expiresAt: Date.now() + 3600000,
      }),
    ),
  )
}
export const test = base.extend({
  context: async ({ context }, use) => {
    await adminSession(context)
    await use(context)
  },
})
