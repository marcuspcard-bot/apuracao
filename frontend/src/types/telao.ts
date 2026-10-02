export type AvailableCandidate = {
  candidato_id: string | null
  cargo: string
  numero: string
  nome: string
}

export type ScreenSelection = AvailableCandidate & {
  id?: string
  ordem?: number
  ativo: boolean
  foto_url?: string | null
  foto?: string | null
}

export type ScreenConfig = {
  municipio: string
  municipio_codigo: string
  uf: string
  zona: string
  eleicao_data: string
  eleicao_turno: number
  cards_por_pagina: number
  tempo_rotacao_segundos: number
  ativo: boolean
  versao: number
  updated_at: string | null
  cargos: string[]
  candidatos: ScreenSelection[]
}

export type ScreenSave = Pick<
  ScreenConfig,
  'versao' | 'cards_por_pagina' | 'tempo_rotacao_segundos' | 'ativo'
> & {
  candidatos: Pick<ScreenSelection, 'cargo' | 'numero' | 'ativo' | 'foto'>[]
}

export type PublicCandidate = {
  id: string
  cargo: string
  numero: string
  nome: string
  ordem: number
  votos: number
  foto_url?: string | null
}

export type Disclosure = {
  municipio: string
  uf: string
  zona: string
  eleicao_data: string
  eleicao_turno: number
  boletins_recebidos: number
  secoes_representadas: number
  total_secoes_esperadas: number | null
  urnas_apuradas: number
  total_urnas: number | null
  ultima_atualizacao: string
  ultima_importacao: string | null
  cards_por_pagina: number
  tempo_rotacao_segundos: number
  ativo: boolean
  versao: number
  candidatos: PublicCandidate[]
}
