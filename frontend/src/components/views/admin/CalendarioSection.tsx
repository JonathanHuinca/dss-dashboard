import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Calendar,
  RefreshCw,
  Plus,
  Trash2,
  Edit2,
  Search,
  CheckCircle2,
  AlertCircle,
  Clock,
  Sparkles,
  X,
  Save,
  Globe,
  Sliders,
  ExternalLink,
} from 'lucide-react'
import {
  fetchCalendarEvents,
  syncCalendarScrape,
  depurarCalendarBasura,
  actualizarEventoCalendario,
  crearEventoCalendario,
  eliminarEventoCalendario,
  EventoCalendarioDetalle,
  EventoCalendarioFormulario,
  EventoCalendarioCrearFormulario,
} from '../../../api/administracion'

const formatIsoDate = (isoStr?: string | null): string => {
  if (!isoStr) return ''
  const parts = String(isoStr).slice(0, 10).split('-')
  if (parts.length === 3) {
    const [y, m, d] = parts
    return `${d}/${m}/${y}`
  }
  return isoStr
}

export const CalendarioSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [anioSeleccionado, setAnioSeleccionado] = useState<number>(2026)
  const [categoriaFiltro, setCategoriaFiltro] = useState<string>('')
  const [busqueda, setBusqueda] = useState<string>('')
  const [agruparPeriodos, setAgruparPeriodos] = useState<boolean>(true)

  // Estados de modales
  const [eventoEditando, setEventoEditando] = useState<EventoCalendarioDetalle | null>(null)
  const [modalNuevoAbierto, setModalNuevoAbierto] = useState<boolean>(false)
  const [mensajeFeedback, setMensajeFeedback] = useState<{ tipo: 'ok' | 'error'; texto: string } | null>(null)

  // Consulta de eventos
  const { data: eventos = [], isLoading, refetch } = useQuery({
    queryKey: ['admin-calendar-events', anioSeleccionado, categoriaFiltro, busqueda, agruparPeriodos],
    queryFn: () =>
      fetchCalendarEvents({
        anio: anioSeleccionado,
        categoria: categoriaFiltro || undefined,
        busqueda: busqueda || undefined,
        agrupar_periodos: agruparPeriodos,
      }),
  })

  // Mutación: Scraping Web
  const mutationScrape = useMutation({
    mutationFn: syncCalendarScrape,
    onSuccess: (data) => {
      setMensajeFeedback({
        tipo: 'ok',
        texto: `Sincronización web completada: ${data.total_days} días procesados desde el calendario oficial.`,
      })
      queryClient.invalidateQueries({ queryKey: ['admin-calendar-events'] })
      queryClient.invalidateQueries({ queryKey: ['calendario-resumen-anual'] })
    },
    onError: (err: any) => {
      setMensajeFeedback({
        tipo: 'error',
        texto: err?.response?.data?.detail || 'Error al conectar con el portal de calendario UCT.',
      })
    },
  })

  // Mutación: Depurar Basura
  const mutationDepurar = useMutation({
    mutationFn: depurarCalendarBasura,
    onSuccess: (data) => {
      setMensajeFeedback({ tipo: 'ok', texto: data.mensaje })
      queryClient.invalidateQueries({ queryKey: ['admin-calendar-events'] })
      queryClient.invalidateQueries({ queryKey: ['calendario-resumen-anual'] })
    },
    onError: (err: any) => {
      setMensajeFeedback({
        tipo: 'error',
        texto: err?.response?.data?.detail || 'Error al depurar registros.',
      })
    },
  })

  // Mutación: Actualizar Evento
  const mutationActualizar = useMutation({
    mutationFn: ({ fecha, datos }: { fecha: string; datos: EventoCalendarioFormulario }) =>
      actualizarEventoCalendario(fecha, datos),
    onSuccess: () => {
      setMensajeFeedback({ tipo: 'ok', texto: 'Hito actualizado exitosamente en la base de datos.' })
      setEventoEditando(null)
      queryClient.invalidateQueries({ queryKey: ['admin-calendar-events'] })
      queryClient.invalidateQueries({ queryKey: ['calendario-resumen-anual'] })
    },
    onError: (err: any) => {
      setMensajeFeedback({
        tipo: 'error',
        texto: err?.response?.data?.detail || 'Error al guardar modificaciones.',
      })
    },
  })

  // Mutación: Crear Evento
  const mutationCrear = useMutation({
    mutationFn: (datos: EventoCalendarioCrearFormulario) => crearEventoCalendario(datos),
    onSuccess: (data) => {
      setMensajeFeedback({ tipo: 'ok', texto: data.mensaje })
      setModalNuevoAbierto(false)
      queryClient.invalidateQueries({ queryKey: ['admin-calendar-events'] })
      queryClient.invalidateQueries({ queryKey: ['calendario-resumen-anual'] })
    },
    onError: (err: any) => {
      setMensajeFeedback({
        tipo: 'error',
        texto: err?.response?.data?.detail || 'Error al crear nuevo hito.',
      })
    },
  })

  // Mutación: Eliminar Evento
  const mutationEliminar = useMutation({
    mutationFn: (fecha: string) => eliminarEventoCalendario(fecha),
    onSuccess: () => {
      setMensajeFeedback({ tipo: 'ok', texto: 'Evento eliminado del calendario.' })
      queryClient.invalidateQueries({ queryKey: ['admin-calendar-events'] })
      queryClient.invalidateQueries({ queryKey: ['calendario-resumen-anual'] })
    },
    onError: (err: any) => {
      setMensajeFeedback({
        tipo: 'error',
        texto: err?.response?.data?.detail || 'Error al eliminar el evento.',
      })
    },
  })

  // Formulario temporal de edición
  const [formEdit, setFormEdit] = useState<EventoCalendarioFormulario>({
    descripcion: '',
    is_holiday: false,
    is_break: false,
    is_exam_period: false,
    is_class_milestone: false,
    suspension_actividades: false,
    is_strike_federado: false,
    is_strike_carrera: false,
  })

  const abrirEdicion = (evento: EventoCalendarioDetalle) => {
    setEventoEditando(evento)
    setFormEdit({
      descripcion: evento.descripcion || '',
      is_holiday: Boolean(evento.is_holiday),
      is_break: Boolean(evento.is_break),
      is_exam_period: Boolean(evento.is_exam_period),
      is_class_milestone: Boolean(evento.is_class_milestone),
      suspension_actividades: Boolean(evento.suspension_actividades),
      is_strike_federado: Boolean(evento.is_strike_federado),
      is_strike_carrera: Boolean(evento.is_strike_carrera),
      tipo_contingencia: evento.tipo_dia === 'paro_federado' ? 'paro_federado' : evento.tipo_dia === 'paro_carrera' ? 'paro_carrera' : null,
    })
  }

  // Formulario nuevo evento
  const [formNuevo, setFormNuevo] = useState<EventoCalendarioCrearFormulario>({
    fecha_inicio: new Date().toISOString().slice(0, 10),
    fecha_fin: new Date().toISOString().slice(0, 10),
    descripcion: '',
    is_holiday: false,
    is_break: false,
    is_exam_period: false,
    is_class_milestone: false,
    suspension_actividades: false,
    is_strike_federado: false,
    is_strike_carrera: false,
  })

  return (
    <div className="space-y-6">
      {/* Banner Superior Explicativo */}
      <div className="bg-gradient-to-r from-uct-blue-primary/10 via-sky-50 to-white border border-slate-200/90 rounded-3xl p-5 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-2xl bg-uct-blue-primary/15 flex items-center justify-center text-uct-blue-primary shadow-2xs">
              <Calendar size={22} />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 tracking-tight">
                Calendario Académico e Hitos Institucionales
              </h2>
              <p className="text-xs text-slate-500 max-w-2xl mt-0.5">
                Los eventos recolectados mediante web scraping o edición manual alimentan las capas visuales del panel y actúan como regresores exógenos para los pronósticos de demanda con Prophet y Gradient Boosting.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <a
              href="https://www.uct.cl/calendario-academico/"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-slate-700 bg-white hover:text-uct-blue-primary hover:bg-slate-50 border border-slate-200 transition shadow-2xs"
              title="Abrir el portal oficial del calendario académico de la Universidad Católica de Temuco"
            >
              <ExternalLink size={13} className="text-slate-400" />
              <span>Fuente Oficial UCT</span>
            </a>

            <button
              type="button"
              disabled={mutationScrape.isPending}
              onClick={() => mutationScrape.mutate()}
              className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold bg-white text-uct-blue-primary hover:bg-slate-50 border border-slate-200 transition shadow-2xs cursor-pointer disabled:opacity-50"
              title="Descargar y sincronizar hitos desde https://www.uct.cl/calendario-academico/"
            >
              <Globe size={14} className={mutationScrape.isPending ? 'animate-spin' : ''} />
              <span>{mutationScrape.isPending ? 'Sincronizando...' : 'Scraping Web UCT'}</span>
            </button>

            <button
              type="button"
              disabled={mutationDepurar.isPending}
              onClick={() => mutationDepurar.mutate()}
              className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold bg-white text-slate-700 hover:bg-slate-50 border border-slate-200 transition shadow-2xs cursor-pointer disabled:opacity-50"
              title="Eliminar trámites o fechas irrelevantes sin impacto presencial"
            >
              <Sparkles size={14} className="text-amber-500" />
              <span>Depurar Irrelevantes</span>
            </button>

            <button
              type="button"
              onClick={() => setModalNuevoAbierto(true)}
              className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold bg-uct-blue-primary text-white hover:bg-uct-blue-secondary transition shadow-xs cursor-pointer"
            >
              <Plus size={14} />
              <span>Agregar Hito Manual</span>
            </button>
          </div>
        </div>
      </div>

      {/* Alerta de Feedback */}
      {mensajeFeedback && (
        <div
          className={`p-3.5 rounded-2xl border text-xs font-semibold flex items-center justify-between gap-3 ${
            mensajeFeedback.tipo === 'ok'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          <div className="flex items-center gap-2">
            {mensajeFeedback.tipo === 'ok' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
            <span>{mensajeFeedback.texto}</span>
          </div>
          <button
            type="button"
            onClick={() => setMensajeFeedback(null)}
            className="p-1 rounded-lg hover:bg-black/5 cursor-pointer"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Barra de Filtros y Búsqueda */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-3.5 shadow-2xs flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-3">
          {/* Selector de Año */}
          <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1.5">
            <span className="font-semibold text-slate-500">Año:</span>
            <select
              value={anioSeleccionado}
              onChange={(e) => setAnioSeleccionado(Number(e.target.value))}
              className="bg-transparent font-bold text-slate-800 focus:outline-none cursor-pointer"
            >
              <option value={2026}>2026 (Vigente)</option>
              <option value={2025}>2025</option>
              <option value={2027}>2027</option>
            </select>
          </div>

          {/* Filtro por Categoría */}
          <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1.5">
            <Sliders size={13} className="text-slate-400" />
            <span className="font-semibold text-slate-500">Categoría:</span>
            <select
              value={categoriaFiltro}
              onChange={(e) => setCategoriaFiltro(e.target.value)}
              className="bg-transparent font-semibold text-slate-800 focus:outline-none cursor-pointer"
            >
              <option value="">Todas las Categorías</option>
              <option value="feriado">Feriados Oficiales</option>
              <option value="receso">Recesos y Vacaciones</option>
              <option value="examen">Exámenes / Solemnes</option>
              <option value="clases">Hitos de Clases / Novatos</option>
              <option value="suspension">Suspensiones (Salida 13:00)</option>
              <option value="paro">Paros / Contingencias</option>
            </select>
          </div>

          {/* Búsqueda por Texto */}
          <div className="relative min-w-[220px]">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Buscar en descripción..."
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-8 pr-2.5 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:bg-white focus:outline-none focus:border-uct-blue-primary transition-all"
            />
          </div>
        </div>

        {/* Toggle de Agrupación por Períodos */}
        <label className="flex items-center gap-2 cursor-pointer font-semibold text-slate-700 hover:text-slate-900 select-none">
          <input
            type="checkbox"
            checked={agruparPeriodos}
            onChange={(e) => setAgruparPeriodos(e.target.checked)}
            className="rounded text-uct-blue-primary focus:ring-uct-blue-primary h-3.5 w-3.5 cursor-pointer"
          />
          <span>Agrupar períodos continuos</span>
        </label>
      </div>

      {/* Tabla de Eventos */}
      <div className="bg-white rounded-2xl border border-slate-200/90 shadow-2xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50/80 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10.5px]">
              <tr>
                <th className="py-3 px-4">Fecha / Período</th>
                <th className="py-3 px-3">Duración</th>
                <th className="py-3 px-4">Descripción del Hito</th>
                <th className="py-3 px-3">Categorías Asignadas</th>
                <th className="py-3 px-3 text-center">Fuente</th>
                <th className="py-3 px-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-400">
                    <RefreshCw size={20} className="animate-spin mx-auto mb-2 text-uct-blue-primary" />
                    <span>Cargando eventos del calendario...</span>
                  </td>
                </tr>
              ) : eventos.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-400">
                    No se encontraron hitos académicos con los filtros seleccionados.
                  </td>
                </tr>
              ) : (
                eventos.map((ev, idx) => {
                  const esRango = ev.fecha_inicio && ev.fecha_fin && ev.fecha_inicio !== ev.fecha_fin
                  const desc = (ev.descripcion || '').toLowerCase()
                  const esVacacion = ev.is_break && desc.includes('vacacion')
                  const esReceso = ev.is_break && !desc.includes('vacacion')

                  return (
                    <tr key={`${ev.fecha_inicio || ev.fecha}_${idx}`} className="hover:bg-slate-50/70 transition-colors">
                      {/* Fecha / Rango */}
                      <td className="py-3 px-4 font-mono font-bold text-slate-800 whitespace-nowrap">
                        {esRango ? (
                          <div className="flex items-center gap-1.5">
                            <span>{formatIsoDate(ev.fecha_inicio)}</span>
                            <span className="text-slate-400">→</span>
                            <span>{formatIsoDate(ev.fecha_fin)}</span>
                          </div>
                        ) : (
                          <span>{formatIsoDate(ev.fecha || ev.fecha_inicio)}</span>
                        )}
                      </td>

                      {/* Duración */}
                      <td className="py-3 px-3 whitespace-nowrap">
                        <span className="px-2 py-0.5 rounded-md text-[10.5px] font-bold bg-slate-100 text-slate-600">
                          {ev.dias_totales ? `${ev.dias_totales} día(s)` : '1 día'}
                        </span>
                      </td>

                      {/* Descripción */}
                      <td className="py-3 px-4 font-medium text-slate-800 max-w-md">
                        {ev.descripcion || <span className="text-slate-400 italic">Sin descripción</span>}
                      </td>

                      {/* Categorías (Badges) */}
                      <td className="py-3 px-3">
                        <div className="flex flex-wrap items-center gap-1.5">
                          {ev.is_holiday && (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-red-50 text-red-700 border border-red-200">
                              Feriado Oficial
                            </span>
                          )}
                          {esReceso && (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                              Semana de Receso
                            </span>
                          )}
                          {esVacacion && (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-[#5F9EA0]/15 text-[#30595B] border border-[#5F9EA0]/30">
                              Vacaciones
                            </span>
                          )}
                          {ev.is_exam_period && (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">
                              Exámenes / Solemnes
                            </span>
                          )}
                          {ev.is_class_milestone && (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-sky-50 text-sky-700 border border-sky-200">
                              Hito Clases / Novatos
                            </span>
                          )}
                          {ev.suspension_actividades && !ev.is_holiday && (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-orange-50 text-orange-700 border border-orange-200">
                              Salida 13:00 / Suspensión
                            </span>
                          )}
                          {(ev.is_strike_federado || ev.is_strike_carrera) && (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
                              Paro / Contingencia
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Fuente */}
                      <td className="py-3 px-3 text-center whitespace-nowrap">
                        <span
                          className={`px-2 py-0.5 rounded-md text-[10px] font-bold border ${
                            ev.fuente === 'manual'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : 'bg-blue-50 text-uct-blue-primary border-blue-200'
                          }`}
                        >
                          {ev.fuente === 'manual' ? 'Manual' : 'Web Scraping'}
                        </span>
                      </td>

                      {/* Acciones */}
                      <td className="py-3 px-4 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => abrirEdicion(ev)}
                            className="p-1.5 rounded-lg text-slate-500 hover:text-uct-blue-primary hover:bg-slate-100 transition cursor-pointer"
                            title="Editar categorías y descripción"
                          >
                            <Edit2 size={14} />
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              if (confirm(`¿Desea eliminar el evento del día ${ev.fecha || ev.fecha_inicio}?`)) {
                                mutationEliminar.mutate(ev.fecha || ev.fecha_inicio || '')
                              }
                            }}
                            className="p-1.5 rounded-lg text-slate-500 hover:text-rose-600 hover:bg-rose-50 transition cursor-pointer"
                            title="Eliminar hito"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal de Edición de Hito */}
      {eventoEditando && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-lg w-full p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Edit2 size={18} className="text-uct-blue-primary" />
                <h3 className="text-sm font-bold text-slate-900">
                  Editar Hito: {formatIsoDate(eventoEditando.fecha || eventoEditando.fecha_inicio)}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setEventoEditando(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Descripción Oficial</label>
                <textarea
                  rows={2}
                  value={formEdit.descripcion}
                  onChange={(e) => setFormEdit({ ...formEdit, descripcion: e.target.value })}
                  className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 focus:bg-white focus:outline-none focus:border-uct-blue-primary"
                />
              </div>

              <div>
                <span className="block font-semibold text-slate-700 mb-2">Categorías Activas para Analítica y ML:</span>
                <div className="grid grid-cols-2 gap-2 p-3 bg-slate-50 rounded-xl border border-slate-200/80">
                  <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700 select-none">
                    <input
                      type="checkbox"
                      checked={formEdit.is_holiday}
                      onChange={(e) => setFormEdit({ ...formEdit, is_holiday: e.target.checked })}
                      className="rounded text-red-600 focus:ring-red-500 h-3.5 w-3.5"
                    />
                    <span>Feriado Oficial</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700 select-none">
                    <input
                      type="checkbox"
                      checked={formEdit.is_break}
                      onChange={(e) => setFormEdit({ ...formEdit, is_break: e.target.checked })}
                      className="rounded text-amber-500 focus:ring-amber-500 h-3.5 w-3.5"
                    />
                    <span>Receso / Vacaciones</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700 select-none">
                    <input
                      type="checkbox"
                      checked={formEdit.is_exam_period}
                      onChange={(e) => setFormEdit({ ...formEdit, is_exam_period: e.target.checked })}
                      className="rounded text-purple-600 focus:ring-purple-500 h-3.5 w-3.5"
                    />
                    <span>Exámenes / Solemnes</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700 select-none">
                    <input
                      type="checkbox"
                      checked={formEdit.is_class_milestone}
                      onChange={(e) => setFormEdit({ ...formEdit, is_class_milestone: e.target.checked })}
                      className="rounded text-sky-600 focus:ring-sky-500 h-3.5 w-3.5"
                    />
                    <span>Hito Clases / Novatos</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700 select-none">
                    <input
                      type="checkbox"
                      checked={formEdit.suspension_actividades}
                      onChange={(e) => setFormEdit({ ...formEdit, suspension_actividades: e.target.checked })}
                      className="rounded text-orange-500 focus:ring-orange-500 h-3.5 w-3.5"
                    />
                    <span>Salida 13:00 / Suspensión</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700 select-none">
                    <input
                      type="checkbox"
                      checked={formEdit.is_strike_federado}
                      onChange={(e) => setFormEdit({ ...formEdit, is_strike_federado: e.target.checked })}
                      className="rounded text-rose-600 focus:ring-rose-500 h-3.5 w-3.5"
                    />
                    <span>Paro Federado FEUCT</span>
                  </label>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setEventoEditando(null)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100 cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={mutationActualizar.isPending}
                onClick={() => {
                  const targetFecha = eventoEditando.fecha || eventoEditando.fecha_inicio
                  if (targetFecha) {
                    mutationActualizar.mutate({ fecha: targetFecha, datos: formEdit })
                  }
                }}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-uct-blue-primary text-white hover:bg-uct-blue-secondary cursor-pointer disabled:opacity-50"
              >
                <Save size={14} />
                <span>{mutationActualizar.isPending ? 'Guardando...' : 'Guardar Cambios'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal de Nuevo Hito */}
      {modalNuevoAbierto && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-lg w-full p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Plus size={18} className="text-uct-blue-primary" />
                <h3 className="text-sm font-bold text-slate-900">Agregar Hito Manual al Calendario</h3>
              </div>
              <button
                type="button"
                onClick={() => setModalNuevoAbierto(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Fecha Inicio</label>
                  <input
                    type="date"
                    value={formNuevo.fecha_inicio}
                    onChange={(e) => setFormNuevo({ ...formNuevo, fecha_inicio: e.target.value })}
                    className="w-full p-2 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 focus:bg-white focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Fecha Fin (Opcional)</label>
                  <input
                    type="date"
                    value={formNuevo.fecha_fin || ''}
                    onChange={(e) => setFormNuevo({ ...formNuevo, fecha_fin: e.target.value })}
                    className="w-full p-2 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 focus:bg-white focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Descripción del Hito</label>
                <input
                  type="text"
                  placeholder="Ej: Semana de Inducción Novatos / Salida anticipada 13:00 hrs"
                  value={formNuevo.descripcion}
                  onChange={(e) => setFormNuevo({ ...formNuevo, descripcion: e.target.value })}
                  className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 focus:bg-white focus:outline-none focus:border-uct-blue-primary"
                />
              </div>

              <div>
                <span className="block font-semibold text-slate-700 mb-2">Categorías que Aplican:</span>
                <div className="grid grid-cols-2 gap-2 p-3 bg-slate-50 rounded-xl border border-slate-200/80">
                  <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700 select-none">
                    <input
                      type="checkbox"
                      checked={formNuevo.is_holiday}
                      onChange={(e) => setFormNuevo({ ...formNuevo, is_holiday: e.target.checked })}
                      className="rounded text-red-600 focus:ring-red-500 h-3.5 w-3.5"
                    />
                    <span>Feriado Oficial</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700 select-none">
                    <input
                      type="checkbox"
                      checked={formNuevo.is_break}
                      onChange={(e) => setFormNuevo({ ...formNuevo, is_break: e.target.checked })}
                      className="rounded text-amber-500 focus:ring-amber-500 h-3.5 w-3.5"
                    />
                    <span>Receso / Vacaciones</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700 select-none">
                    <input
                      type="checkbox"
                      checked={formNuevo.is_exam_period}
                      onChange={(e) => setFormNuevo({ ...formNuevo, is_exam_period: e.target.checked })}
                      className="rounded text-purple-600 focus:ring-purple-500 h-3.5 w-3.5"
                    />
                    <span>Exámenes / Solemnes</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700 select-none">
                    <input
                      type="checkbox"
                      checked={formNuevo.is_class_milestone}
                      onChange={(e) => setFormNuevo({ ...formNuevo, is_class_milestone: e.target.checked })}
                      className="rounded text-sky-600 focus:ring-sky-500 h-3.5 w-3.5"
                    />
                    <span>Hito Clases / Novatos</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700 select-none">
                    <input
                      type="checkbox"
                      checked={formNuevo.suspension_actividades}
                      onChange={(e) => setFormNuevo({ ...formNuevo, suspension_actividades: e.target.checked })}
                      className="rounded text-orange-500 focus:ring-orange-500 h-3.5 w-3.5"
                    />
                    <span>Salida 13:00 / Suspensión</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700 select-none">
                    <input
                      type="checkbox"
                      checked={formNuevo.is_strike_federado}
                      onChange={(e) => setFormNuevo({ ...formNuevo, is_strike_federado: e.target.checked })}
                      className="rounded text-rose-600 focus:ring-rose-500 h-3.5 w-3.5"
                    />
                    <span>Paro Federado FEUCT</span>
                  </label>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setModalNuevoAbierto(false)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100 cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={mutationCrear.isPending || !formNuevo.descripcion.trim()}
                onClick={() => mutationCrear.mutate(formNuevo)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-uct-blue-primary text-white hover:bg-uct-blue-secondary cursor-pointer disabled:opacity-50"
              >
                <Save size={14} />
                <span>{mutationCrear.isPending ? 'Creando...' : 'Crear Hito'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default CalendarioSection

