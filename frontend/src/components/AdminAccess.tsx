import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { api, errorMessage } from '../services/api'
import {
  accessToken,
  clearSession,
  setSession,
  subscribeSession,
} from '../services/session'

export function AdminAccess({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(Boolean(accessToken()))
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(
    () => subscribeSession(() => setAuthenticated(Boolean(accessToken()))),
    [],
  )
  async function login(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { data } = await api.post('/api/auth/login', { email, password })
      setPassword('')
      setSession(data.access_token, data.expires_in)
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }
  async function logout() {
    setBusy(true)
    try {
      await api.post('/api/auth/logout')
    } catch {
      /* Clear local credentials even when the provider is unavailable. */
    } finally {
      clearSession()
      setBusy(false)
    }
  }
  if (authenticated)
    return (
      <>
        <div className="admin-session">
          <span>Área administrativa</span>
          <button type="button" onClick={logout} disabled={busy}>
            Sair
          </button>
        </div>
        {children}
      </>
    )
  return (
    <main className="login-shell">
      <form className="login-card" onSubmit={login}>
        <span className="eyebrow">BOLETINS DE URNA</span>
        <h1>Acesso administrativo</h1>
        <p>Entre para importar boletins e configurar o telão.</p>
        <label htmlFor="admin-email">E-mail</label>
        <input
          id="admin-email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <label htmlFor="admin-password">Senha</label>
        <input
          id="admin-password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <p role="alert">{error}</p>}
        <button className="button" disabled={busy}>
          {busy ? 'Entrando…' : 'Entrar'}
        </button>
        <a href="/divulgacao">Abrir telão público</a>
      </form>
    </main>
  )
}
