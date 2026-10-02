import { useEffect, useState, type CSSProperties } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Maximize,
  Minimize,
  Monitor,
} from 'lucide-react'
import { useDivulgacao } from '../hooks/useDivulgacao'
import { ScreenText } from '../components/ScreenText'
import { CandidatePhoto } from '../components/CandidatePhoto'
import { formatNumber } from '../services/api'
import '../telao.css'

const accents = [
  '#59d05b',
  '#5e9bff',
  '#ff6578',
  '#b6de45',
  '#8b92ff',
  '#f5bf59',
]

function capacity() {
  return Math.max(
    1,
    Math.min(
      12,
      Math.floor(
        (window.innerHeight - 190) / (window.innerWidth < 600 ? 76 : 100),
      ),
    ),
  )
}

export function Divulgacao() {
  const { data, error } = useDivulgacao()
  const [limit, setLimit] = useState(capacity)
  const [page, setPage] = useState(0)
  const [fullscreen, setFullscreen] = useState(false)
  const [fullscreenError, setFullscreenError] = useState('')
  const perPage = Math.min(data?.cards_por_pagina ?? 6, limit)
  const pages = Math.max(1, Math.ceil((data?.candidatos.length ?? 0) / perPage))
  const currentPage = Math.min(page, pages - 1)
  const visible =
    data?.candidatos.slice(
      currentPage * perPage,
      (currentPage + 1) * perPage,
    ) ?? []
  const selection = data?.candidatos.map((c) => c.id).join(',') ?? ''
  const counted = data?.urnas_apuradas ?? 0
  const total = data?.total_urnas
  const progress = total != null && total > 0 ? (counted / total) * 100 : null
  const percentage = progress?.toLocaleString('pt-BR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })

  useEffect(() => {
    const resize = () => setLimit(capacity())
    const changed = () => setFullscreen(Boolean(document.fullscreenElement))
    window.addEventListener('resize', resize)
    document.addEventListener('fullscreenchange', changed)
    return () => {
      window.removeEventListener('resize', resize)
      document.removeEventListener('fullscreenchange', changed)
    }
  }, [])
  useEffect(() => {
    setPage(0)
  }, [selection, perPage])
  const rotation = data?.tempo_rotacao_segundos ?? 10
  useEffect(() => {
    if (pages <= 1) return
    const timer = setInterval(
      () => setPage((current) => (current + 1) % pages),
      rotation * 1000,
    )
    return () => clearInterval(timer)
  }, [pages, rotation, selection, perPage])

  async function toggleFullscreen() {
    setFullscreenError('')
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
      else await document.documentElement.requestFullscreen()
    } catch {
      setFullscreenError(
        'Não foi possível ativar a tela cheia neste navegador.',
      )
    }
  }

  const state = !data
    ? error
      ? 'Não foi possível atualizar os dados. Tentando novamente...'
      : 'Carregando resultados...'
    : !data.ativo
      ? 'Divulgação pausada.'
      : !data.candidatos.length
        ? 'Nenhum candidato configurado para o telão.'
        : ''

  return (
    <div className={`disclosure-screen${fullscreen ? ' is-fullscreen' : ''}`}>
      <header className="disclosure-header">
        <h1>
          Eleições {data?.eleicao_data.slice(0, 4) ?? '2026'} · Bacabal-MA
        </h1>
        <button
          className="screen-fullscreen"
          title={fullscreen ? 'Sair da tela cheia' : 'Tela cheia'}
          aria-label={fullscreen ? 'Sair da tela cheia' : 'Tela cheia'}
          onClick={() => void toggleFullscreen()}
        >
          {fullscreen ? <Minimize size={18} /> : <Maximize size={18} />}
        </button>
      </header>
      <section className="disclosure-summary" aria-label="Apuração das urnas">
        <div className="screen-coverage-heading">
          <span>Urnas apuradas</span>
          <strong>
            {data ? formatNumber(counted) : '--'}
            {total != null && <> de {formatNumber(total)}</>}
            {percentage != null && (
              <>
                {' '}
                <span className="coverage-separator">·</span> {percentage}%
              </>
            )}
          </strong>
        </div>
        <div
          className="screen-coverage-track"
          role="progressbar"
          aria-label="Urnas apuradas"
          aria-valuemin={0}
          aria-valuemax={total ?? undefined}
          aria-valuenow={total != null ? counted : undefined}
          aria-valuetext={
            total != null
              ? `${counted} de ${total} urnas apuradas`
              : 'Total de urnas não cadastrado'
          }
        >
          <span style={{ width: `${Math.min(100, progress ?? 0)}%` }} />
        </div>
        <div
          className={`disclosure-connection${error ? ' stale' : ''}`}
          role="status"
        >
          {fullscreenError ||
            (error && data
              ? 'Não foi possível atualizar os dados. Tentando novamente...'
              : data && data.boletins_recebidos === 0
                ? 'Aguardando recebimento dos boletins.'
                : data && total == null
                  ? 'Total de urnas não cadastrado.'
                  : '\u00a0')}
        </div>
      </section>
      <main className="disclosure-main" id="main">
        {state ? (
          <div className="disclosure-empty" role="status">
            <Monitor size={38} />
            <p>{state}</p>
          </div>
        ) : (
          <div
            className="disclosure-grid"
            aria-label="Candidatos do telão"
            style={{
              gridTemplateRows: `repeat(${visible.length}, minmax(0, 1fr))`,
            }}
          >
            {visible.map((candidate) => (
              <article
                className="disclosure-candidate"
                key={candidate.id}
                data-office={candidate.cargo}
                style={
                  {
                    '--accent': accents[(candidate.ordem - 1) % accents.length],
                  } as CSSProperties
                }
                aria-label={`${candidate.cargo} - ${candidate.numero} - ${candidate.nome}`}
              >
                <CandidatePhoto
                  source={candidate.foto_url}
                  name={candidate.nome}
                />
                <div className="screen-candidate-details">
                  <div className="screen-candidate-office">
                    <ScreenText
                      text={candidate.cargo}
                      maxSize={22}
                      minSize={9}
                    />
                  </div>
                  <h2 className="screen-candidate-name">
                    <ScreenText
                      text={candidate.nome}
                      maxSize={30}
                      minSize={9}
                    />
                  </h2>
                  <div className="screen-candidate-number">
                    <ScreenText
                      text={candidate.numero}
                      maxSize={18}
                      minSize={10}
                    />
                  </div>
                </div>
                <div className="screen-candidate-votes" aria-live="polite">
                  <ScreenText
                    className="vote-value"
                    text={formatNumber(candidate.votos)}
                    suffix="VOTOS"
                    maxSize={84}
                    minSize={10}
                  />
                </div>
              </article>
            ))}
          </div>
        )}
      </main>
      <footer className="disclosure-footer">
        <div>
          <p className="screen-updated">
            Atualizado às{' '}
            {data
              ? new Date(data.ultima_atualizacao).toLocaleTimeString('pt-BR', {
                  hour: '2-digit',
                  minute: '2-digit',
                })
              : '--:--'}
          </p>
          <p>
            Resultados parciais.{' '}
            <span>Consulte a Justiça Eleitoral para o resultado oficial.</span>
          </p>
        </div>
        {pages > 1 && (
          <div className="screen-pagination">
            <button
              title="Página anterior"
              aria-label="Página anterior"
              onClick={() => setPage((currentPage + pages - 1) % pages)}
            >
              <ChevronLeft size={18} />
            </button>
            <span className="screen-page" aria-live="polite">
              Página {currentPage + 1} / {pages}
            </span>
            <button
              title="Próxima página"
              aria-label="Próxima página"
              onClick={() => setPage((currentPage + 1) % pages)}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        )}
      </footer>
    </div>
  )
}
