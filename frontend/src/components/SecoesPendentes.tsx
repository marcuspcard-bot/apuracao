import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  LoaderCircle,
  Upload,
  X,
} from 'lucide-react'
import { confirmSections, errorMessage, previewSections } from '../services/api'
import type {
  Section,
  SectionGroup,
  SectionRegistryPreview,
} from '../types/acompanhamento'

function SectionNumber({ section }: { section: Section }) {
  const label = `${section.apurada ? 'Apurada' : 'Pendente'} - seção ${section.numero}`
  return (
    <span className="section-number-status">
      <span
        className={`section-status-dot ${section.apurada ? 'counted' : 'pending'}`}
        role="img"
        aria-label={label}
        title={label}
      />
      {section.boletim_id ? (
        <Link
          to={`/boletins/${section.boletim_id}`}
          className="code"
          title={`Boletim da seção ${section.secao_principal_bu}`}
        >
          {section.numero}
        </Link>
      ) : (
        <span className="code">{section.numero}</span>
      )}
      {section.vinculo_divergente && (
        <span
          className="section-mismatch"
          title={`O BU vincula esta seção à ${section.secao_principal_bu}, diferente do cadastro.`}
        >
          <AlertTriangle size={14} aria-label="Vínculo diferente no BU" />
        </span>
      )}
    </span>
  )
}

export function SecoesPendentes({
  groups,
  registered,
  onSaved,
  allowImport = true,
}: {
  groups: SectionGroup[]
  registered: boolean
  onSaved: () => void
  allowImport?: boolean
}) {
  const input = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<SectionRegistryPreview | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [reading, setReading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [filter, setFilter] = useState('TODAS')
  const [zone, setZone] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const zones = [...new Set(groups.map((g) => g.zona))].sort(
    (a, b) => Number(a) - Number(b),
  )
  const visible = groups.filter(
    (g) =>
      (filter === 'TODAS' ||
        (filter === 'PENDENTES'
          ? g.status !== 'APURADA'
          : g.status === 'APURADA')) &&
      (!zone || g.zona === zone) &&
      [g.principal, ...g.agregadas].some((s) =>
        s.numero.includes(search.trim()),
      ),
  )
  const pages = Math.max(1, Math.ceil(visible.length / 20))
  const currentPage = Math.min(page, pages - 1)

  async function readList(file: File) {
    setPreview(null)
    setError('')
    setSuccess('')
    if (file.size > 1024 * 1024) {
      setError('A lista excede o limite de 1 MB.')
      return
    }
    setReading(true)
    try {
      setPreview(await previewSections(file))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setReading(false)
    }
  }

  async function confirmList() {
    if (!preview || saving) return
    setSaving(true)
    setError('')
    try {
      await confirmSections(preview)
      setPreview(null)
      setSuccess('Lista de seções salva.')
      setPage(0)
      setZone('')
      setSearch('')
      setFilter('TODAS')
      onSaved()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section
      className="overview-section section-registry"
      aria-labelledby="pending-heading"
    >
      <div className="section-heading registry-heading">
        <h2 id="pending-heading">Seções pendentes</h2>
        {allowImport && (
          <div className="registry-actions">
            <a
              className="icon-button"
              title="Baixar modelo CSV"
              aria-label="Baixar modelo CSV"
              download="modelo-secoes.csv"
              href="data:text/csv;charset=utf-8,zona%3Bsecao_principal%3Bsecoes_agregadas%0A"
            >
              <Download size={17} />
            </a>
            <button
              className="button"
              onClick={() => input.current?.click()}
              disabled={reading || saving}
            >
              {reading ? (
                <LoaderCircle size={17} className="spin" />
              ) : (
                <Upload size={17} />
              )}
              Importar lista
            </button>
            <input
              ref={input}
              className="sr-only"
              type="file"
              accept=".csv,text/csv"
              aria-label="Lista de seções em CSV"
              disabled={reading || saving}
              onChange={(e) => {
                const file = e.target.files?.[0]
                e.target.value = ''
                if (file) void readList(file)
              }}
            />
          </div>
        )}
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {success && (
        <div className="notice success" role="status">
          <Check size={17} />
          {success}
        </div>
      )}
      {preview && (
        <div
          className="registry-preview"
          aria-label="Conferência da lista de seções"
        >
          <div className="section-heading">
            <h3>Conferir lista</h3>
            <span>{preview.total_secoes} seções</span>
          </div>
          <p className="muted">Bacabal / MA · 2026 · 1º turno</p>
          {preview.substitui_lista && (
            <p className="registry-warning">
              O cadastro anterior será substituído. Os boletins salvos serão
              preservados.
            </p>
          )}
          <div className="table-scroll registry-preview-scroll">
            <table>
              <thead>
                <tr>
                  <th>Zona</th>
                  <th>Principal / isolada</th>
                  <th>Agregadas</th>
                </tr>
              </thead>
              <tbody>
                {preview.grupos.map((g) => (
                  <tr key={`${g.zona}-${g.secao_principal}`}>
                    <td className="code">{g.zona}</td>
                    <td className="code">{g.secao_principal}</td>
                    <td>{g.secoes_agregadas.join(', ') || 'Nenhuma'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="registry-confirm">
            <button
              className="button"
              disabled={saving}
              onClick={() => setPreview(null)}
            >
              <X size={17} />
              Cancelar
            </button>
            <button
              className="button primary"
              disabled={saving}
              onClick={() => void confirmList()}
            >
              {saving ? (
                <LoaderCircle size={17} className="spin" />
              ) : (
                <Check size={17} />
              )}
              {preview.substitui_lista ? 'Substituir lista' : 'Salvar lista'}
            </button>
          </div>
        </div>
      )}
      {!registered ? (
        <p className="overview-empty">
          {allowImport
            ? 'Não informado. Lista de seções ainda não importada.'
            : 'Sem cadastro de seções para esta data.'}
        </p>
      ) : (
        <>
          <div className="registry-toolbar">
            <div
              className="segmented-control"
              role="group"
              aria-label="Situação das seções"
            >
              {(['TODAS', 'PENDENTES', 'APURADAS'] as const).map((value) => (
                <button
                  key={value}
                  aria-pressed={filter === value}
                  onClick={() => {
                    setFilter(value)
                    setPage(0)
                  }}
                >
                  {
                    {
                      TODAS: 'Todas',
                      PENDENTES: 'Pendentes',
                      APURADAS: 'Apuradas',
                    }[value]
                  }
                </button>
              ))}
            </div>
            <span className="muted">
              {visible.length} {visible.length === 1 ? 'grupo' : 'grupos'}
            </span>
          </div>
          <div className="overview-filters">
            <label>
              Zona da lista
              <select
                aria-label="Zona da lista"
                value={zone}
                onChange={(e) => {
                  setZone(e.target.value)
                  setPage(0)
                }}
              >
                <option value="">Todas as zonas</option>
                {zones.map((z) => (
                  <option key={z}>{z}</option>
                ))}
              </select>
            </label>
            <label>
              Buscar seção na lista
              <input
                type="search"
                inputMode="numeric"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(0)
                }}
              />
            </label>
          </div>
          <ul className="section-status-list">
            {visible
              .slice(currentPage * 20, (currentPage + 1) * 20)
              .map((g) => (
                <li
                  className="section-status-row"
                  key={`${g.zona}-${g.secao_principal}`}
                >
                  <span className="muted section-zone">
                    Zona <span className="code">{g.zona}</span>
                  </span>
                  <div className="section-members">
                    <span className="main-section-number">
                      Seção <SectionNumber section={g.principal} />
                    </span>
                    {g.agregadas.length ? (
                      <span className="aggregate-members">
                        <span>(agregadas:</span>
                        {g.agregadas.map((s, i) => (
                          <span className="aggregate-member" key={s.numero}>
                            <SectionNumber section={s} />
                            {i < g.agregadas.length - 1 ? ',' : ')'}
                          </span>
                        ))}
                      </span>
                    ) : (
                      <span className="muted">(isolada)</span>
                    )}
                  </div>
                  <span
                    className={`section-state-label ${g.status.toLowerCase()}`}
                  >
                    {
                      {
                        APURADA: 'Apurada',
                        PENDENTE: 'Pendente',
                        PARCIAL: 'Parcial',
                      }[g.status]
                    }
                  </span>
                </li>
              ))}
          </ul>
          {!visible.length && (
            <p className="overview-empty">
              Nenhuma seção corresponde aos filtros.
            </p>
          )}
          {pages > 1 && (
            <div className="pagination">
              <span>
                Página {currentPage + 1} de {pages}
              </span>
              <div>
                <button
                  className="icon-button"
                  title="Página anterior da lista"
                  aria-label="Página anterior da lista"
                  disabled={!currentPage}
                  onClick={() => setPage(currentPage - 1)}
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  className="icon-button"
                  title="Próxima página da lista"
                  aria-label="Próxima página da lista"
                  disabled={currentPage + 1 >= pages}
                  onClick={() => setPage(currentPage + 1)}
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  )
}
