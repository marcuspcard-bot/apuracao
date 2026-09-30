import { api } from './api'
import type {
  AvailableCandidate,
  Disclosure,
  ScreenConfig,
  ScreenSave,
} from '../types/telao'

export async function getScreenConfig(
  signal?: AbortSignal,
): Promise<ScreenConfig> {
  return (await api.get('/api/telao/config', { signal, timeout: 15000 })).data
}

export async function saveScreenConfig(
  body: ScreenSave,
): Promise<ScreenConfig> {
  return (await api.put('/api/telao/config', body, { timeout: 30000 })).data
}

export async function searchCandidates(
  cargo: string,
  q: string,
  offset: number,
  signal: AbortSignal,
): Promise<{
  candidatos: AvailableCandidate[]
  tem_mais: boolean
}> {
  return (
    await api.get('/api/telao/candidatos-disponiveis', {
      signal,
      timeout: 15000,
      params: { cargo, q, offset, limit: 20 },
    })
  ).data
}

export async function getDisclosure(signal: AbortSignal): Promise<Disclosure> {
  return (await api.get('/api/divulgacao', { signal, timeout: 15000 })).data
}
