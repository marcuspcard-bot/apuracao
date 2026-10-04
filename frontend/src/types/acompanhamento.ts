export type Section = {
  numero: string
  parcial?: boolean
  apurada: boolean
  boletim_id: string | null
  secao_principal_bu: string | null
  vinculo_divergente: boolean
}

export type SectionGroup = {
  zona: string
  secao_principal: string
  principal: Section
  agregadas: Section[]
  status: 'APURADA' | 'PARCIAL' | 'PENDENTE'
}

export type SectionRegistryPreview = {
  grupos: {
    zona: string
    secao_principal: string
    secoes_agregadas: string[]
  }[]
  versao_lista: string
  substitui_lista: boolean
  total_secoes: number
}

export type Candidate = {
  numero: string
  nome: string
  nomes: string[]
  votos: number
  vagas: { identificacao: string | null; votos: number }[]
}

export type SectionSelection = { zona: string; secao: string }

export type SectionVotes = {
  boletins: number
  cargos: { nome: string; boletins: number; candidatos: Candidate[] }[]
  secoes: (SectionSelection & {
    parcial?: boolean
    tipo: string
    secao_principal: string
    boletim_id: string
  })[]
}

export type Overview = {
  eleicao: { ano: number; turno: number; data: string }
  eleicao_configurada: { ano: number; turno: number; data: string }
  datas_disponiveis: { data: string; boletins: number }[]
  consultado_em: string
  ultima_importacao: string | null
  boletins: number
  boletins_manuais?: number
  secoes_apuradas: number
  secoes_esperadas: number | null
  secoes_pendentes: number | null
  secoes_principais_apuradas: number
  secoes_principais_esperadas: number | null
  secoes_principais_pendentes: number | null
  lista_secoes_importada: boolean
  grupos_secoes: SectionGroup[]
  cargos: SectionVotes['cargos']
  secoes: SectionVotes['secoes']
}
