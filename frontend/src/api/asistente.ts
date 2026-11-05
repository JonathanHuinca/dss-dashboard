import axios from 'axios'
import { api } from './clienteBase'

export interface AssistantRequest {
  message: string
  model?: string
  history?: { role: string; content: string }[]
}

export interface AssistantResponse {
  reply: string
  model_requested: string
  model_used: string
  success: boolean
  live_llm: boolean
  error?: string
}

export interface ModelItem {
  id: string
  name: string
  description: string
}

export interface ModelsResponse {
  models: ModelItem[]
  default: string
}

export interface InteractiveChatRequest {
  prompt: string
  dataset_tipo: string
  session_id: string
  conversacion_id?: string
  model?: string
  grafico_contexto?: string
  espacio_id?: number
  fecha_inicio?: string
  fecha_fin?: string
  periodo_label?: string
  filtros?: Record<string, any>
}

export interface InteractiveChatResponse {
  tipo: 'component' | 'plotly' | 'df' | 'text' | string
  explicacion: string
  component?: string
  payload?: any
  fig_data?: { data: any[]; layout: any }
  table_data?: Record<string, any>[]
  session_id: string
  conversacion_id?: string
  model_used: string
}

export interface ChatHistoryItem {
  id: string
  timestamp: string
  prompt: string
  dataset_tipo: string
  tipo: 'component' | 'plotly' | 'df' | 'text' | string
  explicacion: string
  component?: string
  payload?: any
  fig_data?: { data: any[]; layout: any }
  table_data?: Record<string, any>[]
  model_used: string
}

export interface ChatHistoryResponse {
  session_id: string
  messages: ChatHistoryItem[]
}

export interface ChatConversacionResumen {
  id: string
  usuario_id: number
  espacio_id: number
  titulo: string
  creada_en: string
  actualizada_en: string
  archivada: boolean
}

export interface ChatMensajeItem {
  id: string
  conversacion_id: string
  rol: 'user' | 'assistant' | 'system'
  tipo: string
  contenido: string
  herramienta?: string
  argumentos_json?: string
  modelo?: string
  creado_en: string
}

export interface ChatConversacionDetalle {
  id: string
  usuario_id: number
  espacio_id: number
  titulo: string
  creada_en: string
  actualizada_en: string
  archivada: boolean
  mensajes: ChatMensajeItem[]
}

export interface CuotaIaInfo {
  usadas: number
  limite: number
  restantes: number
}

const getAuthHeaders = (): Record<string, string> => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('uct_auth_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ─── Funciones API Asistente IA y Chat ─────────────────────────────────────────

export const fetchAssistantModels = () =>
  api.get<ModelsResponse>('/assistant/models').then(r => r.data)

export const sendAssistantMessage = (payload: AssistantRequest) =>
  api.post<AssistantResponse>('/assistant/chat', payload, { timeout: 45_000 }).then(r => r.data)

export const fetchChatConversaciones = (espacioId?: number, archivada: boolean = false) =>
  axios.get<ChatConversacionResumen[]>('/api/chat/conversaciones', {
    params: {
      ...(espacioId ? { espacio_id: espacioId } : {}),
      archivada,
    },
    headers: getAuthHeaders(),
  }).then(r => r.data)

export const createChatConversacion = (payload: { espacio_id: number; titulo?: string }) =>
  axios.post<ChatConversacionResumen>('/api/chat/conversaciones', payload, {
    headers: getAuthHeaders(),
  }).then(r => r.data)

export const fetchChatConversacionDetalle = (conversacionId: string) =>
  axios.get<ChatConversacionDetalle>(`/api/chat/conversaciones/${conversacionId}`, {
    headers: getAuthHeaders(),
  }).then(r => r.data)

export const renameChatConversacion = (conversacionId: string, titulo: string) =>
  axios.patch<ChatConversacionResumen>(`/api/chat/conversaciones/${conversacionId}/renombrar`, { titulo }, {
    headers: getAuthHeaders(),
  }).then(r => r.data)

export const archiveChatConversacion = (conversacionId: string, archivada: boolean) =>
  axios.patch<ChatConversacionResumen>(`/api/chat/conversaciones/${conversacionId}/archivar`, { archivada }, {
    headers: getAuthHeaders(),
  }).then(r => r.data)

export const deleteChatConversacion = (conversacionId: string) =>
  axios.delete(`/api/chat/conversaciones/${conversacionId}`, {
    headers: getAuthHeaders(),
  }).then(r => r.data)

export const fetchChatCuota = () =>
  axios.get<CuotaIaInfo>('/api/chat/cuota', {
    headers: getAuthHeaders(),
  }).then(r => r.data)

export const sendInteractiveChatMessage = (payload: InteractiveChatRequest) =>
  axios.post<InteractiveChatResponse>('/api/chat', payload, {
    timeout: 45_000,
    headers: {
      ...getAuthHeaders(),
      'x-espacio-id': String(payload.espacio_id || (payload.dataset_tipo === 'estacionamiento' ? 2 : 1)),
    },
  }).then(r => r.data)

export async function sendInteractiveChatStream(
  payload: InteractiveChatRequest,
  callbacks: {
    onMeta: (meta: { intent: string; tipo?: string; component?: string; payload?: any; conversacion_id?: string }) => void
    onChunk: (chunk: string) => void
    onDone: () => void
    onError: (err: any) => void
  }
) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('uct_auth_token') : null
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
    'x-espacio-id': String(payload.espacio_id || (payload.dataset_tipo === 'estacionamiento' ? 2 : 1)),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  try {
    const response = await fetch('/api/chat?stream=true', {
      method: 'POST',
      headers,
      body: JSON.stringify({ ...payload, stream: true }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const reader = response.body?.getReader()
    if (!reader) throw new Error('No readable stream')

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data: ')) {
          try {
            const data = JSON.parse(trimmed.slice(6))
            if (data.type === 'meta') {
              callbacks.onMeta(data)
            } else if (data.type === 'text') {
              callbacks.onChunk(data.chunk)
            } else if (data.type === 'done') {
              callbacks.onDone()
            }
          } catch (e) {
            console.error('Error parseando frame SSE:', e)
          }
        }
      }
    }
    callbacks.onDone()
  } catch (err) {
    callbacks.onError(err)
  }
}

export const fetchChatHistory = (sessionId: string) =>
  axios.get<ChatHistoryResponse>('/api/chat/history', {
    params: { session_id: sessionId },
    headers: getAuthHeaders(),
  }).then(r => r.data)

export const exportChatPdf = async (
  sessionId: string,
  titulo?: string,
  conversacionId?: string,
  graficosB64?: Record<string, string>,
) => {
  const convId = conversacionId || (sessionId.includes('-') && sessionId.length === 36 ? sessionId : undefined)
  const res = await axios.post('/api/chat/export-pdf', {
    session_id: sessionId,
    conversacion_id: convId,
    titulo,
    graficos_b64: graficosB64,
  }, {
    responseType: 'blob',
    headers: getAuthHeaders(),
  })
  const blob = new Blob([res.data], { type: 'application/pdf' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `informe_ejecutivo_${sessionId.slice(0, 8)}.pdf`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}

