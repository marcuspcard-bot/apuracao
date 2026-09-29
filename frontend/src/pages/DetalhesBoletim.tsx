import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  LoaderCircle,
} from 'lucide-react'
import { BoletimPreview } from '../components/BoletimPreview'
import { errorMessage, getBoletim } from '../services/api'
import type { BoletimDetail } from '../types/boletim'

export function DetalhesBoletim() {
  const { id } = useParams()
  const [boletim, setBoletim] = useState<BoletimDetail | null>(null)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setBoletim(null)
    setError('')
    getBoletim(id!, controller.signal)
      .then(setBoletim)
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e))
      })
    return () => controller.abort()
  }, [id, reload])
  return (
    <>
      <Link to="/boletins" className="back-link">
        <ArrowLeft size={16} />
        Boletins importados
      </Link>
      {error ? (
        <div role="alert" className="notice error">
          {error}
          <button className="button" onClick={() => setReload((n) => n + 1)}>
            Tentar novamente
          </button>
        </div>
      ) : !boletim ? (
        <div className="loading-area" role="status">
          <LoaderCircle className="spin" />
          Carregando boletim...
        </div>
      ) : (
        <>
          <div className="page-heading">
            <div>
              <span className="eyebrow">BOLETIM DE URNA</span>
              <h1>Seção {boletim.dados.secao}</h1>
              <p>
                {boletim.dados.municipio.nome} · Zona {boletim.dados.zona}
              </p>
            </div>
            <Link
              className="button"
              to={`/boletins/${id}/pdf`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <ExternalLink size={17} />
              Ver PDF original
            </Link>
          </div>
          <div className="notice success">
            <CheckCircle2 size={20} />
            <span>
              Boletim salvo em{' '}
              {new Date(boletim.created_at).toLocaleString('pt-BR')}.
            </span>
          </div>
          <BoletimPreview dados={boletim.dados} />
          <section className="document-section">
            <h2>Arquivo original</h2>
            <dl className="technical-data">
              <div>
                <dt>Nome do arquivo</dt>
                <dd>{boletim.arquivo_nome_original}</dd>
              </div>
              <div>
                <dt>SHA-256</dt>
                <dd className="code hash">{boletim.arquivo_hash}</dd>
              </div>
            </dl>
          </section>
        </>
      )}
    </>
  )
}
