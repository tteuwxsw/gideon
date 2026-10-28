export type MessageRole = 'user' | 'assistant' | 'system'

export interface Message {
  id: string
  role: MessageRole
  content: string
  timestamp: string
  isStreaming?: boolean
  model?: string
  tokens?: number
  status?: 'pending' | 'streaming' | 'complete' | 'cancelled' | 'error'
  latencyMs?: number
}

export interface ActivityItem {
  id_acao: string
  ferramenta: string
  parametros: Record<string, unknown>
  estado: string
  verificado: boolean
  resultado: unknown
  erros: string[]
  evidencias: Record<string, unknown>
  duracao_ms: number
  mensagem_humana: string
  timestamp: string
}

export interface IdiomaOpcao {
  codigo: string
  nome: string
  descricao: string
}

export type ModoEscuta = 'ativacao_por_nome' | 'conversa_continua' | 'conversa_livre'

export interface VoiceStatusData {
  ativa: boolean
  modo_escuta: ModoEscuta
  sensibilidade: number
  falando: boolean
  ouvindo: boolean
}
