import { useEffect, useState } from 'react'
import { api, errorMessage, formatDate, getOverview } from '../services/api'

type Report = {
  cargos: { nome: string; candidatos: { numero: string; nome: string }[] }[]
  linhas: {
    zona: string
    secao: string
    agregadas: string[]
    cargos: Record<string, Record<string, number>>
  }[]
}

export function Relatorios() {
  const [dates, setDates] = useState<string[]>([])
  const [date, setDate] = useState('')
  const [report, setReport] = useState<Report | null>(null)
  const [office, setOffice] = useState('')
  const [selected, setSelected] = useState<{ cargo: string; numero: string }[]>(
    [],
  )
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    getOverview(controller.signal)
      .then((data) => {
        setDates(data.datas_disponiveis.map((d) => d.data))
        setDate(data.eleicao.data)
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setError(errorMessage(e))
          setLoading(false)
        }
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!date) return
    const controller = new AbortController()
    setLoading(true)
    setError('')
    setReport(null)
    setSelected([])
    api
      .get<Report>('/api/acompanhamento/relatorio', {
        params: { data: date },
        signal: controller.signal,
      })
      .then(({ data }) => {
        setReport(data)
        setOffice(data.cargos[0]?.nome ?? '')
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [date])

  const candidates =
    report?.cargos.find((c) => c.nome === office)?.candidatos ?? []
  const chosen = selected.flatMap((selection) => {
    const candidate = report?.cargos
      .find((c) => c.nome === selection.cargo)
      ?.candidatos.find((c) => c.numero === selection.numero)
    return candidate ? [{ ...candidate, cargo: selection.cargo }] : []
  })
  const rows =
    report?.linhas.filter((row) => chosen.some((c) => c.cargo in row.cargos)) ??
    []

  async function download() {
    setExporting(true)
    setError('')
    try {
      const response = await api.post(
        '/api/acompanhamento/relatorio.csv',
        {
          data: date,
          candidatos: chosen.map((c) => ({ cargo: c.cargo, numero: c.numero })),
        },
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(response.data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `relatorio-${date}.csv`
      anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="overview">
      <div className="page-heading">
        <div>
          <span className="eyebrow">RELATÓRIOS</span>
          <h1>Votação por seção</h1>
          <p>
            Selecione os candidatos para exportar a votação das seções apuradas.
          </p>
        </div>
      </div>
      <div className="overview-filters">
        <label>
          Data da eleição
          <select
            value={date}
            disabled={exporting || !dates.length}
            onChange={(e) => setDate(e.target.value)}
          >
            {dates.map((d) => (
              <option key={d} value={d}>
                {formatDate(d)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Cargo
          <select
            value={office}
            disabled={loading || exporting || !report?.cargos.length}
            onChange={(e) => {
              setOffice(e.target.value)
              setSearch('')
            }}
          >
            {report?.cargos.map((c) => (
              <option key={c.nome}>{c.nome}</option>
            ))}
          </select>
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      {loading && <p role="status">Carregando seções apuradas...</p>}
      {!loading && report && !report.cargos.length && (
        <p>Nenhum boletim completo disponível nesta eleição.</p>
      )}
      {!loading && !!candidates.length && (
        <>
          <label>
            Buscar candidato
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Nome ou número"
            />
          </label>
          <fieldset className="report-candidates" disabled={exporting}>
            <legend>Candidatos ({selected.length} selecionados)</legend>
            {candidates
              .filter((c) =>
                `${c.nome} ${c.numero}`
                  .toLocaleLowerCase()
                  .includes(search.toLocaleLowerCase()),
              )
              .map((c) => (
                <label key={c.numero}>
                  <input
                    type="checkbox"
                    checked={selected.some(
                      (s) => s.cargo === office && s.numero === c.numero,
                    )}
                    onChange={(e) =>
                      setSelected((current) =>
                        e.target.checked
                          ? [...current, { cargo: office, numero: c.numero }]
                          : current.filter(
                              (s) =>
                                !(s.cargo === office && s.numero === c.numero),
                            ),
                      )
                    }
                  />
                  {c.numero} — {c.nome}
                </label>
              ))}
          </fieldset>
          {!!chosen.length && (
            <div
              className="report-candidates"
              aria-label="Candidatos selecionados"
            >
              <strong>Selecionados para o relatório</strong>
              {chosen.map((c) => (
                <div key={`${c.cargo}-${c.numero}`}>
                  {c.cargo} — {c.nome} — {c.numero}{' '}
                  <button
                    disabled={exporting}
                    onClick={() =>
                      setSelected((current) =>
                        current.filter(
                          (s) =>
                            !(s.cargo === c.cargo && s.numero === c.numero),
                        ),
                      )
                    }
                    aria-label={`Remover ${c.nome} de ${c.cargo}`}
                  >
                    Remover
                  </button>
                </div>
              ))}
            </div>
          )}
          <p>
            Troque o cargo para adicionar mais candidatos. Suas escolhas serão
            mantidas.
          </p>
          <p>
            Somente boletins completos. Seções agregadas compartilham a votação
            da principal.
          </p>
          <button
            className="button"
            disabled={!chosen.length || !rows.length || exporting}
            onClick={download}
          >
            {exporting ? 'Exportando...' : 'Exportar CSV'}
          </button>
          {!!chosen.length && (
            <>
              <p>{rows.length} grupos de seções apurados.</p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Zona</th>
                      <th>Seção principal</th>
                      <th>Seções agregadas</th>
                      {chosen.map((c) => (
                        <th key={`${c.cargo}-${c.numero}`}>
                          {c.cargo} — {c.nome} — {c.numero}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={`${row.zona}-${row.secao}`}>
                        <td>{row.zona}</td>
                        <td>{row.secao}</td>
                        <td>{row.agregadas.join(', ') || '—'}</td>
                        {chosen.map((c) => (
                          <td key={`${c.cargo}-${c.numero}`}>
                            {c.cargo in row.cargos
                              ? (row.cargos[c.cargo][c.numero] ?? 0)
                              : '—'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
