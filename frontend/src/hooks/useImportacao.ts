import { useEffect, useRef, useState } from 'react'
import {
  confirmBoletim,
  confirmationMayHaveSucceeded,
  errorMessage,
  findBoletimReceipt,
  sendPdf,
  serverErrorMessage,
} from '../services/api'
import type { Preview } from '../types/boletim'

const UNCERTAIN_SAVE =
  'Não foi possível confirmar o salvamento. O boletim pode ter sido salvo. Verifique o salvamento antes de tentar novamente.'

export function useImportacao(substituirId?: string) {
  const [preview, setPreview] = useState<Preview | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const [pdfUrl, setPdfUrl] = useState('')
  const [expires, setExpires] = useState(0)
  const [now, setNow] = useState(Date.now())
  const [uncertain, setUncertain] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const busy = useRef(false)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      abort.current?.abort()
    }
  }, [])
  useEffect(
    () => () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl)
    },
    [pdfUrl],
  )
  useEffect(() => {
    if (!preview) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [preview])
  useEffect(() => {
    if (!saving) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [saving])

  function reset() {
    abort.current?.abort()
    setPreview(null)
    setLoading(false)
    setPdfUrl('')
    setError('')
    setUncertain(false)
  }

  function received(id: string) {
    if (!mounted.current) return
    reset()
    setSaved(id)
  }

  async function upload(file: File) {
    if (busy.current) return
    reset()
    setSaved('')
    setLoading(true)
    const controller = new AbortController()
    abort.current = controller
    try {
      const result = await sendPdf(file, controller.signal, substituirId)
      if (controller.signal.aborted) return
      setPreview(result)
      setPdfUrl(URL.createObjectURL(file))
      setExpires(Date.now() + result.expires_in * 1000)
      setNow(Date.now())
    } catch (e) {
      if (!controller.signal.aborted) setError(errorMessage(e))
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }

  async function checkReceipt(hash: string, failureMessage?: string) {
    let reachable = false
    try {
      const receipt = await findBoletimReceipt(hash)
      reachable = true
      if (receipt) {
        received(receipt.id)
        return
      }
    } catch {
      // A failed lookup or a pending transaction cannot prove that the save failed.
    }
    if (mounted.current) {
      setUncertain(true)
      setError(reachable && failureMessage ? failureMessage : UNCERTAIN_SAVE)
    }
  }

  async function save(checkOnly = false) {
    if (!preview || busy.current) return
    busy.current = true
    setSaving(true)
    setError('')
    try {
      if (checkOnly) {
        await checkReceipt(preview.hash)
      } else {
        try {
          const result = await confirmBoletim(preview.preview_token, substituirId)
          received(result.id)
        } catch (e) {
          if (!mounted.current) return
          if (confirmationMayHaveSucceeded(e)) {
            await checkReceipt(preview.hash, serverErrorMessage(e))
          } else {
            setUncertain(false)
            setError(errorMessage(e))
          }
        }
      }
    } finally {
      busy.current = false
      if (mounted.current) setSaving(false)
    }
  }

  return {
    preview,
    loading,
    saving,
    error,
    saved,
    pdfUrl,
    uncertain,
    expired: Boolean(preview && now >= expires),
    reset,
    upload,
    save,
  }
}
