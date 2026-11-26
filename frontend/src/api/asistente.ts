import { api, API_BASE } from './clienteBase'
import { descargarBlobSeguro } from '../utils/descargaBlob'

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
  rol?: string
  limite_diario?: number
  fecha?: string
}

// ─── Funciones API Asistente IA y Chat ─────────────────────────────────────────

export const fetchAssistantModels = (signal?: AbortSignal) =>
  api.get<ModelsResponse>('/assistant/models', { signal }).then(r => r.data)

export const sendAssistantMessage = (payload: AssistantRequest) =>
  api.post<AssistantResponse>('/assistant/chat', payload, { timeout: 45_000 }).then(r => r.data)

export const fetchChatConversaciones = (espacioId?: number, archivada: boolean = false, signal?: AbortSignal) =>
  api.get<ChatConversacionResumen[]>('/chat/conversaciones', {
    signal,
    params: {
      ...(espacioId ? { espacio_id: espacioId } : {}),
      archivada,
    },
  }).then(r => r.data)

export const createChatConversacion = (payload: { espacio_id: number; titulo?: string }) =>
  api.post<ChatConversacionResumen>('/chat/conversaciones', payload).then(r => r.data)

export const fetchChatConversacionDetalle = (conversacionId: string, signal?: AbortSignal) =>
  api.get<ChatConversacionDetalle>(`/chat/conversaciones/${conversacionId}`, { signal }).then(r => r.data)

export const renameChatConversacion = (conversacionId: string, titulo: string) =>
  api.patch<ChatConversacionResumen>(`/chat/conversaciones/${conversacionId}/renombrar`, { titulo }).then(r => r.data)

export const archiveChatConversacion = (conversacionId: string, archivada: boolean) =>
  api.patch<ChatConversacionResumen>(`/chat/conversaciones/${conversacionId}/archivar`, { archivada }).then(r => r.data)

export const deleteChatConversacion = (conversacionId: string) =>
  api.delete(`/chat/conversaciones/${conversacionId}`).then(r => r.data)

export const fetchChatCuota = (signal?: AbortSignal) =>
  api.get<CuotaIaInfo>('/chat/cuota', { signal }).then(r => r.data)

export const sendInteractiveChatMessage = (payload: InteractiveChatRequest) =>
  api.post<InteractiveChatResponse>('/chat', payload, {
    timeout: 45_000,
    headers: {
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
  },
  signal?: AbortSignal,
) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('uct_auth_token') : null
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
    'x-espacio-id': String(payload.espacio_id || (payload.dataset_tipo === 'estacionamiento' ? 2 : 1)),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  let doneCalled = false
  const finalizar = () => {
    if (!doneCalled) {
      doneCalled = true
      callbacks.onDone()
    }
  }

  try {
    const response = await fetch(`${API_BASE}/chat?stream=true`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ ...payload, stream: true }),
      signal,
    })

    if (response.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('uct_auth_token')
      window.dispatchEvent(new Event('uct:auth-expired'))
    }

    if (!response.ok) {
      let detalle = response.statusText
      try {
        const cuerpo = await response.json()
        if (typeof cuerpo?.detail === 'string' && cuerpo.detail.trim()) {
          detalle = cuerpo.detail
        }
      } catch {
        // Sin cuerpo JSON legible
      }
      throw new Error(`HTTP ${response.status}: ${detalle}`)
    }

    reader = response.body?.getReader()
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
        if (!trimmed.startsWith('data: ')) continue
        try {
          const data = JSON.parse(trimmed.slice(6))
          if (data.type === 'meta') {
            callbacks.onMeta(data)
          } else if (data.type === 'text') {
            callbacks.onChunk(data.chunk)
          } else if (data.type === 'error') {
            throw new Error(data.detail || data.message || 'Error en flujo SSE')
          } else if (data.type === 'done') {
            finalizar()
          }
        } catch (e: any) {
          if (e instanceof SyntaxError) {
            console.error('Error parseando frame SSE:', e)
          } else {
            throw e
          }
        }
      }
    }
    finalizar()
  } catch (err: any) {
    if (err?.name === 'AbortError') return
    callbacks.onError(err)
  } finally {
    if (reader) {
      try {
        reader.releaseLock()
      } catch {
        // Lock ya liberado
      }
    }
  }
}

export const fetchChatHistory = (sessionId: string, espacioId?: number) =>
  api.get<ChatHistoryResponse>('/chat/history', {
    params: {
      session_id: sessionId,
      ...(espacioId ? { espacio_id: espacioId } : {}),
    },
  }).then(r => r.data)

export const exportChatPdf = async (
  sessionId: string,
  titulo?: string,
  conversacionId?: string,
  graficosB64?: Record<string, string>,
) => {
  const convId = conversacionId || (sessionId.includes('-') && sessionId.length === 36 ? sessionId : undefined)
  const res = await api.post('/chat/export-pdf', {
    session_id: sessionId,
    conversacion_id: convId,
    titulo,
    graficos_b64: graficosB64,
  }, {
    responseType: 'blob',
  })
  const blob = new Blob([res.data], { type: 'application/pdf' })
  descargarBlobSeguro(blob, `informe_ejecutivo_${sessionId.slice(0, 8)}.pdf`)
}

