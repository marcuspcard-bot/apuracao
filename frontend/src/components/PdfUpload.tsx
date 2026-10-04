import { useRef, useState } from 'react'
import { FileUp, Upload } from 'lucide-react'

export function PdfUpload({
  onFiles,
  maxFiles = 10,
}: {
  onFiles: (files: File[]) => void
  maxFiles?: number
}) {
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')

  function select(files: FileList | null) {
    setError('')
    if (!files?.length) return
    if (files.length > maxFiles)
      return setError(
        `Selecione até ${maxFiles} PDF${maxFiles === 1 ? '' : 's'} por importação.`,
      )
    const selected = Array.from(files)
    if (
      selected.some(
        (file) =>
          !file.name.toLowerCase().endsWith('.pdf') ||
          file.type !== 'application/pdf',
      )
    ) {
      return setError('Selecione um arquivo PDF válido.')
    }
    onFiles(selected)
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
        <h2>
          {maxFiles === 1
            ? 'Arraste seu PDF até aqui'
            : 'Arraste até 10 PDFs até aqui'}
        </h2>
        <span className="muted">
          ou selecione os arquivos no seu dispositivo
        </span>
        <input
          ref={input}
          type="file"
          multiple={maxFiles > 1}
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
