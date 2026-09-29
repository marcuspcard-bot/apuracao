import { useCallback, useEffect, useState } from 'react'
import { errorMessage, getOverview } from '../services/api'
import type { Overview } from '../types/acompanhamento'

const REFRESH_INTERVAL_MS = 10000

export function useAcompanhamento(electionDate?: string) {
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [reload, setReload] = useState(0)
  const refresh = useCallback(() => setReload((n) => n + 1), [])

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>

    async function poll() {
      setLoading(true)
      try {
        const next = await getOverview(controller.signal, electionDate)
        if (!controller.signal.aborted) {
          setData(next)
          setError('')
        }
      } catch (e) {
        if (!controller.signal.aborted) setError(errorMessage(e))
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
          timer = setTimeout(poll, REFRESH_INTERVAL_MS)
        }
      }
    }

    void poll()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [reload, electionDate])

  return { data, error, loading, refresh, refreshVersion: reload }
}
