import { useState, useRef, useEffect, useCallback } from 'react'
import { ErrorBoundary } from '../ui/ErrorBoundary'
import {
  Sparkles,
  X,
  Send,
  Trash2,
  Cpu,
  Download,
  History,
  Plus,
  Edit2,
  Check,
  Archive,
  ArchiveRestore,
  ShieldAlert,
  Clock,
  MessageSquare,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
} from 'lucide-react'
import { ChatMessage, ChatMessageData } from './ChatMessage'
import { capturarElementoGrafico } from '../../utils/exportadorConsulta'
import {
  sendInteractiveChatMessage,
  sendInteractiveChatStream,
  exportChatPdf,
  fetchAssistantModels,
  fetchChatConversaciones,
  createChatConversacion,
  fetchChatConversacionDetalle,
  renameChatConversacion,
  archiveChatConversacion,
  deleteChatConversacion,
  fetchChatCuota,
  ChatConversacionResumen,
  CuotaIaInfo,
  ModelItem,
} from '../../api/client'

type Message = ChatMessageData

import { useAssistant } from '../../context/AssistantContext'
import { useDownloadProgress } from '../../context/DownloadProgressContext'
import { useAuth } from '../../context/AuthContext'

interface Props {
  isOpen: boolean
  onClose: () => void
  contexto_grafico?: string
  onClearContexto?: () => void
  dateRange?: { startDate?: string; endDate?: string; label?: string }
  dataset_tipo?: DatasetType
}

type DatasetType = 'biblioteca' | 'estacionamiento'

const QUICK_PROMPTS: Record<DatasetType, string[]> = {
  biblioteca: [
    'Grafica la asistencia del mes de marzo',
    '¿Cuál fue la semana de mayor congestión?',
    '¿Cómo impactan los exámenes en el aforo?',
    '¿Cuál es la franja horaria más crítica?',
    '¿Cómo se distribuyen los perfiles de permanencia?',
    'Muestrame la tabla de datos',
  ],
  estacionamiento: [
    'Grafica el flujo vehicular del mes de marzo',
    '¿Cuál cámara tiene mayor flujo vehicular?',
    '¿Cuáles son las horas de mayor saturación vehicular?',
    'Muestrame la tabla de datos',
  ],
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

export function AssistantDrawer({
  isOpen,
  onClose,
  contexto_grafico,
  onClearContexto,
  dateRange,
  dataset_tipo: initialDatasetTipo,
}: Props) {
  const assistantContext = useAssistant()
  const { ejecutarDescarga } = useDownloadProgress()
  const { hasDatasetAccess, isSuperAdmin } = useAuth()
  const puedeAccederBiblioteca = isSuperAdmin || hasDatasetAccess('biblioteca')
  const puedeAccederEstacionamiento = isSuperAdmin || hasDatasetAccess('estacionamiento')

  const activeContexto = contexto_grafico || assistantContext.contextoGrafico
  const activePeriodo = dateRange || assistantContext.periodo
  const activeFiltros = assistantContext.filtros

  const handleClearContext = () => {
    if (onClearContexto) onClearContexto()
    assistantContext.clearContexto()
  }

  const [datasetTipo, setDatasetTipo] = useState<DatasetType>(() => {
    if (initialDatasetTipo === 'estacionamiento' && puedeAccederEstacionamiento) return 'estacionamiento'
    if (initialDatasetTipo === 'biblioteca' && puedeAccederBiblioteca) return 'biblioteca'
    if (puedeAccederBiblioteca) return 'biblioteca'
    if (puedeAccederEstacionamiento) return 'estacionamiento'
    return 'biblioteca'
  })

  useEffect(() => {
    if (initialDatasetTipo === 'estacionamiento' && puedeAccederEstacionamiento) {
      setDatasetTipo('estacionamiento')
    } else if (initialDatasetTipo === 'biblioteca' && puedeAccederBiblioteca) {
      setDatasetTipo('biblioteca')
    } else if (!puedeAccederBiblioteca && puedeAccederEstacionamiento) {
      setDatasetTipo('estacionamiento')
    } else if (!puedeAccederEstacionamiento && puedeAccederBiblioteca) {
      setDatasetTipo('biblioteca')
    }
  }, [initialDatasetTipo, puedeAccederBiblioteca, puedeAccederEstacionamiento])

  // Espacio ID según dataset seleccionado
  const espacioIdActual = datasetTipo === 'estacionamiento' ? 2 : 1

  const [selectedModel, setSelectedModel] = useState('gemini-2.5-flash-lite')
  const [availableModels, setAvailableModels] = useState<ModelItem[]>([
    { id: 'gemini-2.5-flash-lite', name: 'Gemini 2.5 Flash Lite (Recomendado)', description: 'Máxima inferencia y velocidad DSS' },
  ])

  // Estados de persistencia y gestión de conversaciones
  const [conversaciones, setConversaciones] = useState<ChatConversacionResumen[]>([])
  const [conversacionActivaId, setConversacionActivaId] = useState<string | null>(null)
  const [conversacionActivaTitulo, setConversacionActivaTitulo] = useState<string>('Nueva conversación')
  const [mostrarHistorialPanel, setMostrarHistorialPanel] = useState<boolean>(false)
  const [verArchivadas, setVerArchivadas] = useState<boolean>(false)
  const [cargandoHistorial, setCargandoHistorial] = useState<boolean>(false)

  // Edición de título inline
  const [editandoConvId, setEditandoConvId] = useState<string | null>(null)
  const [nuevoTitulo, setNuevoTitulo] = useState<string>('')

  // Cuota diaria de IA
  const [cuotaIa, setCuotaIa] = useState<CuotaIaInfo | null>(null)

  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome-1',
      role: 'assistant',
      content:
        'Hola. Soy tu Asistente Analítico Inteligente DSS. Puedo generar gráficos interactivos, tablas estructuradas o informes técnicos sobre aforos y el calendario académico.',
      tipo: 'text',
      modelUsed: 'gemini-2.5-flash-lite',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  // Cargar modelos y cuota al inicializar
  useEffect(() => {
    fetchAssistantModels()
      .then(res => {
        if (res.models && res.models.length > 0) {
          setAvailableModels(res.models)
          if (res.default) setSelectedModel(res.default)
        }
      })
      .catch(() => {})

    actualizarCuota()
  }, [])

  const actualizarCuota = useCallback(() => {
    fetchChatCuota()
      .then(setCuotaIa)
      .catch(() => {})
  }, [])

  // Cargar listado de conversaciones al abrir o cambiar espacio / pestaña archivadas
  const cargarConversaciones = useCallback(async () => {
    try {
      setCargandoHistorial(true)
      const data = await fetchChatConversaciones(espacioIdActual, verArchivadas)
      setConversaciones(data)
    } catch {
      // Ignorar si no hay sesión
    } finally {
      setCargandoHistorial(false)
    }
  }, [espacioIdActual, verArchivadas])

  useEffect(() => {
    if (isOpen) {
      cargarConversaciones()
      actualizarCuota()
    }
  }, [isOpen, cargarConversaciones, actualizarCuota])

  // Cargar una conversación seleccionada
  const seleccionarConversacion = async (convId: string) => {
    try {
      setLoading(true)
      const detalle = await fetchChatConversacionDetalle(convId)
      setConversacionActivaId(detalle.id)
      setConversacionActivaTitulo(detalle.titulo)

      // Regenerar componentes interactivos a partir de herramienta y argumentos_json
      const cargados: Message[] = detalle.mensajes.map(m => {
        let parsedPayload = undefined
        let parsedFigData = undefined
        let parsedTableData = undefined

        if (m.argumentos_json) {
          try {
            const parsed = JSON.parse(m.argumentos_json)
            if (m.tipo === 'component' || m.herramienta) {
              parsedPayload = parsed
            } else if (m.tipo === 'plotly') {
              parsedFigData = parsed
            } else if (m.tipo === 'df') {
              parsedTableData = Array.isArray(parsed) ? parsed : parsed.data
            }
          } catch {
            // argumento no parseable
          }
        }

        return {
          id: m.id,
          role: m.rol === 'user' ? 'user' : 'assistant',
          content: m.contenido,
          tipo: m.tipo,
          component: m.herramienta,
          payload: parsedPayload,
          fig_data: parsedFigData,
          table_data: parsedTableData,
          dataset_tipo: datasetTipo,
          modelUsed: m.modelo,
          timestamp: new Date(m.creado_en).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        }
      })

      if (cargados.length === 0) {
        setMessages([
          {
            id: `init-${Date.now()}`,
            role: 'assistant',
            content: 'Conversación vacía. ¿Qué deseas consultar hoy?',
            tipo: 'text',
            modelUsed: selectedModel,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ])
      } else {
        setMessages(cargados)
      }
    } catch {
      alert('No se pudo cargar la conversación.')
    } finally {
      setLoading(false)
    }
  }

  // Iniciar nueva conversación en blanco
  const handleNuevaConversacion = async () => {
    setConversacionActivaId(null)
    setConversacionActivaTitulo('Nueva conversación')
    setMessages([
      {
        id: `init-${Date.now()}`,
        role: 'assistant',
        content: `Iniciaste un nuevo hilo analítico para ${datasetTipo === 'estacionamiento' ? 'Estacionamiento' : 'Biblioteca CSF'}. ¿Qué información requieres?`,
        tipo: 'text',
        modelUsed: selectedModel,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ])
  }

  // Renombrar conversación
  const handleGuardarRenombrar = async (convId: string) => {
    if (!nuevoTitulo.trim()) {
      setEditandoConvId(null)
      return
    }
    try {
      await renameChatConversacion(convId, nuevoTitulo.trim())
      if (conversacionActivaId === convId) {
        setConversacionActivaTitulo(nuevoTitulo.trim())
      }
      setEditandoConvId(null)
      setNuevoTitulo('')
      await cargarConversaciones()
    } catch {
      alert('Error al renombrar la conversación.')
    }
  }

  // Archivar o desarchivar conversación
  const handleArchivar = async (convId: string, archivadaActual: boolean) => {
    try {
      await archiveChatConversacion(convId, !archivadaActual)
      await cargarConversaciones()
      if (conversacionActivaId === convId && !archivadaActual) {
        handleNuevaConversacion()
      }
    } catch {
      alert('Error al actualizar el estado de archivo.')
    }
  }

  // Eliminar conversación (borrado lógico)
  const handleEliminar = async (convId: string) => {
    if (!window.confirm('¿Deseas eliminar esta conversación de tu historial?')) return
    try {
      await deleteChatConversacion(convId)
      await cargarConversaciones()
      if (conversacionActivaId === convId) {
        handleNuevaConversacion()
      }
    } catch {
      alert('Error al eliminar la conversación.')
    }
  }

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    }
  }, [isOpen, messages, loading])

  // Envío de mensaje en la conversación activa
  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || input).trim()
    if (!query || loading) return

    if (cuotaIa && cuotaIa.restantes <= 0) {
      alert('Has alcanzado el límite diario de consultas con IA para tu rol. Intenta nuevamente mañana.')
      return
    }

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    const assistantId = `a-${Date.now()}`
    const assistantPlaceholder: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      tipo: 'text',
      dataset_tipo: datasetTipo,
      modelUsed: selectedModel,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    setMessages(prev => [...prev, userMsg, assistantPlaceholder])
    setInput('')
    setLoading(true)

    // Usar ID de conversación activa si existe, o generar un session_id temporal
    const currentSessionId = conversacionActivaId || `uct-sess-${Date.now()}`

    try {
      await sendInteractiveChatStream(
        {
          prompt: query,
          dataset_tipo: datasetTipo,
          session_id: currentSessionId,
          conversacion_id: conversacionActivaId || undefined,
          model: selectedModel,
          grafico_contexto: activeContexto,
          espacio_id: espacioIdActual,
          fecha_inicio: activePeriodo?.startDate,
          fecha_fin: activePeriodo?.endDate,
          periodo_label: activePeriodo?.label,
          filtros: activeFiltros,
        },
        {
          onMeta: (meta) => {
            if (meta.conversacion_id && !conversacionActivaId) {
              setConversacionActivaId(meta.conversacion_id)
            }
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? {
                      ...m,
                      tipo: 'component',
                      component: meta.component,
                      payload: meta.payload,
                    }
                  : m
              )
            )
          },
          onChunk: (chunk) => {
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: m.content + chunk,
                    }
                  : m
              )
            )
          },
          onDone: async () => {
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId && !m.content
                  ? {
                      ...m,
                      content: m.component || m.fig_data ? 'Visualización y métricas generadas para el contexto actual.' : 'Consulta analítica procesada.',
                    }
                  : m
              )
            )
            setLoading(false)
            actualizarCuota()
            await cargarConversaciones()
          },
          onError: async () => {
            try {
              const res = await sendInteractiveChatMessage({
                prompt: query,
                dataset_tipo: datasetTipo,
                session_id: currentSessionId,
                conversacion_id: conversacionActivaId || undefined,
                model: selectedModel,
                grafico_contexto: activeContexto,
                espacio_id: espacioIdActual,
                fecha_inicio: activePeriodo?.startDate,
                fecha_fin: activePeriodo?.endDate,
                periodo_label: activePeriodo?.label,
                filtros: activeFiltros,
              })
              if (res.conversacion_id && !conversacionActivaId) {
                setConversacionActivaId(res.conversacion_id)
              }
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId
                    ? {
                        ...m,
                        content: res?.explicacion || (res?.component || res?.fig_data ? 'Visualización y métricas generadas para el contexto actual.' : 'Consulta analítica procesada.'),
                        tipo: res?.tipo || 'component',
                        component: res?.component,
                        payload: res?.payload,
                        fig_data: res?.fig_data,
                        table_data: res?.table_data,
                        modelUsed: res?.model_used,
                      }
                    : m
                )
              )
            } catch {
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId
                    ? { ...m, content: 'Error de comunicación con el asistente analítico.' }
                    : m
                )
              )
            } finally {
              setLoading(false)
              actualizarCuota()
              await cargarConversaciones()
            }
          },
        }
      )
    } catch {
      setLoading(false)
      actualizarCuota()
    }
  }

  // Exportar PDF
  const handleExportPdf = async () => {
    if (exporting) return
    const idParaPdf = conversacionActivaId || `sesion-${Date.now()}`
    const filename = `Informe_Ejecutivo_DSS_UCT_${idParaPdf.slice(0, 8)}.pdf`
    setExporting(true)
    try {
      await ejecutarDescarga({
        titulo: 'Generación de Informe Ejecutivo PDF',
        subtitulo: `Diálogo analítico • ${conversacionActivaTitulo}`,
        tipo: 'pdf',
        nombreArchivo: filename,
        tarea: async ({ setProgreso }) => {
          setProgreso(20, 'Compilando historial analítico y respuestas...')

          // Capturar imágenes de gráficos renderizados en el DOM
          setProgreso(40, 'Capturando gráficos interactivos generados...')
          const graficosMap: Record<string, string> = {}
          let indiceQ = 1
          for (let i = 0; i < messages.length; i++) {
            const m = messages[i]
            if (m.role === 'assistant') {
              if (m.component || m.fig_data) {
                const b64 = await capturarElementoGrafico(`chart-box-${m.id}`)
                if (b64) {
                  graficosMap[m.id] = b64
                  graficosMap[String(indiceQ)] = b64
                  graficosMap[`consulta_${indiceQ}`] = b64
                }
              }
              indiceQ++
            }
          }

          setProgreso(70, 'Renderizando documento con gráficos y formato institucional UCT...')
          await exportChatPdf(
            idParaPdf,
            `Informe Ejecutivo DSS UCT - ${conversacionActivaTitulo}`,
            conversacionActivaId || undefined,
            graficosMap
          )
          setProgreso(95, 'Descarga del documento PDF finalizada.')
          await new Promise(r => setTimeout(r, 300))
        },
      })
    } catch {
      alert('No se pudo generar el informe en este momento.')
    } finally {
      setExporting(false)
    }
  }

  if (!isOpen) return null

  return (
    <ErrorBoundary>
      <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
        <div
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity"
          onClick={onClose}
        />

        <div className="relative w-full max-w-4xl bg-white h-full shadow-2xl flex flex-row z-10 overflow-hidden">
          {/* Panel Lateral de Historial de Conversaciones */}
          <div
            className={`${
              mostrarHistorialPanel ? 'w-80' : 'w-0'
            } transition-all duration-300 ease-in-out bg-slate-900 text-slate-200 flex flex-col border-r border-slate-800 overflow-hidden shrink-0`}
          >
            <div className="p-3 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <History size={16} className="text-uct-gold" />
                <span className="text-xs font-bold text-white uppercase tracking-wider">Historial de Chats</span>
              </div>
              <button
                onClick={() => setMostrarHistorialPanel(false)}
                title="Ocultar panel de historial"
                className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-800 transition-colors cursor-pointer"
              >
                <ChevronLeft size={16} />
              </button>
            </div>

            <div className="p-3 border-b border-slate-800">
              <button
                onClick={handleNuevaConversacion}
                className="w-full flex items-center justify-center gap-2 bg-uct-gold hover:bg-amber-400 text-uct-blue-primary font-bold text-xs py-2 px-3 rounded-lg shadow-sm transition-all cursor-pointer"
              >
                <Plus size={15} />
                <span>Nueva conversación</span>
              </button>
            </div>

            <div className="flex items-center justify-between px-3 py-1.5 bg-slate-800/60 text-[11px] font-medium border-b border-slate-800">
              <button
                onClick={() => setVerArchivadas(false)}
                className={`px-2 py-1 rounded transition-colors ${
                  !verArchivadas ? 'bg-uct-blue-secondary text-white font-bold' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Activas
              </button>
              <button
                onClick={() => setVerArchivadas(true)}
                className={`px-2 py-1 rounded transition-colors ${
                  verArchivadas ? 'bg-uct-blue-secondary text-white font-bold' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Archivadas
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {cargandoHistorial ? (
                <div className="p-4 text-center text-xs text-slate-400 animate-pulse">Cargando conversaciones...</div>
              ) : conversaciones.length === 0 ? (
                <div className="p-4 text-center text-xs text-slate-400">
                  {verArchivadas ? 'No hay conversaciones archivadas' : 'No tienes conversaciones previas'}
                </div>
              ) : (
                conversaciones.map(conv => {
                  const esActiva = conversacionActivaId === conv.id
                  const estaEditando = editandoConvId === conv.id
                  return (
                    <div
                      key={conv.id}
                      className={`group relative rounded-lg p-2.5 text-xs transition-colors cursor-pointer border ${
                        esActiva
                          ? 'bg-slate-800 border-uct-gold/40 text-white'
                          : 'bg-slate-900/80 border-slate-800/80 hover:bg-slate-800/60 text-slate-300'
                      }`}
                      onClick={() => !estaEditando && seleccionarConversacion(conv.id)}
                    >
                      {estaEditando ? (
                        <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
                          <input
                            type="text"
                            value={nuevoTitulo}
                            onChange={e => setNuevoTitulo(e.target.value)}
                            className="flex-1 bg-slate-950 text-white text-xs px-2 py-1 rounded border border-uct-gold focus:outline-none"
                            autoFocus
                            onKeyDown={e => {
                              if (e.key === 'Enter') handleGuardarRenombrar(conv.id)
                              if (e.key === 'Escape') setEditandoConvId(null)
                            }}
                          />
                          <button
                            onClick={() => handleGuardarRenombrar(conv.id)}
                            className="p-1 text-emerald-400 hover:text-emerald-300"
                            title="Guardar título"
                          >
                            <Check size={14} />
                          </button>
                          <button
                            onClick={() => setEditandoConvId(null)}
                            className="p-1 text-slate-400 hover:text-slate-200"
                            title="Cancelar"
                          >
                            <X size={14} />
                          </button>
                        </div>
                      ) : (
                        <div>
                          <div className="flex items-center justify-between gap-1.5">
                            <span className="font-semibold truncate text-[12px] text-slate-100">{conv.titulo}</span>
                            <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-opacity">
                              <button
                                onClick={e => {
                                  e.stopPropagation()
                                  setEditandoConvId(conv.id)
                                  setNuevoTitulo(conv.titulo)
                                }}
                                title="Renombrar"
                                className="p-1 text-slate-400 hover:text-white rounded hover:bg-slate-700"
                              >
                                <Edit2 size={11} />
                              </button>
                              <button
                                onClick={e => {
                                  e.stopPropagation()
                                  handleArchivar(conv.id, conv.archivada)
                                }}
                                title={conv.archivada ? 'Desarchivar' : 'Archivar'}
                                className="p-1 text-slate-400 hover:text-white rounded hover:bg-slate-700"
                              >
                                {conv.archivada ? <ArchiveRestore size={11} /> : <Archive size={11} />}
                              </button>
                              <button
                                onClick={e => {
                                  e.stopPropagation()
                                  handleEliminar(conv.id)
                                }}
                                title="Eliminar"
                                className="p-1 text-rose-400 hover:text-rose-300 rounded hover:bg-slate-700"
                              >
                                <Trash2 size={11} />
                              </button>
                            </div>
                          </div>
                          <div className="flex items-center justify-between text-[10px] text-slate-500 mt-1">
                            <span>
                              {conv.espacio_id === 2 ? 'Estacionamiento' : 'Biblioteca'}
                            </span>
                            <span>{new Date(conv.actualizada_en).toLocaleDateString([], { month: 'short', day: 'numeric' })}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Área Principal del Chat */}
          <div className="flex-1 flex flex-col bg-white h-full overflow-hidden">
            {/* Cabecera Principal */}
            <div className="bg-uct-blue-primary text-white p-4 flex flex-col gap-2.5 border-b border-white/10 shrink-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  {!mostrarHistorialPanel && (
                    <button
                      onClick={() => setMostrarHistorialPanel(true)}
                      title="Abrir historial de conversaciones"
                      className="bg-white/10 hover:bg-white/20 text-uct-gold p-1.5 rounded-lg border border-white/10 transition-colors cursor-pointer mr-1"
                    >
                      <History size={17} />
                    </button>
                  )}
                  <div className="w-8 h-8 rounded-lg bg-uct-gold flex items-center justify-center text-uct-blue-primary font-black shadow-xs">
                    <Sparkles size={18} />
                  </div>
                  <div>
                    <h2 className="text-sm font-bold flex items-center gap-2 truncate max-w-sm">
                      {conversacionActivaId ? conversacionActivaTitulo : 'Asistente IA · Sistema DSS'}
                      <span className="text-[10px] bg-uct-gold/20 text-uct-gold border border-uct-gold/30 px-1.5 py-0.5 rounded-full uppercase tracking-wider font-semibold">
                        UCT CSF
                      </span>
                    </h2>
                    <p className="text-[11px] text-white/70">
                      Visualización dinámica con regeneración en cliente
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  {cuotaIa && (
                    <div
                      title="Cuota diaria de consultas analíticas IA"
                      className="hidden sm:flex items-center gap-1.5 bg-white/10 text-white/90 text-[11px] px-2.5 py-1.5 rounded-lg border border-white/10"
                    >
                      <Clock size={12} className="text-uct-gold" />
                      <span>
                        Cuota hoy: <strong>{cuotaIa.usadas}</strong>/{cuotaIa.limite}{' '}
                        <span className="text-emerald-300 font-semibold">({cuotaIa.restantes} disp.)</span>
                      </span>
                    </div>
                  )}

                  <button
                    onClick={handleExportPdf}
                    disabled={exporting}
                    title="Descargar informe ejecutivo en PDF"
                    className="flex items-center gap-1.5 bg-white/10 hover:bg-white/20 text-white text-xs px-2.5 py-1.5 rounded-lg border border-white/20 transition-all cursor-pointer disabled:opacity-50"
                  >
                    <Download size={13} className={exporting ? 'animate-bounce' : ''} />
                    <span className="hidden md:inline font-medium">{exporting ? 'Exportando...' : 'Informe PDF'}</span>
                  </button>
                  <button
                    onClick={handleNuevaConversacion}
                    title="Iniciar nuevo chat"
                    className="p-1.5 text-white/70 hover:text-white hover:bg-white/10 rounded-lg transition-colors cursor-pointer"
                  >
                    <Plus size={17} />
                  </button>
                  <button
                    onClick={onClose}
                    title="Cerrar panel"
                    className="p-1.5 text-white/70 hover:text-white hover:bg-white/10 rounded-lg transition-colors cursor-pointer"
                  >
                    <X size={18} />
                  </button>
                </div>
              </div>

              {/* Selector de módulo y modelo */}
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="flex items-center justify-between bg-white/10 px-3 py-1.5 rounded-lg border border-white/10">
                  <span className="text-white/70 font-medium">Módulo:</span>
                  <select
                    value={datasetTipo}
                    onChange={e => {
                      const nuevoTipo = e.target.value as DatasetType
                      setDatasetTipo(nuevoTipo)
                      handleClearContext()
                    }}
                    disabled={!puedeAccederBiblioteca || !puedeAccederEstacionamiento}
                    title={
                      !puedeAccederBiblioteca || !puedeAccederEstacionamiento
                        ? 'Módulo asignado según sus permisos de acceso'
                        : 'Seleccionar módulo analítico'
                    }
                    className="bg-uct-blue-secondary text-white text-xs font-semibold px-2 py-0.5 rounded border border-white/20 focus:outline-none cursor-pointer disabled:opacity-80 disabled:cursor-not-allowed"
                  >
                    {puedeAccederBiblioteca && <option value="biblioteca">Biblioteca CSF</option>}
                    {puedeAccederEstacionamiento && <option value="estacionamiento">Estacionamiento</option>}
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

            {/* Advertencia de Privacidad según Ley N° 21.719 */}
            <div className="bg-blue-50/90 border-b border-blue-200 px-4 py-2 flex items-start gap-2.5 text-[11px] text-blue-950 shrink-0">
              <ShieldAlert size={15} className="text-blue-700 shrink-0 mt-0.5" />
              <div className="flex-1 leading-tight">
                <span className="font-bold text-blue-900">Aviso de Privacidad (Ley N° 21.719):</span> Los registros de
                asistencia y vehículos se procesan estrictamente seudonimizados bajo HMAC/SHA-256. Las consultas son
                auditadas institucionalmente con fines de soporte a la gestión. Queda estrictamente prohibido ingresar
                datos personales sensibles.
              </div>
            </div>

            {/* Contexto del Gráfico Activo */}
            {(activeContexto || activePeriodo?.label) && (
              <div className="bg-gradient-to-r from-amber-50 to-amber-100/50 border-b border-amber-200 px-4 py-2 flex items-center justify-between text-xs shrink-0">
                <div className="flex items-center gap-2 text-amber-950 flex-wrap">
                  <Sparkles size={14} className="text-amber-600 shrink-0 animate-pulse" />
                  {activeContexto && (
                    <span>
                      Foco analítico:{' '}
                      <span className="font-bold underline decoration-amber-400 text-[12px]">
                        {formatContextName(activeContexto)}
                      </span>
                    </span>
                  )}
                  {activePeriodo?.label && (
                    <span className="bg-amber-200/70 text-amber-900 px-2 py-0.5 rounded text-[10px] font-semibold border border-amber-300">
                      Período: {activePeriodo.label}
                    </span>
                  )}
                </div>
                {activeContexto && (
                  <button
                    onClick={handleClearContext}
                    className="text-amber-700 hover:text-amber-900 text-[11px] font-semibold px-2 py-0.5 rounded hover:bg-amber-200/70 transition-colors cursor-pointer"
                    title="Quitar filtro de contexto"
                  >
                    Desvincular
                  </button>
                )}
              </div>
            )}

            {/* Sugerencias Rápidas */}
            <div className="bg-slate-50 border-b border-slate-200 px-4 py-2 shrink-0">
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                Sugerencias Analíticas ({datasetTipo})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {activeContexto && (
                  <button
                    onClick={() =>
                      handleSendMessage(
                        `Analiza detalladamente las métricas y tendencias del gráfico "${formatContextName(
                          activeContexto
                        )}"`
                      )
                    }
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
                    className="text-[11px] bg-white text-slate-700 hover:text-uct-blue-primary hover:border-uct-blue-primary/40 border border-slate-200 px-2.5 py-0.5 rounded-full transition-all shadow-2xs hover:shadow-xs disabled:opacity-50 cursor-pointer text-left"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>

            {/* Lista de Mensajes con Regeneración de Gráficos */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50/50">
              {messages.map((msg, idx) => {
                const preguntaTexto = idx > 0 && messages[idx - 1].role === 'user'
                  ? messages[idx - 1].content
                  : undefined
                return (
                  <ChatMessage
                    key={msg.id}
                    msg={msg}
                    preguntaTexto={preguntaTexto}
                    espacioId={datasetTipo === 'estacionamiento' ? 2 : 1}
                  />
                )
              })}

              <div ref={chatEndRef} />
            </div>

            {/* Formulario de Entrada */}
            <div className="p-3 bg-white border-t border-slate-200 shrink-0">
              {cuotaIa && cuotaIa.restantes <= 0 ? (
                <div className="flex items-center gap-2 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs mb-2">
                  <AlertCircle size={16} className="text-rose-600 shrink-0" />
                  <span>Has agotado tu cuota diaria de IA ({cuotaIa.limite} consultas). Podrás consultar nuevamente mañana.</span>
                </div>
              ) : null}

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
                  disabled={loading || (cuotaIa !== null && cuotaIa.restantes <= 0)}
                  className="flex-1 text-xs bg-slate-50 border border-slate-300 rounded-xl px-3 py-2.5 text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-uct-blue-primary focus:border-uct-blue-primary disabled:opacity-60"
                />
                <button
                  type="submit"
                  disabled={loading || !input.trim() || (cuotaIa !== null && cuotaIa.restantes <= 0)}
                  className="bg-uct-blue-primary hover:bg-uct-blue-secondary text-white p-2.5 rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer shrink-0 shadow-xs"
                >
                  <Send size={15} />
                </button>
              </form>

              <div className="flex items-center justify-between mt-1.5 text-[10px] text-slate-400">
                <span className="flex items-center gap-1">
                  <MessageSquare size={10} />
                  <span>{conversacionActivaId ? `Conversación: ${conversacionActivaId.slice(0, 8)}` : 'Nueva conversación'}</span>
                </span>
                <span>Persistencia SQL Server · DSS UCT Campus San Francisco</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </ErrorBoundary>
  )
}

export default AssistantDrawer
