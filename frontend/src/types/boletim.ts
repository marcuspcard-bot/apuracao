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
  local_votacao: string | null
  secao: string
  quantidade_secoes_agregadas: number
  total_secoes_representadas: number
  secoes_agregadas: string[]
  eleitores: {
    aptos: number | null
    comparecimento: number | null
    faltosos: number | null
  }
  urna: {
    codigo_identificacao: string | null
    data_abertura: string | null
    hora_abertura: string | null
    data_fechamento: string | null
    hora_fechamento: string | null
  }
  cargos: Cargo[]
  assinatura_qrcode: string | null
  codigo_carga: string | null
}

export interface Preview {
  substituicao?: BoletimDetail | null
  status: 'OK' | 'INCONSISTENTE'
  hash: string
  arquivo_nome: string
  dados: BoletimDados
  problemas: string[]
  preview_token: string
  expires_in: number
}

export interface BoletimSummary {
  origem: 'PDF' | 'MANUAL'
  id: string
  municipio_nome: string
  municipio_codigo: string
  zona: string
  secao: string
  quantidade_secoes_agregadas: number
  total_secoes_representadas: number
  comparecimento: number | null
  created_at: string
}

export interface BoletimDetail {
  origem: 'PDF' | 'MANUAL'
  tem_foto: boolean
  historico_manual: { substituido_em: string; boletim: BoletimDetail }[]
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
