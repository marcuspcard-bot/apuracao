import type { BoletimDados } from '../types/boletim'
import { ResultadosTable } from './ResultadosTable'
import { formatDate, formatNumber } from '../services/api'

export function BoletimPreview({
  dados: d,
  parcial = false,
}: {
  dados: BoletimDados
  parcial?: boolean
}) {
  return (
    <div className="boletim-data">
      <section className="general-section">
        <div className="section-heading">
          <h2>Dados do boletim</h2>
          <span className="tag">{d.eleicao.turno}º turno</span>
        </div>
        <dl className="data-grid">
          <div className="wide-field">
            <dt>Eleição</dt>
            <dd>{d.eleicao.descricao}</dd>
          </div>
          <div>
            <dt>Data da eleição</dt>
            <dd>{formatDate(d.eleicao.data)}</dd>
          </div>
          <div className="wide-field">
            <dt>Município</dt>
            <dd>{d.municipio.nome}</dd>
          </div>
          <div>
            <dt>Código do município</dt>
            <dd className="code">{d.municipio.codigo}</dd>
          </div>
          <div>
            <dt>Zona</dt>
            <dd className="code">{d.zona}</dd>
          </div>
          <div>
            <dt>Local de votação</dt>
            <dd className="code">{d.local_votacao ?? 'Não informado'}</dd>
          </div>
          <div>
            <dt>
              {d.quantidade_secoes_agregadas > 0 ? 'Seção principal' : 'Seção'}
            </dt>
            <dd className="code">{d.secao}</dd>
          </div>
          <div>
            <dt>Total de seções representadas</dt>
            <dd>{d.total_secoes_representadas}</dd>
          </div>
        </dl>
        <div className="aggregated">
          <span className="muted">
            Seções agregadas ({d.quantidade_secoes_agregadas})
          </span>
          <div>
            {d.secoes_agregadas.length ? (
              d.secoes_agregadas.map((s) => (
                <span key={s} className="section-code code">
                  {s}
                </span>
              ))
            ) : (
              <span>Nenhuma</span>
            )}
          </div>
        </div>
        <dl className="electors">
          <div>
            <dt>Eleitores aptos</dt>
            <dd>{formatNumber(d.eleitores.aptos)}</dd>
          </div>
          <div>
            <dt>Comparecimento</dt>
            <dd>{formatNumber(d.eleitores.comparecimento)}</dd>
          </div>
          <div>
            <dt>Faltosos</dt>
            <dd>{formatNumber(d.eleitores.faltosos)}</dd>
          </div>
        </dl>
      </section>
      {d.cargos.map((c) => (
        <ResultadosTable key={c.nome} cargo={c} />
      ))}
      {!parcial && (
        <section className="machine-section">
          <h2>Dados da urna</h2>
          <dl className="data-grid">
            <div>
              <dt>Identificação UE</dt>
              <dd className="code">{d.urna.codigo_identificacao}</dd>
            </div>
            <div>
              <dt>Abertura</dt>
              <dd>
                {formatDate(d.urna.data_abertura)}
                <small>{d.urna.hora_abertura}</small>
              </dd>
            </div>
            <div>
              <dt>Fechamento</dt>
              <dd>
                {formatDate(d.urna.data_fechamento)}
                <small>{d.urna.hora_fechamento}</small>
              </dd>
            </div>
          </dl>
          <dl className="technical-data">
            <div>
              <dt>Código de identificação da carga</dt>
              <dd className="code">{d.codigo_carga}</dd>
            </div>
            <div>
              <dt>Assinatura QR Code</dt>
              <dd className="code hash">{d.assinatura_qrcode}</dd>
            </div>
          </dl>
        </section>
      )}
    </div>
  )
}
