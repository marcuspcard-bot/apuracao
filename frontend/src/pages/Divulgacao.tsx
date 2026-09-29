import { useEffect, useState } from 'react'
import { FileCheck2, Maximize, Minimize, Monitor } from 'lucide-react'
import { useDivulgacao } from '../hooks/useDivulgacao'
import { ScreenText } from '../components/ScreenText'
import { formatNumber } from '../services/api'
import '../telao.css'

function capacity() {
  if (window.innerWidth < 600) return window.innerHeight < 700 ? 1 : 2
  if (window.innerHeight < 650) return 2
  if (window.innerWidth < 1100) return 4
  if (window.innerWidth >= 2400 && window.innerHeight >= 1300) return 12
  return 6
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
        <div className="disclosure-identity">
          <span className="screen-brand">
            <FileCheck2 size={19} />
            BOLETINS / DIVULGAÇÃO
          </span>
          <h1>BACABAL - MA</h1>
          <p>ZONA ELEITORAL 0013</p>
        </div>
        <div className="disclosure-heading">
          <h2>RESULTADOS PARCIAIS DOS BOLETINS RECEBIDOS</h2>
          {data && (
            <span>
              {new Date(`${data.eleicao_data}T12:00:00`).toLocaleDateString(
                'pt-BR',
              )}{' '}
              · {data.eleicao_turno}º turno
            </span>
          )}
        </div>
        <button
          className="screen-fullscreen"
          title={fullscreen ? 'Sair da tela cheia' : 'Tela cheia'}
          aria-label={fullscreen ? 'Sair da tela cheia' : 'Tela cheia'}
          onClick={() => void toggleFullscreen()}
        >
          {fullscreen ? <Minimize size={20} /> : <Maximize size={20} />}
        </button>
      </header>
      <div className="disclosure-summary">
        <dl>
          <div>
            <dt>BOLETINS RECEBIDOS</dt>
            <dd>{data ? formatNumber(data.boletins_recebidos) : '--'}</dd>
          </div>
          <div>
            <dt>
              {data?.total_secoes_esperadas != null
                ? 'SEÇÕES REPRESENTADAS / ESPERADAS'
                : 'SEÇÕES REPRESENTADAS'}
            </dt>
            <dd>
              {data ? formatNumber(data.secoes_representadas) : '--'}
              {data?.total_secoes_esperadas != null && (
                <span> / {formatNumber(data.total_secoes_esperadas)}</span>
              )}
            </dd>
          </div>
          <div className="screen-last-update">
            <dt>ÚLTIMA ATUALIZAÇÃO</dt>
            <dd>
              {data
                ? new Date(data.ultima_atualizacao).toLocaleTimeString('pt-BR')
                : '--'}
            </dd>
          </div>
        </dl>
        <div
          className={`disclosure-connection${error ? ' stale' : ''}`}
          role="status"
        >
          {fullscreenError ||
            (error && data
              ? 'Não foi possível atualizar os dados. Tentando novamente...'
              : data && data.boletins_recebidos === 0
                ? 'Aguardando recebimento dos boletins.'
                : '\u00a0')}
        </div>
      </div>
      <main className="disclosure-main" id="main">
        {state ? (
          <div className="disclosure-empty" role="status">
            <Monitor size={38} />
            <p>{state}</p>
          </div>
        ) : (
          <div
            className={`disclosure-grid count-${visible.length}`}
            aria-label="Candidatos do telão"
          >
            {visible.map((candidate) => (
              <article
                className="disclosure-candidate"
                key={candidate.id}
                data-office={candidate.cargo}
                aria-label={`${candidate.cargo} - ${candidate.numero} - ${candidate.nome}`}
              >
                <div className="screen-candidate-office">
                  <ScreenText text={candidate.cargo} maxSize={19} />
                </div>
                <div className="screen-candidate-number">
                  <ScreenText text={candidate.numero} maxSize={34} />
                </div>
                <h3 className="screen-candidate-name">
                  <ScreenText text={candidate.nome} maxSize={32} minSize={13} />
                </h3>
                <div className="screen-candidate-votes" aria-live="polite">
                  <ScreenText
                    className="vote-value"
                    text={formatNumber(candidate.votos)}
                    suffix="VOTOS"
                    maxSize={76}
                    minSize={20}
                  />
                </div>
              </article>
            ))}
          </div>
        )}
      </main>
      <footer className="disclosure-footer">
        <div>
          <p>
            Resultados parciais baseados nos Boletins de Urna inseridos no
            sistema.
          </p>
          <p>Dados sujeitos à inclusão de novos boletins.</p>
          <p>Consulte a Justiça Eleitoral para o resultado oficial.</p>
        </div>
        <div className="disclosure-footer-meta">
          <strong>Bacabal - MA | Zona Eleitoral 0013</strong>
          {pages > 1 && (
            <span className="screen-page" aria-live="polite">
              Página {currentPage + 1} / {pages}
            </span>
          )}
        </div>
      </footer>
    </div>
  )
}
