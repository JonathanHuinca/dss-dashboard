import { useState, useRef, useEffect } from 'react'
import { Sparkles, X, Send, Bot, User, Trash2, Cpu, Download, FileText, Table as TableIcon, BarChart3, ChevronDown, Check } from 'lucide-react'
import { InteractiveChart } from '../ui/InteractiveChart'
import {
  sendInteractiveChatMessage,
  fetchChatHistory,
  exportChatPdf,
  fetchAssistantModels,
  ModelItem
} from '../../api/client'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  tipo?: 'plotly' | 'df' | 'text'
  fig_data?: { data: any[]; layout: any }
  table_data?: Record<string, any>[]
  modelUsed?: string
  timestamp: string
}

import { useAssistant } from '../../context/AssistantContext'

interface Props {
  isOpen: boolean
  onClose: () => void
  contexto_grafico?: string
  onClearContexto?: () => void
}

type DatasetType = 'biblioteca' | 'estacionamiento' | 'general'

const QUICK_PROMPTS: Record<DatasetType, string[]> = {
  biblioteca: [
    'Grafica la asistencia del mes de marzo',
    '¿Cuál fue la semana de mayor congestión?',
    '¿Cómo impactan los exámenes en el aforo?',
    '¿Cuál es la franja horaria más crítica?',
    '¿Cómo se distribuyen los perfiles de permanencia?',
    'Muestrame la tabla de datos'
  ],
  estacionamiento: [
    'Grafica el flujo vehicular del mes de marzo',
    '¿Cuál cámara tiene mayor flujo vehicular?',
    '¿Cuáles son las horas de mayor saturación vehicular?',
    'Muestrame la tabla de datos'
  ],
  general: [
    'Grafica la asistencia del mes de marzo',
    '¿Cuál fue la semana de mayor congestión?',
    '¿Cómo impactan los exámenes en el aforo?',
    '¿Cuál cámara tiene mayor flujo vehicular?'
  ]
}

function formatContextName(slug?: string | null): string {
  if (!slug) return ''
  const lowerWords = new Set(['de', 'del', 'la', 'las', 'el', 'los', 'en', 'por', 'y', 'a', 'con', 'para'])
  const words = slug.split('_').filter(Boolean)
  return words
    .map((w, idx) => {
      const lower = w.toLowerCase()
      if (idx > 0 && lowerWords.has(lower)) {
        return lower
      }
      return lower.charAt(0).toUpperCase() + lower.slice(1)
    })
    .join(' ')
}

export function AssistantDrawer({ isOpen, onClose, contexto_grafico, onClearContexto }: Props) {
  const assistantContext = useAssistant()
  const activeContexto = contexto_grafico || assistantContext.contextoGrafico

  const handleClearContext = () => {
    if (onClearContexto) onClearContexto()
    assistantContext.clearContexto()
  }

  const [sessionId] = useState<string>(() => {
    const saved = localStorage.getItem('uct_dss_chat_session_id')
    if (saved) return saved
    const created = 'uct-' + Math.random().toString(36).substring(2, 10)
    localStorage.setItem('uct_dss_chat_session_id', created)
    return created
  })

  const [datasetTipo, setDatasetTipo] = useState<DatasetType>('biblioteca')
  const [selectedModel, setSelectedModel] = useState('gemini-3.5-flash-lite')
  const [availableModels, setAvailableModels] = useState<ModelItem[]>([
    { id: 'gemini-3.5-flash-lite', name: 'Gemini 3.5 Flash Lite (Recomendado)', description: 'Máxima inferencia y velocidad DSS' },
    { id: 'gemini-3.1-flash-lite', name: 'Gemini 3.1 Flash Lite', description: 'Equilibrio analítico multidimensional' },
  ])
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome-1',
      role: 'assistant',
      content:
        'Hola. Soy tu Asistente Analítico Inteligente DSS. Puedo generar gráficos interactivos Plotly, tablas estructuradas o informes técnicos sobre aforos y el calendario académico.',
      tipo: 'text',
      modelUsed: 'gemini-2.5-flash-lite',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchAssistantModels()
      .then(res => {
        if (res.models && res.models.length > 0) {
          setAvailableModels(res.models)
          if (res.default) setSelectedModel(res.default)
        }
      })
      .catch(() => {})

    fetchChatHistory(sessionId)
      .then(res => {
        if (res.messages && res.messages.length > 0) {
          const loaded: Message[] = []
          res.messages.forEach(m => {
            loaded.push({
              id: `u-${m.id}`,
              role: 'user',
              content: m.prompt,
              timestamp: m.timestamp
            })
            loaded.push({
              id: `a-${m.id}`,
              role: 'assistant',
              content: m.explicacion,
              tipo: m.tipo,
              fig_data: m.fig_data,
              table_data: m.table_data,
              modelUsed: m.model_used,
              timestamp: m.timestamp
            })
          })
          setMessages(loaded)
        }
      })
      .catch(() => {})
  }, [sessionId])

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    }
  }, [isOpen, messages, loading])

  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || input).trim()
    if (!query || loading) return

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await sendInteractiveChatMessage({
        prompt: query,
        dataset_tipo: datasetTipo,
        session_id: sessionId,
        model: selectedModel,
        grafico_contexto: activeContexto,
      })

      const assistantMsg: Message = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: res.explicacion,
        tipo: res.tipo,
        fig_data: res.fig_data,
        table_data: res.table_data,
        modelUsed: res.model_used,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }

      setMessages(prev => [...prev, assistantMsg])
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string; error?: string } } }
      const detail = axiosErr?.response?.data?.detail || axiosErr?.response?.data?.error
      const isRateLimit = axiosErr?.response?.status === 429
      const isAuthError = axiosErr?.response?.status === 401 || axiosErr?.response?.status === 403
      let errorText = 'Error de comunicación con el servicio analítico. Intente nuevamente en unos instantes.'
      if (isRateLimit) {
        errorText = `Límite de consultas excedido: ${detail || 'Ha alcanzado el tope diario permitido para su rol.'}`
      } else if (isAuthError) {
        errorText = 'Sesión expirada o permisos insuficientes. Por favor inicie sesión nuevamente.'
      } else if (detail) {
        errorText = detail
      }
      const errMsg: Message = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: errorText,
        tipo: 'text',
        modelUsed: selectedModel,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }
      setMessages(prev => [...prev, errMsg])
    } finally {
      setLoading(false)
    }
  }

  const handleExportPdf = async () => {
    if (exporting) return
    setExporting(true)
    try {
      await exportChatPdf(sessionId, `Informe Ejecutivo DSS UCT - Sesión ${sessionId.slice(0, 8)}`)
    } catch {
      alert('No se pudo generar el informe en este momento.')
    } finally {
      setExporting(false)
    }
  }

  const handleClearChat = () => {
    const newId = 'uct-' + Math.random().toString(36).substring(2, 10)
    localStorage.setItem('uct_dss_chat_session_id', newId)
    setMessages([
      {
        id: `init-${Date.now()}`,
        role: 'assistant',
        content: 'Historial reiniciado. Puedes realizar nuevas consultas sobre Biblioteca o Estacionamiento.',
        tipo: 'text',
        modelUsed: selectedModel,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ])
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
      <div
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      <div className="relative w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col z-10">
        <div className="bg-uct-blue-primary text-white p-4 flex flex-col gap-3 border-b border-white/10">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-uct-gold flex items-center justify-center text-uct-blue-primary">
                <Sparkles size={18} />
              </div>
              <div>
                <h2 className="text-sm font-bold flex items-center gap-2">
                  Asistente IA · Sistema DSS
                  <span className="text-[10px] bg-uct-gold/20 text-uct-gold border border-uct-gold/30 px-1.5 py-0.5 rounded-full uppercase tracking-wider font-semibold">
                    UCT CSF
                  </span>
                </h2>
                <p className="text-[11px] text-white/70">Plotly interactivo, tablas dinámicas e informes PDF</p>
              </div>
            </div>

            <div className="flex items-center gap-1.5">
              <button
                onClick={handleExportPdf}
                disabled={exporting}
                title="Descargar informe ejecutivo en PDF"
                className="flex items-center gap-1.5 bg-white/10 hover:bg-white/20 text-white text-xs px-2.5 py-1.5 rounded-lg border border-white/20 transition-all cursor-pointer disabled:opacity-50"
              >
                <Download size={13} className={exporting ? 'animate-bounce' : ''} />
                <span className="hidden sm:inline font-medium">{exporting ? 'Exportando...' : 'Informe PDF'}</span>
              </button>
              <button
                onClick={handleClearChat}
                title="Limpiar conversación"
                className="p-1.5 text-white/60 hover:text-white hover:bg-white/10 rounded-lg transition-colors cursor-pointer"
              >
                <Trash2 size={16} />
              </button>
              <button
                onClick={onClose}
                title="Cerrar panel"
                className="p-1.5 text-white/60 hover:text-white hover:bg-white/10 rounded-lg transition-colors cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex items-center justify-between bg-white/10 px-3 py-1.5 rounded-lg border border-white/10">
              <span className="text-white/70 font-medium">Módulo:</span>
              <select
                value={datasetTipo}
                onChange={e => setDatasetTipo(e.target.value as DatasetType)}
                className="bg-uct-blue-secondary text-white text-xs font-semibold px-2 py-0.5 rounded border border-white/20 focus:outline-none cursor-pointer"
              >
                <option value="biblioteca">Biblioteca CSF</option>
                <option value="estacionamiento">Estacionamiento</option>
                <option value="general">Visión General</option>
              </select>
            </div>

            <div className="flex items-center justify-between bg-white/10 px-3 py-1.5 rounded-lg border border-white/10">
              <div className="flex items-center gap-1 text-white/70">
                <Cpu size={12} className="text-uct-gold" />
                <span className="font-medium">Modelo:</span>
              </div>
              <select
                value={selectedModel}
                onChange={e => setSelectedModel(e.target.value)}
                className="bg-uct-blue-secondary text-white text-xs font-semibold px-2 py-0.5 rounded border border-white/20 focus:outline-none cursor-pointer"
              >
                {availableModels.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {activeContexto && (
          <div className="bg-gradient-to-r from-amber-50 to-amber-100/50 border-b border-amber-200/80 px-4 py-2 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2 text-amber-950">
              <Sparkles size={14} className="text-amber-600 shrink-0 animate-pulse" />
              <span>
                Foco analítico en gráfico: <span className="font-bold underline decoration-amber-400 text-[12px]">{formatContextName(activeContexto)}</span>
              </span>
            </div>
            <button
              onClick={handleClearContext}
              className="text-amber-700 hover:text-amber-900 text-[11px] font-semibold px-2 py-0.5 rounded hover:bg-amber-200/70 transition-colors cursor-pointer"
              title="Quitar filtro de contexto"
            >
              Desvincular
            </button>
          </div>
        )}

        <div className="bg-slate-50 border-b border-slate-200 px-4 py-2.5">
          <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
            Sugerencias Analíticas ({datasetTipo})
          </p>
          <div className="flex flex-wrap gap-1.5">
            {activeContexto && (
              <button
                onClick={() => handleSendMessage(`Analiza detalladamente las métricas y tendencias del gráfico "${formatContextName(activeContexto)}"`)}
                disabled={loading}
                className="text-[11px] bg-amber-50 text-amber-900 hover:bg-amber-100 border border-amber-300 px-2.5 py-1 rounded-full transition-all shadow-2xs font-semibold flex items-center gap-1 cursor-pointer"
              >
                <Sparkles size={11} className="text-amber-600" />
                <span>Analizar {formatContextName(activeContexto)}</span>
              </button>
            )}
            {QUICK_PROMPTS[datasetTipo].map((q, i) => (
              <button
                key={i}
                onClick={() => handleSendMessage(q)}
                disabled={loading}
                className="text-[11px] bg-white text-slate-700 hover:text-uct-blue-primary hover:border-uct-blue-primary/40 border border-slate-200 px-2.5 py-1 rounded-full transition-all shadow-2xs hover:shadow-xs disabled:opacity-50 cursor-pointer text-left"
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50/50">
          {messages.map(msg => (
            <div
              key={msg.id}
              className={`flex gap-2.5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.role === 'assistant' && (
                <div className="w-7 h-7 rounded-full bg-uct-blue-primary text-uct-gold flex items-center justify-center shrink-0 mt-0.5 shadow-xs">
                  <Bot size={15} />
                </div>
              )}

              <div
                className={`max-w-[90%] rounded-2xl p-3 text-xs leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-uct-blue-primary text-white rounded-br-xs shadow-xs'
                    : 'bg-white text-slate-800 border border-slate-200/80 rounded-bl-xs shadow-xs space-y-2.5'
                }`}
              >
                <div className="whitespace-pre-wrap">{msg.content}</div>

                {msg.tipo === 'plotly' && msg.fig_data && (
                  <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
                    <InteractiveChart
                      data={msg.fig_data.data}
                      layout={msg.fig_data.layout}
                      height={270}
                      filename="grafico_asistente_uct"
                    />
                  </div>
                )}

                {msg.tipo === 'df' && msg.table_data && msg.table_data.length > 0 && (
                  <div className="overflow-x-auto rounded-lg border border-slate-200 mt-2 bg-white">
                    <table className="w-full text-[11px] text-left border-collapse">
                      <thead className="bg-uct-blue-primary text-white uppercase text-[10px]">
                        <tr>
                          {Object.keys(msg.table_data[0]).map((col, idx) => (
                            <th key={idx} className="px-2.5 py-1.5 font-semibold">
                              {col.replace(/_/g, ' ')}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {msg.table_data.slice(0, 10).map((row, rIdx) => (
                          <tr key={rIdx} className="hover:bg-slate-50">
                            {Object.values(row).map((val: any, cIdx) => (
                              <td key={cIdx} className="px-2.5 py-1 text-slate-600">
                                {typeof val === 'number' ? val.toLocaleString() : String(val)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div
                  className={`flex items-center justify-between text-[10px] pt-1 ${
                    msg.role === 'user' ? 'text-white/60' : 'text-slate-400'
                  }`}
                >
                  <span>{msg.timestamp}</span>
                  {msg.role === 'assistant' && (
                    <span className="flex items-center gap-1 font-medium text-slate-500">
                      {msg.tipo === 'plotly' && <BarChart3 size={11} className="text-uct-gold" />}
                      {msg.tipo === 'df' && <TableIcon size={11} className="text-emerald-500" />}
                      {msg.tipo === 'text' && <FileText size={11} className="text-blue-500" />}
                      <span className="uppercase text-[9px]">{msg.tipo}</span>
                      <span className="text-slate-300">•</span>
                      <span>{msg.modelUsed || 'DSS Local'}</span>
                    </span>
                  )}
                </div>
              </div>

              {msg.role === 'user' && (
                <div className="w-7 h-7 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center shrink-0 mt-0.5">
                  <User size={15} />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex gap-2.5 justify-start">
              <div className="w-7 h-7 rounded-full bg-uct-blue-primary text-uct-gold flex items-center justify-center shrink-0 mt-0.5">
                <Bot size={15} />
              </div>
              <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-xs p-3 shadow-xs flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full bg-uct-gold animate-bounce" />
                <div className="w-2 h-2 rounded-full bg-uct-gold animate-bounce [animation-delay:0.2s]" />
                <div className="w-2 h-2 rounded-full bg-uct-gold animate-bounce [animation-delay:0.4s]" />
                <span className="text-[11px] text-slate-400 ml-1">Procesando consulta analítica...</span>
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        <div className="p-3 bg-white border-t border-slate-200">
          <form
            onSubmit={e => {
              e.preventDefault()
              handleSendMessage()
            }}
            className="flex items-center gap-2"
          >
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="Pregunta o escribe 'tabla', 'certámenes', 'semanas'..."
              disabled={loading}
              className="flex-1 text-xs bg-slate-50 border border-slate-300 rounded-xl px-3 py-2.5 text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-uct-blue-primary focus:border-uct-blue-primary disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="bg-uct-blue-primary hover:bg-uct-blue-secondary text-white p-2.5 rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer shrink-0 shadow-xs"
            >
              <Send size={15} />
            </button>
          </form>
          <div className="flex items-center justify-between mt-1.5 text-[10px] text-slate-400">
            <span>Sesión: {sessionId.slice(0, 12)}</span>
            <span>Anonimización irreversible HMAC/SHA-256</span>
          </div>
        </div>
      </div>
    </div>
  )
}
export default AssistantDrawer
