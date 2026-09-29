import type { Cargo, ResultadoDados } from '../types/boletim'
import { formatNumber } from '../services/api'

export function ResultadosTable({ cargo }: { cargo: Cargo }) {
  const hasOverall =
    cargo.candidatos.length > 0 ||
    [
      cargo.votos_nominais,
      cargo.brancos,
      cargo.nulos,
      cargo.total_apurado,
    ].some((value) => value !== null)
  return (
    <section className="results-section" aria-label={cargo.nome}>
      <div className="section-heading">
        <h2>{cargo.nome}</h2>
        <span className="muted">
          {cargo.vagas.length
            ? `${cargo.vagas.length} vagas`
            : `${cargo.candidatos.length} candidatos`}
        </span>
      </div>
      {(!cargo.vagas.length || hasOverall) && (
        <ResultadoContent resultado={cargo} />
      )}
      {cargo.vagas.map((vaga) => (
        <section
          className="seat-result"
          key={vaga.identificacao}
          aria-label={`${cargo.nome} / ${vaga.identificacao}`}
        >
          <h3>{vaga.identificacao}</h3>
          <ResultadoContent resultado={vaga} />
        </section>
      ))}
    </section>
  )
}

function ResultadoContent({ resultado: cargo }: { resultado: ResultadoDados }) {
  return (
    <>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th className="number-column">Número</th>
              <th>Candidato</th>
              <th className="numeric">Votos</th>
            </tr>
          </thead>
          <tbody>
            {cargo.candidatos.map((c) => (
              <tr key={c.numero}>
                <td className="code">{c.numero}</td>
                <td>{c.nome}</td>
                <td className="numeric vote">{formatNumber(c.votos)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="totals">
        <div>
          <dt>Votos nominais</dt>
          <dd>{formatNumber(cargo.votos_nominais)}</dd>
        </div>
        <div>
          <dt>Votos de legenda</dt>
          <dd>{formatNumber(cargo.votos_legenda)}</dd>
        </div>
        <div>
          <dt>Brancos</dt>
          <dd>{formatNumber(cargo.brancos)}</dd>
        </div>
        <div>
          <dt>Nulos</dt>
          <dd>{formatNumber(cargo.nulos)}</dd>
        </div>
        <div className="total-highlight">
          <dt>Total apurado</dt>
          <dd>{formatNumber(cargo.total_apurado)}</dd>
        </div>
      </dl>
    </>
  )
}
