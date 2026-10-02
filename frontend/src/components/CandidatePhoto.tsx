import { useEffect, useState } from 'react'
import { UserRound } from 'lucide-react'
import { api } from '../services/api'

export function CandidatePhoto({
  source,
  name,
}: {
  source?: string | null
  name: string
}) {
  const [failed, setFailed] = useState<string | null>(null)
  const url = source?.startsWith('data:image/')
    ? source
    : source
      ? api.getUri({ url: source })
      : null
  useEffect(() => {
    if (!failed || failed !== url) return
    const timer = setTimeout(() => setFailed(null), 10000)
    return () => clearTimeout(timer)
  }, [failed, url])
  return (
    <span className="candidate-portrait">
      {url && failed !== url ? (
        <img src={url} alt={`Foto de ${name}`} onError={() => setFailed(url)} />
      ) : (
        <UserRound aria-label={`Sem foto de ${name}`} role="img" />
      )}
    </span>
  )
}
