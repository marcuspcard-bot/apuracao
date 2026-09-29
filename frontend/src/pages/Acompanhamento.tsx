import { Link, useSearchParams } from 'react-router-dom'
import { RotateCw, CalendarDays } from 'lucide-react'
import { formatDate, formatNumber } from '../services/api'
import { SecoesPendentes } from '../components/SecoesPendentes'
import { VotosCandidato } from '../components/VotosCandidato'
import { useAcompanhamento } from '../hooks/useAcompanhamento'

export function Acompanhamento() {
  const [params, setParams] = useSearchParams()
  const electionDate = params.get('data') || undefined
  return (
    <OverviewContent
      key={electionDate ?? 'configured'}
      electionDate={electionDate}
      onDateChange={(value) => setParams({ data: value })}
    />
  )
}

function OverviewContent({
  electionDate,
  onDateChange,
}: {
  electionDate?: string
  onDateChange: (value: string) => void
}) {
  const { data, error, loading, refresh, refreshVersion } =
    useAcompanhamento(electionDate)
  const count = (value: number | null | undefined) =>
    value == null ? 'Não informado' : formatNumber(value)
  const configured = data?.eleicao_configurada ?? data?.eleicao
  const dates =
    data?.datas_disponiveis ??
    (data ? [{ data: data.eleicao.data, boletins: data.boletins }] : [])
  const otherDates = dates.filter(
    (entry) => entry.data !== data?.eleicao.data && entry.boletins > 0,
  )
  const outsideCount = otherDates.reduce(
    (total, entry) => total + entry.boletins,
    0,
  )
  const isConfigured = data?.eleicao.data === configured?.data

  return (
    <div className="overview">
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            {data
              ? `ACOMPANHAMENTO / ${data.eleicao.ano} / ${data.eleicao.turno}º TURNO`
              : 'ACOMPANHAMENTO'}
          </span>
          <h1>
            Bacabal <span className="muted">/ MA</span>
          </h1>
          <p>Parcial dos boletins importados</p>
        </div>
        <button
          className="icon-button"
          title="Atualizar acompanhamento"
          aria-label="Atualizar acompanhamento"
          disabled={loading}
          onClick={refresh}
        >
          <RotateCw size={18} className={loading ? 'spin' : ''} />
        </button>
      </div>
      <div className="overview-filters overview-election">
        <label>
          Data da eleição
          <select
            aria-label="Data da eleição"
            disabled={!data}
            value={data?.eleicao.data ?? ''}
            onChange={(e) => onDateChange(e.target.value)}
          >
            {!data && <option value="">Consultando...</option>}
            {dates.map((entry) => (
              <option key={entry.data} value={entry.data}>
                {formatDate(entry.data)}
                {entry.data === configured?.data
                  ? ' · Configurada'
                  : ` · ${entry.boletins} ${entry.boletins === 1 ? 'boletim' : 'boletins'}`}
              </option>
            ))}
          </select>
        </label>
        {data && !isConfigured && configured && (
          <p className="overview-date-scope">
            Consulta de {formatDate(data.eleicao.data)}
            <Link to="/acompanhamento">
              Voltar a {formatDate(configured.data)}
            </Link>
          </p>
        )}
      </div>
      <div className="overview-status" role="status">
        <span>
          {error
            ? 'Atualização indisponível'
            : loading
              ? 'Consultando boletins...'
              : 'Conectado'}
        </span>
        {data && (
          <span>
            Última consulta:{' '}
            {new Date(data.consultado_em).toLocaleTimeString('pt-BR')}
          </span>
        )}
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}{' '}
          {data && 'Os dados exibidos são da última consulta bem-sucedida.'}
        </div>
      )}
      {data && (
        <>
          {outsideCount > 0 && (
            <div className="notice warning overview-date-notice" role="status">
              <CalendarDays size={20} aria-hidden="true" />
              <div>
                <strong>
                  {outsideCount}{' '}
                  {outsideCount === 1
                    ? 'boletim salvo em outra data'
                    : 'boletins salvos em outras datas'}
                </strong>
                <p>Fora dos totais de {formatDate(data.eleicao.data)}.</p>
                <ul>
                  {otherDates.map((entry) => (
                    <li key={entry.data}>
                      <Link
                        to={`/acompanhamento?data=${entry.data}`}
                        aria-label={`Ver boletins de ${formatDate(entry.data)}`}
                      >
                        {formatDate(entry.data)}: {entry.boletins}{' '}
                        {entry.boletins === 1 ? 'boletim' : 'boletins'}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
          <dl className="overview-metrics">
            <div>
              <dt>Boletins salvos</dt>
              <dd>{count(data.boletins)}</dd>
            </div>
            <div>
              <dt>Seções principais apuradas</dt>
              <dd>{count(data.secoes_principais_apuradas)}</dd>
            </div>
            <div>
              <dt>Seções principais esperadas</dt>
              <dd className="unknown">
                {count(data.secoes_principais_esperadas)}
              </dd>
            </div>
            <div>
              <dt>Seções principais pendentes</dt>
              <dd className="unknown">
                {count(data.secoes_principais_pendentes)}
              </dd>
            </div>
          </dl>
          <VotosCandidato data={data} refreshVersion={refreshVersion} />
          <SecoesPendentes
            groups={data.grupos_secoes ?? []}
            registered={data.lista_secoes_importada ?? false}
            onSaved={refresh}
            allowImport={isConfigured}
          />
        </>
      )}
    </div>
  )
}
