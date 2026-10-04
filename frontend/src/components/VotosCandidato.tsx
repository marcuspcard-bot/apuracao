import { useState } from 'react'
import { Link } from 'react-router-dom'
import { formatNumber } from '../services/api'
import { useVotosSecao } from '../hooks/useVotosSecao'
import type {
  Candidate,
  Overview,
  SectionSelection,
} from '../types/acompanhamento'

const candidateKey = (number: string) => number.replace(/^0+(?=\d)/, '')

const sectionKey = ({ zona, secao }: SectionSelection) =>
  `${zona.replace(/^0+(?=\d)/, '')}:${secao.replace(/^0+(?=\d)/, '')}`

function sectionOptions(data: Overview, selected: SectionSelection | null) {
  const options = new Map<string, SectionSelection>()
  const add = (section: SectionSelection) => {
    options.set(sectionKey(section), section)
  }
  for (const group of data.grupos_secoes ?? []) {
    for (const section of [group.principal, ...group.agregadas]) {
      add({ zona: group.zona, secao: section.numero })
    }
  }
  for (const section of data.secoes) add(section)
  if (selected) add(selected)
  return [...options.values()].sort((a, b) =>
    sectionKey(a).localeCompare(sectionKey(b), 'pt-BR', { numeric: true }),
  )
}

export function VotosCandidato({
  data,
  refreshVersion,
}: {
  data: Overview
  refreshVersion: number
}) {
  const [officeName, setOfficeName] = useState('')
  const [candidateNumber, setCandidateNumber] = useState('')
  const [section, setSection] = useState<SectionSelection | null>(null)
  const office = data.cargos.find((c) => c.nome === officeName)
  const candidate = office?.candidatos.find(
    (c) => candidateKey(c.numero) === candidateNumber,
  )
  const options = sectionOptions(data, section)

  return (
    <section className="overview-section" aria-labelledby="candidate-heading">
      <div className="section-heading">
        <h2 id="candidate-heading">Votos por candidato</h2>
        <span className="muted">Bacabal / MA</span>
      </div>
      <div className="overview-filters candidate-filters">
        <label>
          Cargo
          <select
            aria-label="Cargo"
            value={officeName}
            onChange={(e) => {
              setOfficeName(e.target.value)
              setCandidateNumber('')
            }}
          >
            <option value="">Selecionar cargo</option>
            {data.cargos.map((c) => (
              <option key={c.nome}>{c.nome}</option>
            ))}
          </select>
        </label>
        <label>
          Candidato
          <select
            aria-label="Candidato"
            value={candidate?.numero ?? ''}
            disabled={!office}
            onChange={(e) => setCandidateNumber(candidateKey(e.target.value))}
          >
            <option value="">Selecionar candidato</option>
            {office?.candidatos.map((c) => (
              <option value={c.numero} key={c.numero}>
                {c.numero} - {c.nome}
              </option>
            ))}
          </select>
        </label>
        <label>
          Seção
          <select
            aria-label="Seção dos votos"
            value={section ? sectionKey(section) : ''}
            onChange={(e) =>
              setSection(
                options.find((s) => sectionKey(s) === e.target.value) ?? null,
              )
            }
          >
            <option value="">Todas as seções</option>
            {options.map((s) => (
              <option key={sectionKey(s)} value={sectionKey(s)}>
                Seção {s.secao} · Zona {s.zona}
              </option>
            ))}
          </select>
        </label>
      </div>
      {candidate && office ? (
        <CandidateResult
          key={section ? sectionKey(section) : 'all'}
          candidate={candidate}
          office={office}
          section={section}
          electionDate={data.eleicao.data}
          refreshVersion={refreshVersion}
        />
      ) : (
        <p className="overview-empty">
          {data.cargos.length
            ? 'Nenhum candidato selecionado.'
            : 'Ainda não há resultados de Bacabal para esta eleição.'}
        </p>
      )}
    </section>
  )
}

function CandidateResult({
  candidate: overallCandidate,
  office: overallOffice,
  section,
  electionDate,
  refreshVersion,
}: {
  candidate: Candidate
  office: Overview['cargos'][number]
  section: SectionSelection | null
  electionDate: string
  refreshVersion: number
}) {
  const { data, error, loading } = useVotosSecao(
    section,
    electionDate,
    refreshVersion,
  )
  const office = section
    ? data?.cargos.find((c) => c.nome === overallOffice.nome)
    : overallOffice
  const candidate = section
    ? office?.candidatos.find(
        (c) => candidateKey(c.numero) === candidateKey(overallCandidate.numero),
      )
    : overallCandidate
  const principal = data?.secoes.find((s) => s.tipo === 'PRINCIPAL')
  const aggregated = data?.secoes.filter((s) => s.tipo === 'AGREGADA') ?? []
  const emptyMessage = !data
    ? 'Consultando votos da seção...'
    : !data.boletins
      ? 'Aguardando boletim desta seção.'
      : data.secoes.some((s) => s.parcial)
        ? 'Votos não informados neste lançamento manual parcial.'
        : !office
          ? 'Este cargo não consta no boletim desta seção.'
          : 'Este candidato não consta no boletim desta seção.'

  return (
    <div className="candidate-result" aria-live="polite" aria-busy={loading}>
      <div className="candidate-identity">
        <span className="code">{overallCandidate.numero}</span>
        <h3>{candidate?.nome ?? overallCandidate.nome}</h3>
        <span className="muted">{overallOffice.nome}</span>
        <p className="candidate-scope">
          {section
            ? `Seção ${section.secao} · Zona ${section.zona}`
            : 'Todas as seções'}
        </p>
        {principal && aggregated.length > 0 && (
          <p className="candidate-group">
            BU da seção {principal.secao} (agregadas:{' '}
            {aggregated.map((s) => s.secao).join(', ')}). Votos conjuntos.
          </p>
        )}
        {principal?.parcial && <p>Lançamento manual — parcial.</p>}
        {principal && (
          <Link to={`/boletins/${principal.boletim_id}`}>Ver boletim</Link>
        )}
        {candidate && candidate.nomes.length > 1 && (
          <p>Nomes registrados: {candidate.nomes.join('; ')}</p>
        )}
      </div>
      {candidate ? (
        <div className="candidate-votes">
          <strong>{formatNumber(candidate.votos)}</strong>
          <span>
            {section
              ? aggregated.length
                ? 'votos no grupo'
                : 'votos na seção'
              : 'votos acumulados'}
          </span>
          {!section && (
            <small>
              {office?.boletins}{' '}
              {office?.boletins === 1 ? 'boletim' : 'boletins'} com este cargo
            </small>
          )}
        </div>
      ) : (
        !error && (
          <p className="overview-empty" role="status">
            {emptyMessage}
          </p>
        )
      )}
      {error && (
        <div className="notice error candidate-error" role="alert">
          {error}{' '}
          {data &&
            'Os votos exibidos são da última consulta bem-sucedida desta seção.'}
        </div>
      )}
      {candidate?.vagas.some((v) => v.identificacao) && (
        <dl className="candidate-seats">
          {candidate.vagas.map((v) => (
            <div key={v.identificacao ?? ''}>
              <dt>{v.identificacao ?? 'Sem identificação de vaga'}</dt>
              <dd>{formatNumber(v.votos)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
