export interface ResultadoDados {
  candidatos: { numero: string; nome: string; votos: number }[]
  votos_nominais: number | null
  votos_legenda: number | null
  brancos: number | null
  nulos: number | null
  total_apurado: number | null
}

export interface ResultadoVaga extends ResultadoDados {
  identificacao: string
}

export interface Cargo extends ResultadoDados {
  nome: string
  vagas: ResultadoVaga[]
}

export interface BoletimDados {
  eleicao: { descricao: string; turno: number; data: string }
  municipio: { codigo: string; nome: string }
  zona: string
  local_votacao: string
  secao: string
  quantidade_secoes_agregadas: number
  total_secoes_representadas: number
  secoes_agregadas: string[]
  eleitores: { aptos: number; comparecimento: number; faltosos: number }
  urna: {
    codigo_identificacao: string
    data_abertura: string
    hora_abertura: string
    data_fechamento: string
    hora_fechamento: string
  }
  cargos: Cargo[]
  assinatura_qrcode: string
  codigo_carga: string
}

export interface Preview {
  status: 'OK' | 'INCONSISTENTE'
  hash: string
  arquivo_nome: string
  dados: BoletimDados
  problemas: string[]
  preview_token: string
  expires_in: number
}

export interface BoletimSummary {
  id: string
  municipio_nome: string
  municipio_codigo: string
  zona: string
  secao: string
  quantidade_secoes_agregadas: number
  total_secoes_representadas: number
  comparecimento: number
  created_at: string
}

export interface BoletimDetail {
  id: string
  created_at: string
  dados: BoletimDados
  dados_gerais: Omit<BoletimDados, 'cargos'>
  cargos: Cargo[]
  arquivo_nome_original: string
  arquivo_hash: string
  storage_bucket: string
  storage_path: string
  secoes: { numero_secao: string; tipo: string }[]
}
