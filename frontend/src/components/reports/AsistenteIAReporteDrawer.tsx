import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  Sparkles,
  History,
  FileText,
  Plus,
  X,
  Send,
  ShieldCheck,
  Bot,
  Loader2,
  MessageSquare,
} from 'lucide-react'
import {
  MensajeIAReporteItem,
  ReporteCompartidoResumen,
  consultarIAReportePublico,
  fetchHistorialIAReportePublico,
} from '../../api/reportesCompartidos'
import { MarkdownRespuestaIA, markdownAHtmlSeguro } from '../ui/MarkdownRespuestaIA'

interface AsistenteIAReporteDrawerProps {
  tokenAcceso: string
  reporte: ReporteCompartidoResumen
  mensajesIniciales?: MensajeIAReporteItem[]
}

const SUGERENCIAS_BIBLIOTECA = [
  '¿Cuáles fueron los principales hallazgos de asistencia?',
  'Resume la distribución por carreras y facultades',
  '¿Cómo se comportó el aforo y la hora pico en este período?',
  '¿Qué recomiendas destacar en el informe ejecutivo?',
]

const SUGERENCIAS_ESTACIONAMIENTO = [
  '¿Cuál fue el flujo vehicular y la hora punta del período?',
  'Resume la composición de flota y rotación diaria',
  '¿Qué sector o pórtico concentró la mayor demanda?',
  '¿Qué conclusiones ejecutivas arrojan los clusters de estadía?',
]

function formatearHora(iso?: string | null): string {
  if (!iso) {
    return new Date().toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })
  }
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })
}

export const AsistenteIAReporteDrawer: React.FC<AsistenteIAReporteDrawerProps> = ({
  tokenAcceso,
  reporte,
  mensajesIniciales = [],
}) => {
  const [abierto, setAbierto] = useState(false)
  const [vistaHistorial, setVistaHistorial] = useState(false)
  const [mensajes, setMensajes] = useState<MensajeIAReporteItem[]>(mensajesIniciales)
  const [sesionActiva, setSesionActiva] = useState<string>('principal')
  const [pregunta, setPregunta] = useState('')
  const [consultando, setConsultando] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [cargandoHistorial, setCargandoHistorial] = useState(false)
  const finListaRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    setMensajes(mensajesIniciales)
    const sesiones = Array.from(new Set(mensajesIniciales.map((m) => m.sesion_id || 'principal')))
    setSesionActiva(sesiones.length > 0 ? sesiones[sesiones.length - 1] : 'principal')
    setVistaHistorial(false)
    setErrorMsg(null)
  }, [tokenAcceso, reporte.id, mensajesIniciales])

  useEffect(() => {
    if (abierto && finListaRef.current) {
      finListaRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [abierto, mensajes.length, sesionActiva])

  const sesionesDisponibles = useMemo(() => {
    const mapa = new Map<string, { id: string; primerPrompt: string; count: number; ultimaFecha: string | null }>()
    for (const m of mensajes) {
      const sid = m.sesion_id || 'principal'
      const cur = mapa.get(sid)
      if (!cur) {
        mapa.set(sid, {
          id: sid,
          primerPrompt: m.pregunta,
          count: 1,
          ultimaFecha: m.creado_en,
        })
      } else {
        cur.count += 1
        cur.ultimaFecha = m.creado_en
      }
    }
    return Array.from(mapa.values()).reverse()
  }, [mensajes])

  const mensajesSesion = useMemo(
    () => mensajes.filter((m) => (m.sesion_id || 'principal') === sesionActiva),
    [mensajes, sesionActiva]
  )

  const sugerencias = reporte.espacio_id === 1 ? SUGERENCIAS_BIBLIOTECA : SUGERENCIAS_ESTACIONAMIENTO

  const recargarHistorial = async () => {
    setCargandoHistorial(true)
    try {
      const res = await fetchHistorialIAReportePublico(tokenAcceso)
      setMensajes(res.mensajes || [])
    } catch {
      // Mantiene historial actual si falla recarga puntual
    } finally {
      setCargandoHistorial(false)
    }
  }

  const enviarConsulta = async (textoPregunta: string) => {
    const limpia = textoPregunta.trim()
    if (!limpia || consultando) return
    setConsultando(true)
    setErrorMsg(null)
    setPregunta('')
    setVistaHistorial(false)
    try {
      const res = await consultarIAReportePublico(tokenAcceso, limpia, sesionActiva)
      const nuevo: MensajeIAReporteItem = {
        id: res.id,
        sesion_id: res.sesion_id || sesionActiva,
        pregunta: res.pregunta || limpia,
        respuesta: res.respuesta,
        modelo_utilizado: res.modelo_utilizado,
        tiempo_respuesta_ms: res.tiempo_respuesta_ms,
        creado_en: res.timestamp,
      }
      setMensajes((prev) => [...prev, nuevo])
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No fue posible procesar la consulta con el asistente IA.')
      setPregunta(limpia)
    } finally {
      setConsultando(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    enviarConsulta(pregunta)
  }

  const iniciarNuevaConversacion = () => {
    const nuevaId = `sesion_${Date.now()}`
    setSesionActiva(nuevaId)
    setVistaHistorial(false)
    setErrorMsg(null)
  }

  const exportarConversacionPDF = () => {
    const win = window.open('', '_blank', 'width=900,height=700')
    if (!win) return
    const itemsHtml = mensajesSesion
      .map(
        (m) => `
        <div style="margin-bottom:14px;border:1px solid #e2e8f0;border-radius:8px;padding:12px;">
          <div style="font-weight:700;color:#003865;margin-bottom:6px;">Consulta (${formatearHora(m.creado_en)}): ${m.pregunta
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')}</div>
          <div>${markdownAHtmlSeguro(m.respuesta)}</div>
        </div>`
      )
      .join('')
    win.document.write(`<!doctype html><html><head><title>Conversación IA — ${reporte.codigo_corto}</title></head>
      <body style="font-family:Segoe UI,Arial,sans-serif;padding:24px;color:#0f172a;">
        <h2 style="color:#003865;margin-bottom:4px;">Síntesis Asistente IA — ${reporte.titulo_reporte}</h2>
        <p style="font-size:12px;color:#475569;margin-top:0;">Código: ${reporte.codigo_corto} | Módulo: ${reporte.espacio_nombre} | Período: ${reporte.fecha_inicio} al ${reporte.fecha_fin}</p>
        <hr style="margin:16px 0;border:none;border-top:1px solid #cbd5e1;" />
        ${itemsHtml || '<p>Sin consultas registradas en esta conversación.</p>'}
      </body></html>`)
    win.document.close()
    win.focus()
    win.print()
  }

  return (
    <>
      {!abierto && (
        <button
          type="button"
          onClick={() => {
            setAbierto(true)
            recargarHistorial()
          }}
          className="no-imprimir-reporte print:hidden fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-4 py-3 rounded-full bg-uct-blue-primary hover:bg-uct-blue-secondary text-white shadow-xl border-2 border-uct-gold/70 text-xs font-bold transition-all cursor-pointer"
          title="Abrir Asistente IA acotado a este Reporte Ejecutivo"
        >
          <Sparkles className="w-4 h-4 text-uct-gold" />
          <span>Asistente IA</span>
          {mensajes.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-full bg-uct-gold text-uct-blue-primary text-[10px] font-extrabold leading-none">
              {mensajes.length}
            </span>
          )}
        </button>
      )}

      {abierto && (
        <div className="no-imprimir-reporte print:hidden fixed inset-0 z-50 flex justify-end bg-slate-900/30 backdrop-blur-[1px]">
          <aside className="w-full max-w-[540px] h-full bg-white shadow-2xl border-l border-slate-200 flex flex-col">
            {/* Cabecera Institucional azul UCT */}
            <div className="bg-uct-blue-primary text-white px-4 py-3 border-b border-white/10">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2.5 min-w-0">
                  <button
                    type="button"
                    onClick={() => setVistaHistorial((v) => !v)}
                    className={`p-1.5 rounded-lg border transition cursor-pointer ${
                      vistaHistorial
                        ? 'bg-uct-gold text-uct-blue-primary border-uct-gold'
                        : 'bg-white/10 hover:bg-white/20 text-white border-white/15'
                    }`}
                    title="Ver historial de conversaciones del reporte"
                  >
                    <History className="w-4 h-4" />
                  </button>
                  <div className="w-8 h-8 rounded-lg bg-uct-gold/20 border border-uct-gold/50 flex items-center justify-center shrink-0">
                    <Sparkles className="w-4 h-4 text-uct-gold" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-xs sm:text-sm font-bold truncate">
                        Asistente IA · Reporte Ejecutivo
                      </h3>
                      <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-uct-gold/20 text-uct-gold border border-uct-gold/40 shrink-0">
                        {reporte.codigo_corto}
                      </span>
                    </div>
                    <p className="text-[11px] text-white/75 truncate">
                      Alcance confinado exclusivamente a este informe
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    type="button"
                    onClick={exportarConversacionPDF}
                    disabled={mensajesSesion.length === 0}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-40 text-white border border-white/20 text-[11px] font-semibold cursor-pointer"
                    title="Imprimir o guardar conversación como PDF"
                  >
                    <FileText className="w-3.5 h-3.5 text-uct-gold" />
                    <span className="hidden sm:inline">Informe PDF</span>
                  </button>
                  <button
                    type="button"
                    onClick={iniciarNuevaConversacion}
                    className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white border border-white/15 cursor-pointer"
                    title="Nueva conversación"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setAbierto(false)}
                    className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white border border-white/15 cursor-pointer"
                    title="Cerrar panel"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <div className="mt-2.5 pt-2 border-t border-white/10 flex flex-wrap items-center justify-between gap-2 text-[11px]">
                <span className="text-white/80">
                  Módulo: <strong className="text-uct-gold">{reporte.espacio_nombre}</strong>
                </span>
                <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 font-semibold text-[10px]">
                  Período sellado: {reporte.fecha_inicio} al {reporte.fecha_fin}
                </span>
              </div>
            </div>

            {/* Aviso privacidad Ley 21.719 */}
            <div className="px-4 py-2 bg-blue-50/70 border-b border-blue-100 flex items-start gap-2 text-[11px] text-slate-700">
              <ShieldCheck className="w-4 h-4 text-uct-blue-primary shrink-0 mt-0.5" />
              <span>
                <strong>Aviso de Privacidad (Ley N° 21.719):</strong> Respuestas acotadas únicamente a indicadores y
                notas del reporte {reporte.codigo_corto}. Las consultas quedan auditadas y persistidas en el sistema.
              </span>
            </div>

            {/* Cuerpo principal: historial de sesiones o conversación activa */}
            {vistaHistorial ? (
              <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-uct-blue-primary uppercase tracking-wider">
                    Conversaciones Guardadas ({sesionesDisponibles.length})
                  </h4>
                  <button
                    type="button"
                    onClick={() => setVistaHistorial(false)}
                    className="text-xs font-semibold text-uct-blue-primary hover:underline cursor-pointer"
                  >
                    Volver al chat
                  </button>
                </div>

                {cargandoHistorial ? (
                  <div className="py-10 text-center text-xs text-slate-500">Cargando historial...</div>
                ) : sesionesDisponibles.length === 0 ? (
                  <div className="py-10 text-center text-xs text-slate-500 bg-white rounded-xl border border-slate-200 p-4">
                    Aún no existen conversaciones previas guardadas en este reporte.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {sesionesDisponibles.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => {
                          setSesionActiva(s.id)
                          setVistaHistorial(false)
                        }}
                        className={`w-full text-left p-3 rounded-xl border transition cursor-pointer ${
                          s.id === sesionActiva
                            ? 'bg-blue-50 border-uct-blue-primary text-uct-blue-primary'
                            : 'bg-white border-slate-200 hover:border-slate-300 text-slate-800'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 text-[11px] font-semibold">
                          <span className="flex items-center gap-1.5">
                            <MessageSquare className="w-3.5 h-3.5" />
                            {s.count} {s.count === 1 ? 'consulta' : 'consultas'}
                          </span>
                          <span className="text-slate-400">{formatearHora(s.ultimaFecha)}</span>
                        </div>
                        <p className="text-xs font-medium mt-1 line-clamp-2">{s.primerPrompt}</p>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50/70">
                {/* Sugerencias rápidas */}
                <div className="space-y-1.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                    Sugerencias Analíticas ({reporte.espacio_nombre})
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {sugerencias.map((sug, i) => (
                      <button
                        key={i}
                        type="button"
                        disabled={consultando}
                        onClick={() => enviarConsulta(sug)}
                        className="px-2.5 py-1 rounded-full bg-white hover:bg-blue-50 border border-slate-200 hover:border-uct-blue-primary/40 text-[11px] text-slate-700 hover:text-uct-blue-primary transition cursor-pointer disabled:opacity-50"
                      >
                        {sug}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Saludo inicial */}
                <div className="flex items-start gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0 text-uct-blue-primary">
                    <Bot className="w-4 h-4" />
                  </div>
                  <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-xs px-3.5 py-2.5 text-xs text-slate-700 shadow-2xs max-w-[88%]">
                    <p>
                      Hola. Soy tu Asistente Analítico para este Reporte Ejecutivo (<strong>{reporte.codigo_corto}</strong>).
                      Puedo interpretar sus indicadores, resumir tendencias del período y aclarar las notas registradas.
                    </p>
                  </div>
                </div>

                {/* Mensajes persistidos */}
                {mensajesSesion.map((m, idx) => (
                  <div key={m.id || idx} className="space-y-2.5">
                    <div className="flex justify-end">
                      <div className="bg-uct-blue-primary text-white rounded-2xl rounded-tr-xs px-3.5 py-2 text-xs max-w-[85%] shadow-2xs">
                        <p>{m.pregunta}</p>
                        <span className="block text-[10px] text-white/70 mt-1 text-right">
                          {formatearHora(m.creado_en)}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-start gap-2.5">
                      <div className="w-7 h-7 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0 text-uct-blue-primary">
                        <Bot className="w-4 h-4" />
                      </div>
                      <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-xs px-3.5 py-2.5 text-xs text-slate-800 shadow-2xs max-w-[88%] space-y-1.5">
                        <MarkdownRespuestaIA contenido={m.respuesta} />
                        <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-100">
                          <span>{formatearHora(m.creado_en)}</span>
                          <span className="font-mono">{m.modelo_utilizado || 'IA DSS'}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}

                {consultando && (
                  <div className="flex items-center gap-2 text-xs text-uct-blue-primary bg-white border border-slate-200 rounded-xl px-3.5 py-2.5 w-fit">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Analizando cifras selladas del reporte...</span>
                  </div>
                )}

                {errorMsg && (
                  <div className="p-2.5 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">
                    {errorMsg}
                  </div>
                )}
                <div ref={finListaRef} />
              </div>
            )}

            {/* Pie de composición */}
            <div className="p-3 bg-white border-t border-slate-200 space-y-2">
              <form onSubmit={handleSubmit} className="flex items-center gap-2">
                <input
                  type="text"
                  value={pregunta}
                  onChange={(e) => setPregunta(e.target.value)}
                  disabled={consultando}
                  placeholder="Pregunta sobre los indicadores o gráficos de este reporte..."
                  className="flex-1 bg-slate-50 border border-slate-300 rounded-xl px-3 py-2 text-xs text-slate-800 focus:outline-none focus:border-uct-blue-primary"
                />
                <button
                  type="submit"
                  disabled={consultando || !pregunta.trim()}
                  className="p-2.5 rounded-xl bg-uct-blue-primary hover:bg-uct-blue-secondary disabled:opacity-40 text-white cursor-pointer"
                  title="Enviar consulta"
                >
                  <Send className="w-4 h-4 text-uct-gold" />
                </button>
              </form>
              <div className="flex items-center justify-between text-[10px] text-slate-400">
                <button
                  type="button"
                  onClick={iniciarNuevaConversacion}
                  className="hover:text-uct-blue-primary font-semibold flex items-center gap-1 cursor-pointer"
                >
                  <Plus className="w-3 h-3" />
                  Nueva conversación
                </button>
                <span>Persistencia SQL Server · DSS UCT Campus San Francisco</span>
              </div>
            </div>
          </aside>
        </div>
      )}
    </>
  )
}
