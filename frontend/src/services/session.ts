// Session is scoped to this browser tab; no password or refresh token is stored.
const key = 'apuracao.admin.session'
const listeners = new Set<() => void>()
export function accessToken(): string {
  try {
    const session = JSON.parse(sessionStorage.getItem(key) || 'null')
    return session && Date.now() < session.expiresAt ? session.token : ''
  } catch {
    return ''
  }
}
export function setSession(token: string, seconds: number) {
  sessionStorage.setItem(
    key,
    JSON.stringify({ token, expiresAt: Date.now() + seconds * 1000 }),
  )
  listeners.forEach((listener) => listener())
}
export function clearSession() {
  sessionStorage.removeItem(key)
  listeners.forEach((listener) => listener())
}
export function subscribeSession(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
