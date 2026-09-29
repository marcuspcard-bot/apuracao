import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  FileStack,
  LoaderCircle,
  Plus,
  RotateCw,
} from 'lucide-react'
import { errorMessage, formatNumber, listBoletins } from '../services/api'
import type { BoletimSummary } from '../types/boletim'

export function Boletins() {
  const [rows, setRows] = useState<BoletimSummary[]>([])
  const [page, setPage] = useState(0)
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    listBoletins(page * 20, controller.signal)
      .then(setRows)
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [page, reload])
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ARQUIVO</span>
          <h1>Boletins importados</h1>
          <p>Registros de Boletins de Urna.</p>
        </div>
        <Link className="button primary" to="/importar">
          <Plus size={17} />
          Importar PDF
        </Link>
      </div>
      <div className="section-heading list-heading">
        <h2>Boletins</h2>
        <button
          className="icon-button"
          title="Atualizar listagem"
          aria-label="Atualizar listagem"
          onClick={() => setReload((n) => n + 1)}
          disabled={loading}
        >
          <RotateCw size={18} />
        </button>
      </div>
      {error ? (
        <div className="notice error" role="alert">
          {error}
        </div>
      ) : loading ? (
        <div className="loading-area" role="status">
          <LoaderCircle size={28} className="spin" />
          Carregando boletins...
        </div>
      ) : !rows.length ? (
        <div className="empty-state">
          <FileStack size={40} strokeWidth={1.5} />
          <h2>{page ? 'Não há mais boletins' : 'Nenhum boletim importado'}</h2>
          <Link className="button" to="/importar">
            <Plus size={16} />
            Importar PDF
          </Link>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="boletins-table">
            <thead>
              <tr>
                <th>Município</th>
                <th>Zona</th>
                <th>Seção</th>
                <th>Agregadas</th>
                <th>Comparecimento</th>
                <th>Data de importação</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.id}>
                  <td>
                    <strong>{b.municipio_nome}</strong>
                    <small className="muted code">{b.municipio_codigo}</small>
                  </td>
                  <td className="code">{b.zona}</td>
                  <td className="code">{b.secao}</td>
                  <td>{b.quantidade_secoes_agregadas}</td>
                  <td>{formatNumber(b.comparecimento)}</td>
                  <td>{new Date(b.created_at).toLocaleDateString('pt-BR')}</td>
                  <td>
                    <Link
                      className="text-link"
                      to={`/boletins/${b.id}`}
                      aria-label={`Ver seção ${b.secao}`}
                    >
                      Ver <ArrowRight size={16} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="pagination">
        <span className="muted">Página {page + 1}</span>
        <div>
          <button
            className="icon-button"
            title="Página anterior"
            aria-label="Página anterior"
            disabled={page === 0 || loading}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft size={19} />
          </button>
          <button
            className="icon-button"
            title="Próxima página"
            aria-label="Próxima página"
            disabled={rows.length < 20 || loading || !!error}
            onClick={() => setPage((p) => p + 1)}
          >
            <ChevronRight size={19} />
          </button>
        </div>
      </div>
    </>
  )
}
