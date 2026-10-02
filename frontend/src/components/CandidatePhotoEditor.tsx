import { useEffect, useRef } from 'react'
import { Camera, X } from 'lucide-react'
import { CandidatePhoto } from './CandidatePhoto'
import type { ScreenSelection } from '../types/telao'

export function CandidatePhotoEditor({
  candidate,
  disabled,
  onChange,
  onError,
  onBusy,
}: {
  candidate: ScreenSelection
  disabled: boolean
  onChange: (photo: string | null) => void
  onError: (message: string) => void
  onBusy: (value: boolean) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const reader = useRef<FileReader | null>(null)
  useEffect(() => () => reader.current?.abort(), [])
  const photo =
    candidate.foto !== undefined ? candidate.foto : candidate.foto_url

  function select(file?: File) {
    if (!file) return
    if (
      !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) ||
      file.size > 2 * 1024 * 1024
    ) {
      onError('Envie uma foto JPG, PNG ou WebP de até 2 MB.')
      return
    }
    const next = new FileReader()
    reader.current = next
    onBusy(true)
    next.onload = () => onChange(String(next.result))
    next.onerror = () =>
      onError('Não foi possível abrir a foto. Escolha o arquivo novamente.')
    next.onloadend = () => onBusy(false)
    next.readAsDataURL(file)
  }

  return (
    <div className="candidate-photo-editor">
      <button
        type="button"
        className="candidate-photo-picker"
        disabled={disabled}
        title={photo ? 'Substituir foto' : 'Adicionar foto'}
        aria-label={`${photo ? 'Substituir' : 'Adicionar'} foto de ${candidate.nome}`}
        onClick={() => input.current?.click()}
      >
        <CandidatePhoto source={photo} name={candidate.nome} />
        <span className="photo-camera">
          <Camera size={14} />
        </span>
      </button>
      <input
        ref={input}
        type="file"
        hidden
        accept="image/jpeg,image/png,image/webp"
        aria-label={`Foto de ${candidate.nome}`}
        disabled={disabled}
        onChange={(event) => {
          select(event.target.files?.[0])
          event.target.value = ''
        }}
      />
      {photo && (
        <button
          type="button"
          className="icon-button remove-photo"
          disabled={disabled}
          title="Remover foto"
          aria-label={`Remover foto de ${candidate.nome}`}
          onClick={() => onChange(null)}
        >
          <X size={14} />
        </button>
      )}
    </div>
  )
}
