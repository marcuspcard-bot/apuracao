import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { BoletimPreview } from './BoletimPreview'
import { useImportacao } from '../hooks/useImportacao'

let batchQueue = Promise.resolve()
function enqueue(task: () => Promise<void>) {
  const result = batchQueue.then(task)
  batchQueue = result.catch(() => {})
  return result
}
type Status = { ready: boolean; busy: boolean; saved: boolean }
function BatchItem({
  file,
  request,
  report,
}: {
  file: File
  request: number
  report: (s: Status) => void
}) {
  const item = useImportacao()
  const [queued, setQueued] = useState(true)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  async function run(task: () => Promise<void>) {
    setQueued(true)
    try {
      await enqueue(async () => {
        if (mounted.current) await task()
      })
    } finally {
      if (mounted.current) setQueued(false)
    }
  }
  const upload = useRef(item.upload)
  const started = useRef(false)
  const lastRequest = useRef(0)
  const ready =
    !!item.preview &&
    item.preview.status === 'OK' &&
    !item.expired &&
    !item.saved &&
    !item.uncertain
  useEffect(() => {
    if (started.current) return
    started.current = true
    void run(() => upload.current(file))
  }, [file])
  useEffect(() => {
    report({
      ready,
      busy: queued || item.loading || item.saving,
      saved: !!item.saved,
    })
  }, [ready, queued, item.loading, item.saving, item.saved, report])
  useEffect(() => {
    if (request === lastRequest.current) return
    lastRequest.current = request
    if (ready) void run(() => item.save())
  }, [request, ready, item.save])
  return (
    <section className="document-section">
      <h2>{file.name}</h2>
      {queued && !item.loading && !item.saving && (
        <p role="status">Aguardando processamento...</p>
      )}
      {item.loading && <p role="status">Lendo e analisando boletim...</p>}
      {item.error && (
        <div className="notice error" role="alert">
          {item.error}
        </div>
      )}
      {item.saved && (
        <div className="notice success" role="status">
          Boletim salvo com sucesso.{' '}
          <Link to={`/boletins/${item.saved}`}>Ver boletim</Link>
        </div>
      )}
      {item.preview && (
        <>
          <p>
            {item.preview.dados.municipio.nome} / Zona {item.preview.dados.zona}{' '}
            / Seção {item.preview.dados.secao}
          </p>
          <a
            className="button"
            href={item.pdfUrl}
            target="_blank"
            rel="noreferrer"
          >
            Conferir PDF
          </a>
          {item.preview.status === 'OK' ? (
            <p>Dados validados.</p>
          ) : (
            <div className="notice error" role="alert">
              <div>
                Este boletim possui inconsistências e não poderá ser salvo.
                <ul>
                  {item.preview.problemas.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
          <details>
            <summary>Conferir dados do boletim</summary>
            <BoletimPreview dados={item.preview.dados} />
          </details>
          {item.expired && (
            <p role="alert">Prévia expirada. Envie o PDF novamente.</p>
          )}
          <button
            className="button primary"
            disabled={!ready || queued || item.saving}
            onClick={() => void run(() => item.save())}
          >
            {item.saving ? 'Salvando...' : 'Salvar boletim'}
          </button>
          {item.uncertain && (
            <button
              className="button"
              disabled={queued || item.saving}
              onClick={() => void run(() => item.save(true))}
            >
              Verificar salvamento
            </button>
          )}
        </>
      )}
      {!queued && !item.loading && !item.saving && !item.saved && (
        <button
          className="button"
          onClick={() => void run(() => item.upload(file))}
        >
          Ler PDF novamente
        </button>
      )}
    </section>
  )
}
export function BatchImport({
  files,
  onReset,
}: {
  files: File[]
  onReset: () => void
}) {
  const [statuses, setStatuses] = useState<Status[]>(() =>
    files.map(() => ({ ready: false, busy: true, saved: false })),
  )
  const [request, setRequest] = useState(0)
  const [callbacks] = useState(() =>
    files.map(
      (_, index) => (status: Status) =>
        setStatuses((current) =>
          current.map((entry, i) => (i === index ? status : entry)),
        ),
    ),
  )
  const busy = statuses.some((s) => s.busy)
  const ready = statuses.filter((s) => s.ready).length
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">IMPORTAÇÃO</span>
          <h1>Importar Boletins de Urna</h1>
          <p>
            {files.length} PDFs selecionados. Confira os dados antes de salvar.
          </p>
        </div>
      </div>
      <div className="save-bar">
        <span role="status">
          {statuses.filter((s) => s.saved).length} de {files.length} boletins
          salvos · {ready} prontos para salvar
        </span>
        <div>
          <button className="button" disabled={busy} onClick={onReset}>
            Nova importação
          </button>
          <button
            className="button primary"
            disabled={busy || !ready}
            onClick={() => setRequest((n) => n + 1)}
          >
            Salvar todos os boletins válidos
          </button>
        </div>
      </div>
      {files.map((file, index) => (
        <BatchItem
          key={index}
          file={file}
          request={request}
          report={callbacks[index]}
        />
      ))}
    </>
  )
}
