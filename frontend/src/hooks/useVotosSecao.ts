import { useEffect, useState } from 'react'
import { errorMessage, getSectionVotes } from '../services/api'
import type { SectionSelection, SectionVotes } from '../types/acompanhamento'

export function useVotosSecao(
  section: SectionSelection | null,
  electionDate: string,
  refreshVersion: number,
) {
  const [data, setData] = useState<SectionVotes | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(Boolean(section))
  const zone = section?.zona
  const number = section?.secao

  useEffect(() => {
    if (!zone || !number) return
    const selected = { zona: zone, secao: number }
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>

    async function poll() {
      setLoading(true)
      try {
        const next = await getSectionVotes(
          selected,
          electionDate,
          controller.signal,
        )
        if (!controller.signal.aborted) {
          setData(next)
          setError('')
        }
      } catch (e) {
        if (!controller.signal.aborted) setError(errorMessage(e))
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
          timer = setTimeout(poll, 10000)
        }
      }
    }

    void poll()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [zone, number, electionDate, refreshVersion])

  return { data, error, loading }
}
