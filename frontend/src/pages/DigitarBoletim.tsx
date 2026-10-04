import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../services/api'

const offices = [
  'DEPUTADO FEDERAL',
  'DEPUTADO ESTADUAL',
  'DEPUTADO DISTRITAL',
  'SENADOR',
  'GOVERNADOR',
  'PRESIDENTE',
]
const emptyCandidate = () => ({
  cargo: offices[0],
  numero: '',
  nome: '',
  votos: '',
})

export function DigitarBoletim() {
  const navigate = useNavigate()
  const [identity, setIdentity] = useState({
    data: '2026-10-04',
    turno: '1',
    descricao: 'Eleições Gerais 2026',
    municipio: 'Bacabal',
    codigo: '07234',
    zona: '',
    secao: '',
    agregadas: '',
  })
  const [candidates, setCandidates] = useState([emptyCandidate()])
  const [photos, setPhotos] = useState<File[]>([])
  const [photoUrls, setPhotoUrls] = useState<string[]>([])
  const [reading, setReading] = useState(false)
  const [photoText, setPhotoText] = useState('')
  const [review, setReview] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    const urls = photos.map((p) => URL.createObjectURL(p))
    setPhotoUrls(urls)
    return () => urls.forEach((url) => URL.revokeObjectURL(url))
  }, [photos])
  function prepare(event: FormEvent) {
    event.preventDefault()
    setError('')
    const included = candidates.filter((c) => c.votos !== '')
    if (!included.length) {
      setError('Informe os votos de pelo menos um candidato.')
      return
    }
    const keys = included.map((c) => `${c.cargo}:${Number(c.numero)}`)
    if (new Set(keys).size !== keys.length) {
      setError('Há candidato repetido no mesmo cargo.')
      return
    }
    const sections = [
      identity.secao,
      ...identity.agregadas.split(/[\s,;]+/).filter(Boolean),
    ]
    if (
      sections.some((s) => !/^\d{1,20}$/.test(s)) ||
      new Set(sections.map((s) => Number(s))).size !== sections.length
    ) {
      setError('Confira os números das seções. Não pode haver repetição.')
      return
    }
    setReview(true)
  }
  async function readPhotos() {
    if (!photos.length || reading) return
    setReading(true)
    setError('')
    setPhotoText('')
    try {
      const form = new FormData()
      photos.forEach((photo) => form.append('files', photo))
      const prepared = await api.post('/api/boletins/fotos/preview', form)
      const result = await api.post('/api/boletins/fotos/ler', {
        foto_token: prepared.data.foto_token,
      })
      setPhotoText(
        result.data.texto ||
          'Nenhum texto identificado. Confira a foto e continue pela digitação manual.',
      )
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setReading(false)
    }
  }
  async function save() {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      let foto_token: string | undefined
      if (photos.length) {
        const form = new FormData()
        photos.forEach((photo) => form.append('files', photo))
        foto_token = (await api.post('/api/boletins/fotos/preview', form)).data
          .foto_token
      }
      const result = await api.post('/api/boletins/manual/confirmar', {
        eleicao: {
          descricao: identity.descricao,
          data: identity.data,
          turno: Number(identity.turno),
        },
        municipio: { codigo: identity.codigo, nome: identity.municipio },
        zona: identity.zona,
        secao: identity.secao,
        secoes_agregadas: identity.agregadas.split(/[\s,;]+/).filter(Boolean),
        candidatos: candidates
          .filter((c) => c.votos !== '')
          .map((c) => ({ ...c, nome: c.nome.trim(), votos: Number(c.votos) })),
        foto_token,
      })
      navigate(`/boletins/${result.data.id}`)
    } catch (e) {
      setError(
        errorMessage(e) +
          ' Se houve perda de conexão, consulte a listagem antes de tentar novamente.',
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">CONTINGÊNCIA</span>
          <h1>Digitar votos do BU</h1>
          <p>Registre somente os candidatos que deseja acompanhar.</p>
        </div>
        <Link className="button" to="/importar">
          Importar PDF
        </Link>
      </div>
      <div className="notice">
        Lançamento manual — parcial. Campo de votos vazio significa não
        informado. Digite 0 apenas quando o boletim mostrar zero.
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {review ? (
        <section className="document-section">
          <h2>Confira com o boletim antes de salvar</h2>
          <p>
            {identity.descricao} · {identity.data} · {identity.turno}º turno
          </p>
          <p>
            {identity.municipio} ({identity.codigo}) · Zona {identity.zona} ·
            Seção {identity.secao}
          </p>
          <p>
            Agregadas: {identity.agregadas || 'Nenhuma'} · Fotos:{' '}
            {photos.length}
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Cargo</th>
                  <th>Número</th>
                  <th>Candidato</th>
                  <th>Votos</th>
                </tr>
              </thead>
              <tbody>
                {candidates
                  .filter((c) => c.votos !== '')
                  .map((c, i) => (
                    <tr key={i}>
                      <td>{c.cargo}</td>
                      <td>{c.numero}</td>
                      <td>{c.nome}</td>
                      <td>{c.votos}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <div className="save-bar">
            <button
              className="button"
              disabled={busy}
              onClick={() => setReview(false)}
            >
              Voltar e corrigir
            </button>
            <button
              className="button primary"
              disabled={busy}
              onClick={() => void save()}
            >
              {busy ? 'Salvando...' : 'Confirmar lançamento parcial'}
            </button>
          </div>
        </section>
      ) : (
        <form onSubmit={prepare} className="manual-form">
          <fieldset>
            <legend>Identificação do boletim</legend>
            <div className="manual-grid">
              {(
                [
                  ['descricao', 'Eleição', 'text'],
                  ['data', 'Data da eleição', 'date'],
                  ['municipio', 'Município', 'text'],
                  ['codigo', 'Código TSE do município', 'text'],
                  ['zona', 'Zona', 'text'],
                  ['secao', 'Seção principal', 'text'],
                ] as const
              ).map(([key, label, type]) => (
                <label key={key}>
                  {label}
                  <input
                    required
                    type={type}
                    value={identity[key]}
                    maxLength={
                      ['codigo', 'zona', 'secao'].includes(key) ? 20 : 200
                    }
                    pattern={
                      ['codigo', 'zona', 'secao'].includes(key)
                        ? '[0-9]{1,20}'
                        : undefined
                    }
                    onChange={(e) =>
                      setIdentity({ ...identity, [key]: e.target.value })
                    }
                  />
                </label>
              ))}
              <label>
                Turno
                <select
                  value={identity.turno}
                  onChange={(e) =>
                    setIdentity({ ...identity, turno: e.target.value })
                  }
                >
                  <option value="1">1º turno</option>
                  <option value="2">2º turno</option>
                </select>
              </label>
              <label>
                Seções agregadas (se houver)
                <input
                  placeholder="Separe por vírgulas"
                  value={identity.agregadas}
                  onChange={(e) =>
                    setIdentity({ ...identity, agregadas: e.target.value })
                  }
                />
              </label>
            </div>
            <p className="muted">
              Transcreva a seção principal e todas as agregadas impressas no BU.
              Os votos pertencem ao conjunto.
            </p>
          </fieldset>
          <fieldset>
            <legend>Candidatos de interesse</legend>
            {candidates.map((c, i) => (
              <div className="manual-candidate" key={i}>
                <label>
                  Cargo
                  <select
                    aria-label={`Cargo do candidato ${i + 1}`}
                    value={c.cargo}
                    onChange={(e) =>
                      setCandidates(
                        candidates.map((v, n) =>
                          n === i ? { ...v, cargo: e.target.value } : v,
                        ),
                      )
                    }
                  >
                    {offices.map((o) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                </label>
                {(['numero', 'nome', 'votos'] as const).map((key) => (
                  <label key={key}>
                    {key === 'numero'
                      ? 'Número'
                      : key === 'nome'
                        ? 'Nome'
                        : 'Votos'}
                    <input
                      aria-label={`${key === 'numero' ? 'Número' : key === 'nome' ? 'Nome' : 'Votos'} do candidato ${i + 1}`}
                      required={key !== 'votos' && c.votos !== ''}
                      type={key === 'votos' ? 'number' : 'text'}
                      min={0}
                      max={10000000}
                      step={1}
                      maxLength={key === 'nome' ? 200 : 20}
                      pattern={key === 'numero' ? '[0-9]{1,20}' : undefined}
                      value={c[key]}
                      placeholder={
                        key === 'votos' ? 'Não informado' : undefined
                      }
                      onChange={(e) =>
                        setCandidates(
                          candidates.map((v, n) =>
                            n === i ? { ...v, [key]: e.target.value } : v,
                          ),
                        )
                      }
                    />
                  </label>
                ))}
                <button
                  type="button"
                  className="button"
                  disabled={candidates.length === 1}
                  onClick={() =>
                    setCandidates(candidates.filter((_, n) => n !== i))
                  }
                >
                  Remover
                </button>
              </div>
            ))}
            <button
              className="button"
              type="button"
              disabled={candidates.length >= 200}
              onClick={() => setCandidates([...candidates, emptyCandidate()])}
            >
              Adicionar candidato
            </button>
          </fieldset>
          <fieldset>
            <legend>Fotos do BU (opcional)</legend>
            <p>
              Anexe até 10 fotos legíveis, na ordem do boletim. Elas serão
              guardadas em um PDF para conferência. Os votos devem ser digitados
              acima. Você também pode tentar reconhecer o texto das fotos e
              conferir os números antes de preencher.
            </p>
            <input
              disabled={reading}
              aria-label="Fotos do BU"
              type="file"
              multiple
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => {
                const files = Array.from(e.target.files || [])
                if (files.length > 10) {
                  setError('Selecione no máximo 10 fotos.')
                  e.target.value = ''
                  return
                }
                setPhotoText('')
                setPhotos(files)
                setError('')
              }}
            />
            <button
              className="button"
              type="button"
              disabled={!photos.length || reading}
              onClick={() => void readPhotos()}
            >
              {reading ? 'Reconhecendo texto...' : 'Tentar ler texto das fotos'}
            </button>
            {photoText && (
              <label>
                Texto reconhecido — confira com a foto
                <textarea readOnly rows={14} value={photoText} />
              </label>
            )}
            <p className="muted">
              A leitura pode errar números ou omitir linhas. Ela não preenche
              nem salva votos automaticamente.
            </p>
          </fieldset>
          <button className="button primary" type="submit" disabled={reading}>
            Conferir lançamento
          </button>
        </form>
      )}
      {photoUrls.length > 0 && (
        <section className="document-section">
          <h2>Fotos para conferência</h2>
          <div className="manual-photos">
            {photoUrls.map((url, i) => (
              <a key={url} href={url} target="_blank" rel="noreferrer">
                <img src={url} alt={`Foto ${i + 1} do BU`} />
                <span>
                  Foto {i + 1}: {photos[i]?.name}
                </span>
              </a>
            ))}
          </div>
        </section>
      )}
    </>
  )
}
