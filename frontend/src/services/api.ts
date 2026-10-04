import axios from 'axios'
import type { BoletimDetail, BoletimSummary, Preview } from '../types/boletim'
import type {
  Overview,
  SectionRegistryPreview,
  SectionSelection,
  SectionVotes,
} from '../types/acompanhamento'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  timeout: 120000,
})

api.interceptors.request.use((config) => {
  if (!import.meta.env.VITE_API_URL)
    throw new Error('O endereço da API não foi configurado.')
  return config
})

export async function sendPdf(
  file: File,
  signal: AbortSignal,
  substituirId?: string,
): Promise<Preview> {
  const form = new FormData()
  form.append('file', file)
  return (
    await api.post('/api/boletins/preview', form, {
      signal,
      timeout: 180000,
      params: { substituir_id: substituirId },
    })
  ).data
}

export async function confirmBoletim(
  token: string,
  substituirId?: string,
): Promise<{ id: string; detail: string }> {
  return (
    await api.post(
      '/api/boletins/confirmar',
      { preview_token: token, substituir_id: substituirId },
      { timeout: 240000 },
    )
  ).data
}

export async function findBoletimReceipt(
  hash: string,
): Promise<{ id: string } | null> {
  return (await api.get(`/api/boletins/por-hash/${hash}`, { timeout: 15000 }))
    .data
}

export function confirmationMayHaveSucceeded(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false
  const status = error.response?.status
  return status === undefined || status >= 500
}

export function serverErrorMessage(error: unknown): string | undefined {
  return axios.isAxiosError(error) && error.response
    ? errorMessage(error)
    : undefined
}

export async function listBoletins(
  offset: number,
  signal: AbortSignal,
): Promise<BoletimSummary[]> {
  return (
    await api.get('/api/boletins', { params: { offset, limit: 20 }, signal })
  ).data
}

export async function getBoletim(
  id: string,
  signal: AbortSignal,
): Promise<BoletimDetail> {
  return (await api.get(`/api/boletins/${id}`, { signal })).data
}

export async function getOverview(
  signal: AbortSignal,
  electionDate?: string,
): Promise<Overview> {
  return (
    await api.get('/api/acompanhamento', {
      signal,
      timeout: 15000,
      params: electionDate ? { data: electionDate } : undefined,
    })
  ).data
}

export async function getSectionVotes(
  section: SectionSelection,
  electionDate: string,
  signal: AbortSignal,
): Promise<SectionVotes> {
  return (
    await api.get('/api/acompanhamento/votos-secao', {
      signal,
      timeout: 15000,
      params: { ...section, data: electionDate },
    })
  ).data
}

export async function previewSections(
  file: File,
): Promise<SectionRegistryPreview> {
  const form = new FormData()
  form.append('file', file)
  return (await api.post('/api/acompanhamento/secoes/preview', form)).data
}

export async function confirmSections(
  preview: SectionRegistryPreview,
): Promise<void> {
  await api.post('/api/acompanhamento/secoes/confirmar', {
    grupos: preview.grupos,
    versao_lista: preview.versao_lista,
  })
}

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (detail?.problemas) return detail.problemas.join(' ')
    if (!error.response)
      return 'Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente.'
    return 'Não foi possível concluir a operação. Tente novamente.'
  }
  return error instanceof Error ? error.message : 'Ocorreu um erro inesperado.'
}

export const formatDate = (value: string | null) =>
  value === null
    ? 'Não informado'
    : new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR')
export const formatNumber = (value: number | null) =>
  value === null ? 'Não identificado' : value.toLocaleString('pt-BR')
