import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { LoaderCircle, RotateCw } from 'lucide-react'
import { api, errorMessage } from '../services/api'

export function AbrirPdf() {
  const { id } = useParams()
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setError('')
    api
      .get(`/api/boletins/${id}/pdf`, { signal: controller.signal })
      .then(({ data }) => {
        if (controller.signal.aborted) return
        const url = new URL(data.url)
        if (!['https:', 'http:'].includes(url.protocol))
          throw new Error('Endereço do PDF inválido.')
        window.location.replace(url.href)
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e))
      })
    return () => controller.abort()
  }, [id, attempt])

  return error ? (
    <div className="empty-state">
      <div className="notice error" role="alert">
        {error}
      </div>
      <button className="button" onClick={() => setAttempt((n) => n + 1)}>
        <RotateCw size={17} />
        Tentar novamente
      </button>
      <Link to={`/boletins/${id}`}>Voltar ao boletim</Link>
    </div>
  ) : (
    <div className="loading-area" role="status">
      <LoaderCircle className="spin" size={28} />
      Abrindo PDF original...
    </div>
  )
}
