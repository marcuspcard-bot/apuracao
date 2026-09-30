import { useEffect, useState } from 'react'
import { getDisclosure } from '../services/telao'
import type { Disclosure } from '../types/telao'

export function useDivulgacao() {
  const [data, setData] = useState<Disclosure | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let pollTimer: ReturnType<typeof setTimeout>
    let debounceTimer: ReturnType<typeof setTimeout>
    let fetching = false
    let pending = false

    async function refresh() {
      if (controller.signal.aborted) return
      if (fetching) {
        pending = true
        return
      }
      fetching = true
      clearTimeout(pollTimer)
      try {
        const next = await getDisclosure(controller.signal)
        if (!controller.signal.aborted) {
          setData(next)
          setError(false)
        }
      } catch {
        if (!controller.signal.aborted) setError(true)
      } finally {
        fetching = false
        if (!controller.signal.aborted) {
          pollTimer = setTimeout(refresh, pending ? 750 : 10000)
          pending = false
        }
      }
    }

    function changed() {
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(refresh, 750)
    }

    void refresh()
    // The backend relays only invalidations. Supabase credentials never reach the browser.
    const base = import.meta.env.VITE_API_URL?.replace(/\/$/, '')
    const events = base
      ? new EventSource(`${base}/api/divulgacao/eventos`)
      : null
    events?.addEventListener('update', changed)
    events?.addEventListener('open', changed)
    return () => {
      controller.abort()
      clearTimeout(pollTimer)
      clearTimeout(debounceTimer)
      events?.close()
    }
  }, [])

  return { data, error }
}
