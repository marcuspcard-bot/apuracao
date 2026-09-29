import { Link } from 'react-router-dom'
import {
  Check,
  CheckCircle2,
  CircleAlert,
  FileText,
  LoaderCircle,
  Save,
  X,
  ExternalLink,
  SearchCheck,
} from 'lucide-react'
import { PdfUpload } from '../components/PdfUpload'
import { BoletimPreview } from '../components/BoletimPreview'
import { useImportacao } from '../hooks/useImportacao'

export function Importar() {
  const {
    preview,
    loading,
    saving,
    error,
    saved,
    pdfUrl,
    expired,
    uncertain,
    reset,
    upload,
    save,
  } = useImportacao()
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">IMPORTAÇÃO</span>
          <h1>Importar Boletim de Urna</h1>
          <p>Envie o PDF gerado pelo aplicativo Boletim na Mão.</p>
        </div>
        <span className="edition">BU / 01</span>
      </div>
      <ol className="steps" aria-label="Etapas da importação">
        {['Enviar PDF', 'Conferir dados', 'Salvar boletim'].map((step, i) => (
          <li
            key={step}
            className={(preview ? i <= 1 : i === 0) ? 'active' : ''}
          >
            <span className="step-number">
              {preview && i === 0 ? <Check size={15} /> : i + 1}
            </span>
            {step}
          </li>
        ))}
      </ol>
      {saved && (
        <div className="notice success" role="status">
          <CheckCircle2 size={20} />
          <div>
            Boletim salvo com sucesso.{' '}
            <Link to={`/boletins/${saved}`}>Ver boletim</Link>
          </div>
        </div>
      )}
      {error && (
        <div className="notice error" role="alert">
          <CircleAlert size={20} />
          <span>{error}</span>
        </div>
      )}
      {loading ? (
        <div className="loading-area" role="status">
          <LoaderCircle className="spin" size={30} />
          <h2>Lendo e analisando boletim...</h2>
          <button className="button" onClick={reset}>
            <X size={16} />
            Cancelar
          </button>
        </div>
      ) : !preview ? (
        <div className="import-layout">
          <div>
            <div className="section-heading">
              <h2>Arquivo do boletim</h2>
              <span className="muted">01</span>
            </div>
            <PdfUpload onFile={upload} />
          </div>
          <aside className="reference">
            <img
              src="/boletim-referencia.jpeg"
              alt="Exemplo de Boletim de Urna com identificação da seção e votos por candidato"
            />
            <span className="eyebrow">DOCUMENTO DE REFERÊNCIA</span>
            <h2>Boletim de Urna</h2>
            <p className="muted">Justiça Eleitoral · Via digital</p>
            <dl>
              <div>
                <dt>Origem</dt>
                <dd>Boletim na Mão</dd>
              </div>
              <div>
                <dt>Formato</dt>
                <dd>PDF com texto digital</dd>
              </div>
            </dl>
          </aside>
        </div>
      ) : (
        <>
          <div className="preview-heading">
            <div>
              <span className="eyebrow">BOLETIM IDENTIFICADO</span>
              <h2>
                {preview.dados.municipio.nome}{' '}
                <span className="muted">/ Seção {preview.dados.secao}</span>
              </h2>
            </div>
            <a
              className="button"
              href={pdfUrl}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={16} />
              Conferir PDF
            </a>
          </div>
          <div className="file-bar">
            <FileText size={18} />
            <span>{preview.arquivo_nome}</span>
          </div>
          {preview.status === 'OK' ? (
            <div className="notice success" role="status">
              <CheckCircle2 size={20} />
              <span>Dados validados.</span>
            </div>
          ) : (
            <div className="notice error" role="alert">
              <CircleAlert size={20} />
              <div>
                <strong>
                  Este boletim possui inconsistências e não poderá ser salvo.
                </strong>
                <ul>
                  {preview.problemas.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
          <BoletimPreview dados={preview.dados} />
          <div className="save-bar">
            <span className="muted">
              {expired
                ? 'Prévia expirada. Envie o PDF novamente.'
                : 'Conferência do boletim'}
            </span>
            <div>
              {uncertain && (
                <button
                  className="button"
                  disabled={saving}
                  onClick={() => void save(true)}
                >
                  <SearchCheck size={17} />
                  Verificar salvamento
                </button>
              )}
              <button className="button" disabled={saving} onClick={reset}>
                <X size={17} />
                Cancelar
              </button>
              <button
                className="button primary"
                disabled={saving || preview.status !== 'OK' || !!expired}
                onClick={() => void save()}
              >
                {saving ? (
                  <LoaderCircle className="spin" size={17} />
                ) : (
                  <Save size={17} />
                )}
                {saving ? 'Salvando...' : 'Salvar boletim'}
              </button>
            </div>
          </div>
        </>
      )}
    </>
  )
}
