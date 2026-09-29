import { useRef, useState } from 'react'
import { FileUp, Upload } from 'lucide-react'

export function PdfUpload({ onFile }: { onFile: (file: File) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')

  function select(files: FileList | null) {
    setError('')
    if (!files?.length) return
    if (files.length !== 1)
      return setError('Selecione apenas um PDF por importação.')
    const file = files[0]
    if (
      !file.name.toLowerCase().endsWith('.pdf') ||
      file.type !== 'application/pdf'
    ) {
      return setError('Selecione um arquivo PDF válido.')
    }
    onFile(file)
  }

  return (
    <>
      <div
        className={`upload-zone ${dragging ? 'dragging' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node))
            setDragging(false)
        }}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          select(e.dataTransfer.files)
        }}
      >
        <FileUp className="upload-icon" size={44} strokeWidth={1.5} />
        <h2>Arraste seu PDF até aqui</h2>
        <span className="muted">ou selecione o arquivo no seu dispositivo</span>
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          aria-label="Arquivo PDF"
          hidden
          onChange={(e) => {
            select(e.target.files)
            e.target.value = ''
          }}
        />
        <button
          className="button primary"
          onClick={() => input.current?.click()}
        >
          <Upload size={17} /> Selecionar PDF
        </button>
        <span className="file-type">PDF · Boletim na Mão</span>
      </div>
      {error && (
        <div role="alert" className="notice error">
          {error}
        </div>
      )}
    </>
  )
}
