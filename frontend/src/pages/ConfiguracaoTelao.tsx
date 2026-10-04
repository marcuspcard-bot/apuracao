import { useEffect, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  Check,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  LoaderCircle,
  Plus,
  RotateCw,
  Save,
  Trash2,
} from 'lucide-react'
import { errorMessage, formatDate } from '../services/api'
import {
  getScreenConfig,
  saveScreenConfig,
  searchCandidates,
} from '../services/telao'
import type { AvailableCandidate, ScreenConfig } from '../types/telao'
import { CandidatePhotoEditor } from '../components/CandidatePhotoEditor'
import '../telao.css'

export function ConfiguracaoTelao() {
  const [config, setConfig] = useState<ScreenConfig | null>(null)
  const [cargo, setCargo] = useState('DEPUTADO ESTADUAL')
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [results, setResults] = useState<AvailableCandidate[]>([])
  const [more, setMore] = useState(false)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)
  const [dirty, setDirty] = useState(false)
  const [reload, setReload] = useState(0)
  const [photoBusy, setPhotoBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    void getScreenConfig(controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) {
          setConfig(next)
          setError('')
          setDirty(false)
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [reload])

  const available = Boolean(config)
  useEffect(() => {
    if (!available) return
    const controller = new AbortController()
    setSearching(true)
    setSearchError('')
    setResults([])
    setMore(false)
    const timer = setTimeout(() => {
      void searchCandidates(cargo, query, offset, controller.signal)
        .then((next) => {
          if (!controller.signal.aborted) {
            setResults(next.candidatos)
            setMore(next.tem_mais)
          }
        })
        .catch((e) => {
          if (!controller.signal.aborted) setSearchError(errorMessage(e))
        })
        .finally(() => {
          if (!controller.signal.aborted) setSearching(false)
        })
    }, 300)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [available, cargo, query, offset, reload])

  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  function change(patch: Partial<ScreenConfig>) {
    setConfig((current) => (current ? { ...current, ...patch } : current))
    setDirty(true)
    setSuccess('')
  }

  function move(index: number, direction: number) {
    if (!config) return
    const items = [...config.candidatos]
    const next = index + direction
    if (next < 0 || next >= items.length) return
    ;[items[index], items[next]] = [items[next], items[index]]
    change({ candidatos: items })
  }

  function changePhoto(cargo: string, numero: string, foto: string | null) {
    setConfig((current) =>
      current
        ? {
            ...current,
            candidatos: current.candidatos.map((candidate) =>
              candidate.cargo === cargo && candidate.numero === numero
                ? { ...candidate, foto }
                : candidate,
            ),
          }
        : current,
    )
    setDirty(true)
    setSuccess('')
  }

  async function save() {
    if (!config || saving || photoBusy) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const next = await saveScreenConfig({
        versao: config.versao,
        cards_por_pagina: config.cards_por_pagina,
        tempo_rotacao_segundos: config.tempo_rotacao_segundos,
        ativo: config.ativo,
        candidatos: config.candidatos.map(({ cargo, numero, ativo, foto }) => ({
          cargo,
          numero,
          ativo,
          ...(foto !== undefined ? { foto } : {}),
        })),
      })
      setConfig(next)
      setDirty(false)
      setSuccess('Configuração do telão salva com sucesso.')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="screen-admin">
      <div className="page-heading">
        <div>
          <span className="eyebrow">DIVULGAÇÃO</span>
          <h1>Configuração do telão</h1>
          <p>
            Bacabal / MA · Zona 0013
            {config &&
              ` · ${formatDate(config.eleicao_data)} · ${config.eleicao_turno}º turno`}
          </p>
        </div>
        <a
          className="button"
          href="/divulgacao"
          target="_blank"
          rel="noopener noreferrer"
        >
          <ExternalLink size={17} />
          Visualizar telão
        </a>
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
          <button
            className="button"
            disabled={saving || loading || photoBusy}
            onClick={() => {
              setSuccess('')
              setReload((n) => n + 1)
            }}
          >
            <RotateCw size={16} />
            Recarregar configuração
          </button>
        </div>
      )}
      {success && (
        <div className="notice success" role="status">
          <Check size={18} />
          {success}
        </div>
      )}
      {loading && (
        <p className="overview-empty" role="status">
          Carregando configuração...
        </p>
      )}
      {config && !loading && (
        <>
          <fieldset className="screen-settings" disabled={saving}>
            <legend>Exibição</legend>
            <label>
              Cards por página
              <input
                aria-label="Cards por página"
                type="number"
                min={1}
                max={12}
                value={config.cards_por_pagina}
                onChange={(e) =>
                  change({ cards_por_pagina: Number(e.target.value) })
                }
              />
            </label>
            <label>
              Rotação em segundos
              <input
                aria-label="Rotação em segundos"
                type="number"
                min={5}
                max={300}
                value={config.tempo_rotacao_segundos}
                onChange={(e) =>
                  change({ tempo_rotacao_segundos: Number(e.target.value) })
                }
              />
            </label>
            <label className="screen-checkbox">
              <input
                type="checkbox"
                checked={config.ativo}
                onChange={(e) => change({ ativo: e.target.checked })}
              />
              Telão ativo
            </label>
          </fieldset>
          <div className="screen-editor">
            <section
              className="screen-search"
              aria-labelledby="available-title"
            >
              <h2 id="available-title">Candidatos disponíveis</h2>
              <div className="screen-search-fields">
                <label>
                  Cargo
                  <select
                    aria-label="Cargo"
                    value={cargo}
                    onChange={(e) => {
                      setCargo(e.target.value)
                      setOffset(0)
                    }}
                  >
                    {config.cargos.map((office) => (
                      <option key={office}>{office}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Pesquisar candidato
                  <input
                    type="search"
                    aria-label="Pesquisar candidato"
                    placeholder="Número ou nome"
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value)
                      setOffset(0)
                    }}
                  />
                </label>
              </div>
              {searchError && (
                <p className="notice error" role="alert">
                  {searchError}
                </p>
              )}
              {searching ? (
                <p className="overview-empty" role="status">
                  Consultando candidatos...
                </p>
              ) : !results.length && !searchError ? (
                <p className="overview-empty">
                  Nenhum candidato encontrado nos boletins recebidos.
                </p>
              ) : null}
              <ul className="screen-search-results">
                {results.map((candidate) => {
                  const selected = config.candidatos.some(
                    (c) =>
                      c.cargo === candidate.cargo &&
                      c.numero.replace(/^0+(?=\d)/, '') ===
                        candidate.numero.replace(/^0+(?=\d)/, ''),
                  )
                  return (
                    <li key={`${candidate.cargo}:${candidate.numero}`}>
                      <div>
                        <span className="code">{candidate.numero}</span>
                        <strong>{candidate.nome}</strong>
                      </div>
                      <button
                        className="icon-button"
                        disabled={selected || saving}
                        title={
                          selected ? 'Já selecionado' : 'Adicionar ao telão'
                        }
                        aria-label={`Adicionar ${candidate.numero} - ${candidate.nome} ao telão`}
                        onClick={() =>
                          change({
                            candidatos: [
                              ...config.candidatos,
                              { ...candidate, ativo: true },
                            ],
                          })
                        }
                      >
                        {selected ? <Check size={18} /> : <Plus size={18} />}
                      </button>
                    </li>
                  )
                })}
              </ul>
              {(offset > 0 || more) && (
                <div className="pagination">
                  <span>Página {Math.floor(offset / 20) + 1}</span>
                  <div>
                    <button
                      className="icon-button"
                      aria-label="Candidatos anteriores"
                      title="Candidatos anteriores"
                      disabled={offset === 0 || searching}
                      onClick={() => setOffset((n) => n - 20)}
                    >
                      <ChevronLeft size={18} />
                    </button>
                    <button
                      className="icon-button"
                      aria-label="Próximos candidatos"
                      title="Próximos candidatos"
                      disabled={!more || searching}
                      onClick={() => setOffset((n) => n + 20)}
                    >
                      <ChevronRight size={18} />
                    </button>
                  </div>
                </div>
              )}
            </section>
            <section
              className="screen-selected"
              aria-labelledby="selected-title"
            >
              <div className="section-heading">
                <h2 id="selected-title">Candidatos do telão</h2>
                <span className="muted">
                  {config.candidatos.length} selecionados
                </span>
              </div>
              {!config.candidatos.length && (
                <p className="overview-empty">Nenhum candidato selecionado.</p>
              )}
              <ol className="screen-selection-list">
                {config.candidatos.map((candidate, index) => (
                  <li key={`${candidate.cargo}:${candidate.numero}`}>
                    <div className="selection-portrait">
                      <CandidatePhotoEditor
                        candidate={candidate}
                        disabled={saving || photoBusy}
                        onBusy={setPhotoBusy}
                        onError={setError}
                        onChange={(foto) =>
                          changePhoto(candidate.cargo, candidate.numero, foto)
                        }
                      />
                      <span className="selection-order">{index + 1}</span>
                    </div>
                    <div className="selection-name">
                      <span className="eyebrow">{candidate.cargo}</span>
                      <strong>
                        <span className="code">{candidate.numero}</span>{' '}
                        {candidate.nome}
                      </strong>
                      <label className="screen-checkbox">
                        <input
                          type="checkbox"
                          aria-label={`Exibir ${candidate.numero} - ${candidate.nome}`}
                          checked={candidate.ativo}
                          disabled={saving}
                          onChange={(e) =>
                            change({
                              candidatos: config.candidatos.map((c, i) =>
                                i === index
                                  ? { ...c, ativo: e.target.checked }
                                  : c,
                              ),
                            })
                          }
                        />
                        Exibir
                      </label>
                    </div>
                    <div className="selection-actions">
                      <button
                        className="icon-button"
                        title="Mover para cima"
                        aria-label={`Mover ${candidate.numero} para cima`}
                        disabled={index === 0 || saving}
                        onClick={() => move(index, -1)}
                      >
                        <ArrowUp size={17} />
                      </button>
                      <button
                        className="icon-button"
                        title="Mover para baixo"
                        aria-label={`Mover ${candidate.numero} para baixo`}
                        disabled={
                          index === config.candidatos.length - 1 || saving
                        }
                        onClick={() => move(index, 1)}
                      >
                        <ArrowDown size={17} />
                      </button>
                      <button
                        className="icon-button remove-selection"
                        title="Remover do telão"
                        aria-label={`Remover ${candidate.numero} do telão`}
                        disabled={saving}
                        onClick={() =>
                          change({
                            candidatos: config.candidatos.filter(
                              (_, i) => i !== index,
                            ),
                          })
                        }
                      >
                        <Trash2 size={17} />
                      </button>
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          </div>
          <div className="screen-save-bar">
            <span className="muted">
              {dirty ? 'Alterações não salvas' : 'Configuração salva'}
            </span>
            <button
              className="button primary"
              disabled={
                saving ||
                photoBusy ||
                !dirty ||
                config.cards_por_pagina < 1 ||
                config.cards_por_pagina > 12 ||
                config.tempo_rotacao_segundos < 5 ||
                config.tempo_rotacao_segundos > 300
              }
              onClick={() => void save()}
            >
              {saving ? (
                <LoaderCircle size={18} className="spin" />
              ) : (
                <Save size={18} />
              )}
              {saving ? 'Salvando...' : 'Salvar configuração do telão'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
