import React, { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Clock,
  RefreshCw,
  Play,
  CheckCircle2,
  AlertTriangle,
  Activity,
  Calendar,
  Zap,
  Trash2,
  Cpu,
  Layers,
  Eye,
  X,
  FileText,
} from 'lucide-react'
import {
  consultarResumenTareasAdmin,
  ejecutarTareaAdmin,
  obtenerEstadoSmartCampus,
  sincronizarSmartCampusManual,
  fetchCalendarStatus,
  syncCalendarScrape,
  limpiarCacheAdmin,
  obtenerStatsCacheAdmin,
  dispararActualizacionModelos,
  consultarEstadoModelos,
  TareaItem,
  EjecucionTareaDetalle,
} from '../../../api/client'

export const TareasProgramadasSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [sincronizandoManual, setSincronizandoManual] = useState(false)
  const [mensajeSmartCampus, setMensajeSmartCampus] = useState<string | null>(null)
  const [mensajeCache, setMensajeCache] = useState<string | null>(null)
  const [mensajeModelos, setMensajeModelos] = useState<string | null>(null)
  const [actualizandoModelos, setActualizandoModelos] = useState(false)
  const [tareaEjecutando, setTareaEjecutando] = useState<string | null>(null)
  const [tareaDetalleModal, setTareaDetalleModal] = useState<TareaItem | null>(null)
  const [ejecucionSeleccionada, setEjecucionSeleccionada] = useState<EjecucionTareaDetalle | null>(null)
  const ultimasFinEnRef = useRef<Record<string, string>>({})

  // 1. Consulta de tareas de APScheduler (refresco rápido cuando hay tareas en ejecución)
  const {
    data: resumenTareas,
    isLoading: cargandoTareas,
    refetch: refetchTareas,
  } = useQuery({
    queryKey: ['admin-tareas-resumen'],
    queryFn: consultarResumenTareasAdmin,
    refetchInterval: (query) => {
      const hayEnCurso = query.state.data?.catalogo?.some((t) => t.en_curso)
      return hayEnCurso || tareaEjecutando ? 4_000 : 15_000
    },
  })

  // 1b. Consulta de estado de los modelos predictivos
  const {
    data: estadoModelos,
    isLoading: cargandoModelos,
    refetch: refetchModelos,
  } = useQuery({
    queryKey: ['admin-modelos-estado'],
    queryFn: consultarEstadoModelos,
    refetchInterval: 20_000,
  })

  // 2. Consulta de estado del conector Smart Campus
  const {
    data: estadoSmartCampus,
    isLoading: cargandoSmartCampus,
    refetch: refetchSmartCampus,
  } = useQuery({
    queryKey: ['admin-smart-campus-estado'],
    queryFn: obtenerEstadoSmartCampus,
    refetchInterval: 30_000,
  })

  // 3. Consulta de estado del calendario institucional
  const {
    data: estadoCalendario,
    isLoading: cargandoCalendario,
    refetch: refetchCalendario,
  } = useQuery({
    queryKey: ['admin-calendar-status'],
    queryFn: fetchCalendarStatus,
    refetchInterval: 60_000,
  })

  // 4. Consulta de métricas de la caché en memoria
  const {
    data: statsCache,
    isLoading: cargandoCache,
    refetch: refetchCache,
  } = useQuery({
    queryKey: ['admin-cache-stats'],
    queryFn: obtenerStatsCacheAdmin,
    refetchInterval: 15_000,
  })

  const refrescarDatosDashboard = () => {
    try {
      localStorage.removeItem('uct_ultima_fecha_max_espacio_1')
      localStorage.removeItem('uct_ultima_fecha_max_espacio_2')
    } catch {
      // Ignorar bloqueo de almacenamiento
    }
    queryClient.invalidateQueries({ queryKey: ['date-bounds'] })
    queryClient.invalidateQueries({ queryKey: ['kpi-summary'] })
    queryClient.invalidateQueries({ queryKey: ['attendance-kpis'] })
    queryClient.invalidateQueries({ queryKey: ['occupancy-realtime'] })
    queryClient.invalidateQueries({ queryKey: ['attendance-hourly-flow'] })
    queryClient.invalidateQueries({ queryKey: ['forecast-attendance'] })
    queryClient.invalidateQueries({ queryKey: ['rooms-comparison'] })
    queryClient.invalidateQueries({ queryKey: ['doors-usage'] })
    queryClient.invalidateQueries({ queryKey: ['heatmap'] })
    queryClient.invalidateQueries({ queryKey: ['weekly-evolution'] })
    queryClient.invalidateQueries({ queryKey: ['vehicle-kpis'] })
    queryClient.invalidateQueries({ queryKey: ['parking-occupancy'] })
    queryClient.invalidateQueries({ queryKey: ['vehicle-hourly-flow'] })
    queryClient.invalidateQueries({ queryKey: ['forecast-parking'] })
    queryClient.invalidateQueries({ queryKey: ['vehicle-daily-evolution'] })
    queryClient.invalidateQueries({ queryKey: ['camera-stats'] })
    queryClient.invalidateQueries({ queryKey: ['admin-smart-campus-estado'] })
    queryClient.invalidateQueries({ queryKey: ['admin-tareas-resumen'] })
    queryClient.invalidateQueries({ queryKey: ['admin-modelos-estado'] })
    queryClient.invalidateQueries({ queryKey: ['admin-cache-stats'] })
  }

  // Detectar finalización reactiva de cualquier tarea para refrescar gráficos automáticamente sin recargar la página
  useEffect(() => {
    if (!resumenTareas?.catalogo) return
    let huboNuevaFinalizacion = false
    for (const item of resumenTareas.catalogo) {
      const finActual = item.ultima_ejecucion?.fin_en || item.ultima_ejecucion?.fin || ''
      const finPrevio = ultimasFinEnRef.current[item.nombre]
      if (finPrevio !== undefined && finActual && finActual !== finPrevio) {
        huboNuevaFinalizacion = true
      }
      ultimasFinEnRef.current[item.nombre] = finActual
    }
    if (huboNuevaFinalizacion) {
      refrescarDatosDashboard()
    }
    if (tareaDetalleModal) {
      const actualizada = resumenTareas.catalogo.find((c) => c.nombre === tareaDetalleModal.nombre)
      if (actualizada) {
        setTareaDetalleModal(actualizada)
        if (!ejecucionSeleccionada || ejecucionSeleccionada.id === tareaDetalleModal.ultima_ejecucion?.id) {
          setEjecucionSeleccionada(actualizada.ultima_ejecucion || null)
        }
      }
    }
  }, [resumenTareas])

  // Mutación: Sincronización manual de Smart Campus
  const syncManualMutation = useMutation({
    mutationFn: () => sincronizarSmartCampusManual({}),
    onMutate: () => setSincronizandoManual(true),
    onSuccess: (res) => {
      setMensajeSmartCampus(res.mensaje || 'Sincronización manual ejecutada con éxito.')
      refrescarDatosDashboard()
      setTimeout(() => setMensajeSmartCampus(null), 8000)
    },
    onError: (err: any) => {
      setMensajeSmartCampus(err?.response?.data?.detail || 'Error al ejecutar sincronización manual.')
      setTimeout(() => setMensajeSmartCampus(null), 6000)
    },
    onSettled: () => setSincronizandoManual(false),
  })

  // Mutación: Scrape y sincronización de calendario
  const syncCalendarioMutation = useMutation({
    mutationFn: syncCalendarScrape,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-calendar-status'] })
      refetchCalendario()
    },
  })

  // Mutación: Limpieza total de caché en memoria
  const purgarCacheMutation = useMutation({
    mutationFn: () => limpiarCacheAdmin(),
    onSuccess: (res) => {
      setMensajeCache(`Caché purgada exitosamente: ${res.entradas_eliminadas} entradas eliminadas.`)
      queryClient.invalidateQueries({ queryKey: ['admin-cache-stats'] })
      setTimeout(() => setMensajeCache(null), 5000)
    },
    onError: () => {
      setMensajeCache('Error al purgar la memoria de caché.')
      setTimeout(() => setMensajeCache(null), 5000)
    },
  })

  // Mutación: Actualización manual de modelos predictivos (Campeón vs. Retador)
  const actualizarModelosMutation = useMutation({
    mutationFn: () => dispararActualizacionModelos(),
    onMutate: () => setActualizandoModelos(true),
    onSuccess: (res) => {
      setMensajeModelos(res.mensaje || 'Actualización y reentrenamiento de modelos iniciado en segundo plano.')
      queryClient.invalidateQueries({ queryKey: ['admin-tareas-resumen'] })
      queryClient.invalidateQueries({ queryKey: ['admin-modelos-estado'] })
      queryClient.invalidateQueries({ queryKey: ['forecast-attendance'] })
      queryClient.invalidateQueries({ queryKey: ['forecast-parking'] })
      queryClient.invalidateQueries({ queryKey: ['forecast-14days'] })
      setTimeout(() => setMensajeModelos(null), 8000)
    },
    onError: (err: any) => {
      setMensajeModelos(err?.response?.data?.detail || 'Error al solicitar actualización de modelos.')
      setTimeout(() => setMensajeModelos(null), 6000)
    },
    onSettled: () => setActualizandoModelos(false),
  })

  // Mutación: Ejecución manual de una tarea individual del catálogo
  const ejecutarTareaManual = async (nombreTarea: string) => {
    setTareaEjecutando(nombreTarea)
    try {
      await ejecutarTareaAdmin(nombreTarea)
      refrescarDatosDashboard()
      if (nombreTarea === 'reentrenar_modelos_ml') {
        queryClient.invalidateQueries({ queryKey: ['admin-modelos-estado'] })
      }
      setTimeout(() => {
        refrescarDatosDashboard()
      }, 4000)
    } catch (err: any) {
      setMensajeModelos(err?.response?.data?.detail || `Error al ejecutar tarea ${nombreTarea}.`)
      setTimeout(() => setMensajeModelos(null), 5000)
    } finally {
      setTareaEjecutando(null)
    }
  }

  const tareaModelosInfo = (resumenTareas?.catalogo || []).find((t) => t.nombre === 'reentrenar_modelos_ml')
  const tareaSmartCampusVivoInfo = (resumenTareas?.catalogo || []).find(
    (t) => t.nombre === 'sincronizar_smart_campus_en_vivo'
  )

  return (
    <div className="space-y-6">
      {/* Encabezado y Estado Global del Planificador */}
      <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-uct-blue-primary/10 flex items-center justify-center text-uct-blue-primary shadow-2xs">
            <Clock size={20} />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-800">Planificador de Tareas, Modelos IA y Conectores de Datos</h2>
            <p className="text-xs text-slate-500">
              Monitoreo operativo de modelos predictivos, tareas programadas (APScheduler), ingesta Smart Campus y caché de rendimiento.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>APScheduler Activo</span>
          </div>
          <button
            type="button"
            onClick={() => {
              refetchTareas()
              refetchModelos()
              refetchSmartCampus()
              refetchCalendario()
              refetchCache()
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 transition cursor-pointer"
          >
            <RefreshCw size={13} />
            <span>Actualizar</span>
          </button>
        </div>
      </div>

      {/* Módulo Modelos Predictivos: Campeón vs. Retador */}
      <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center text-amber-600">
              <Activity size={16} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-800">
                Modelos Predictivos (Prophet 14 Días, GBR Demanda y K-Means)
              </h3>
              <p className="text-[11px] text-slate-500">
                Actualización automática diaria a las 06:00 AM (solo en días operativos de cada módulo según horario y calendario académico) o ejecución manual bajo demanda.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            {tareaModelosInfo?.proxima_ejecucion && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200 text-[11px] text-slate-600">
                <Clock size={12} className="text-uct-blue-primary shrink-0" />
                <span>
                  Siguiente actualización:{' '}
                  <strong className="text-slate-800">
                    {new Date(tareaModelosInfo.proxima_ejecucion).toLocaleString('es-CL')}
                  </strong>
                </span>
              </div>
            )}
            <button
              type="button"
              onClick={() => actualizarModelosMutation.mutate()}
              disabled={actualizandoModelos}
              title="Actualizar modelo predictivo ahora ejecutando evaluación Campeón vs. Retador"
              className="flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-amber-950 bg-amber-100 hover:bg-amber-200 border border-amber-300 shadow-2xs transition cursor-pointer disabled:opacity-60"
            >
              <RefreshCw size={13} className={`text-amber-800 ${actualizandoModelos ? 'animate-spin' : ''}`} />
              <span>{actualizandoModelos ? 'Actualizando modelo...' : 'Actualizar modelo ahora'}</span>
            </button>
          </div>
        </div>

        {mensajeModelos && (
          <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-xl text-xs text-amber-900 flex items-center gap-2">
            <CheckCircle2 size={15} className="text-amber-600 shrink-0" />
            <span>{mensajeModelos}</span>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/75 text-[11px] uppercase font-bold text-slate-500 tracking-wider">
                <th className="py-2 px-3">Modelo</th>
                <th className="py-2 px-3">Familia</th>
                <th className="py-2 px-3">Estado</th>
                <th className="py-2 px-3">WAPE / MAE</th>
                <th className="py-2 px-3">Última Calibración</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {cargandoModelos ? (
                <tr>
                  <td colSpan={5} className="py-4 text-center text-slate-400">Cargando estado de modelos predictivos...</td>
                </tr>
              ) : (
                (estadoModelos || []).map((m) => (
                  <tr key={m.clave} className="hover:bg-slate-50/50 transition">
                    <td className="py-2 px-3 font-semibold text-slate-800">{m.clave}</td>
                    <td className="py-2 px-3 text-slate-600">{m.familia}</td>
                    <td className="py-2 px-3">
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                          m.disponible
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}
                      >
                        {m.estado}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-slate-600">
                      {m.wape !== null && m.wape !== undefined ? `WAPE ${m.wape}%` : '—'}
                      {m.mae !== null && m.mae !== undefined ? ` | MAE ${m.mae}` : ''}
                    </td>
                    <td className="py-2 px-3 text-slate-500">
                      {m.ultima_modificacion ? new Date(m.ultima_modificacion).toLocaleString('es-CL') : '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Módulo 1: Conector Oficial API Smart Campus UCT */}
      <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center text-amber-600">
              <Zap size={16} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-800">Conector API Smart Campus UCT</h3>
              <p className="text-[11px] text-slate-500">
                Sincronización incremental desde la última fecha en base de datos hasta hoy (torniquetes Biblioteca y cámaras ANPR Estacionamiento).
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            {tareaSmartCampusVivoInfo?.proxima_ejecucion && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200 text-[11px] text-slate-600">
                <Clock size={12} className="text-uct-blue-primary shrink-0" />
                <span>
                  Siguiente sincronización:{' '}
                  <strong className="text-slate-800">
                    {new Date(tareaSmartCampusVivoInfo.proxima_ejecucion).toLocaleString('es-CL')}
                  </strong>
                </span>
              </div>
            )}
            <button
              type="button"
              onClick={() => syncManualMutation.mutate()}
              disabled={sincronizandoManual}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-uct-blue-primary hover:bg-uct-blue-hover text-white shadow-xs transition cursor-pointer disabled:opacity-50"
            >
              {sincronizandoManual ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
              <span>{sincronizandoManual ? 'Sincronizando...' : 'Sincronizar Manualmente'}</span>
            </button>
          </div>
        </div>

        {mensajeSmartCampus && (
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-700 flex items-center gap-2">
            <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
            <span>{mensajeSmartCampus}</span>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {cargandoSmartCampus ? (
            <div className="col-span-2 p-6 text-center text-xs text-slate-400">Cargando estado de sincronización...</div>
          ) : (
            (estadoSmartCampus?.fuentes || []).map((fuente) => (
              <div key={fuente.id} className="p-4 rounded-xl border border-slate-200/80 bg-slate-50/50 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-700">
                    Fuente: {fuente.fuente}
                  </span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                      fuente.estado === 'completado' || fuente.estado === 'exitoso'
                        ? 'bg-emerald-100 text-emerald-800'
                        : fuente.estado === 'error' || fuente.estado === 'fallido'
                        ? 'bg-red-100 text-red-800'
                        : 'bg-blue-100 text-blue-800'
                    }`}
                  >
                    {fuente.estado}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center pt-1">
                  <div className="bg-white p-2 rounded-lg border border-slate-100 shadow-2xs">
                    <span className="text-[10px] text-slate-400 block font-medium">Leídas</span>
                    <span className="text-xs font-bold text-slate-700">{fuente.filas_leidas.toLocaleString('es-CL')}</span>
                  </div>
                  <div className="bg-white p-2 rounded-lg border border-slate-100 shadow-2xs">
                    <span className="text-[10px] text-slate-400 block font-medium">Insertadas</span>
                    <span className="text-xs font-bold text-emerald-600">{fuente.filas_insertadas.toLocaleString('es-CL')}</span>
                  </div>
                  <div className="bg-white p-2 rounded-lg border border-slate-100 shadow-2xs">
                    <span className="text-[10px] text-slate-400 block font-medium">Duplicadas</span>
                    <span className="text-xs font-bold text-slate-500">{fuente.filas_duplicadas.toLocaleString('es-CL')}</span>
                  </div>
                </div>
                <div className="text-[11px] text-slate-500 flex justify-between pt-1">
                  <span>Última sinc: {fuente.ultima_fecha_sincronizada || '—'}</span>
                  <span>{fuente.ultima_ejecucion_en ? new Date(fuente.ultima_ejecucion_en).toLocaleTimeString('es-CL') : '—'}</span>
                </div>
                {fuente.ultimo_error && (
                  <p className="text-[10px] text-red-600 bg-red-50 p-2 rounded-lg border border-red-100 truncate" title={fuente.ultimo_error}>
                    Error: {fuente.ultimo_error}
                  </p>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Módulo 2: Catálogo de Tareas Programadas Internas (APScheduler) */}
      <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs space-y-4">
        <div className="flex items-center gap-2.5 pb-2 border-b border-slate-100">
          <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center text-blue-600">
            <Cpu size={16} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-800">Catálogo de Tareas Automáticas en Servidor</h3>
            <p className="text-[11px] text-slate-500">
              Ciclos periódicos: ingesta en vivo (horario), consolidación nocturna D-1 (00:05) y reentrenamiento diario (06:00).
            </p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/75 text-[11px] uppercase font-bold text-slate-500 tracking-wider">
                <th className="py-2.5 px-3">Tarea</th>
                <th className="py-2.5 px-3">Estado</th>
                <th className="py-2.5 px-3">Última Ejecución</th>
                <th className="py-2.5 px-3">Siguiente Actualización Programada</th>
                <th className="py-2.5 px-3">Duración</th>
                <th className="py-2.5 px-3">Resultado</th>
                <th className="py-2.5 px-3 text-right">Acción</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {cargandoTareas ? (
                <tr>
                  <td colSpan={7} className="py-4 text-center text-slate-400">Cargando tareas registradas...</td>
                </tr>
              ) : (
                (resumenTareas?.catalogo || []).map((t) => {
                  const fechaInicio = t.ultima_ejecucion?.inicio_en || t.ultima_ejecucion?.inicio
                  const estadoUltima = t.ultima_ejecucion?.estado
                  const esExitoso = estadoUltima === 'exitoso' || estadoUltima === 'completado'
                  const errorUltima = t.ultima_ejecucion?.error || t.ultima_ejecucion?.error_detalle
                  return (
                    <tr key={t.nombre} className="hover:bg-slate-50/50 transition">
                      <td className="py-2.5 px-3 font-semibold text-slate-800 flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full shrink-0 ${t.en_curso ? 'bg-amber-500 animate-pulse' : 'bg-slate-300'}`} />
                        <div>
                          <span className="block">{t.nombre}</span>
                          {t.descripcion && <span className="text-[10.5px] font-normal text-slate-400 block">{t.descripcion}</span>}
                          {errorUltima && (
                            <span className="text-[10px] font-normal text-red-600 block mt-0.5 max-w-xs truncate" title={errorUltima}>
                              Detalle: {errorUltima}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-2.5 px-3">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                          t.en_curso ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-600'
                        }`}>
                          {t.en_curso ? 'Ejecutando' : 'En Espera'}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-slate-500">
                        {fechaInicio ? new Date(fechaInicio).toLocaleString('es-CL') : 'Sin registros'}
                      </td>
                      <td className="py-2.5 px-3">
                        {t.proxima_ejecucion ? (
                          <div>
                            <span className="font-semibold text-uct-blue-primary block">
                              {new Date(t.proxima_ejecucion).toLocaleString('es-CL')}
                            </span>
                            {t.cron_expresion && (
                              <span className="text-[10px] text-slate-400 block">{t.cron_expresion}</span>
                            )}
                          </div>
                        ) : (
                          <span className="text-[11px] text-slate-400">{t.cron_expresion || 'Bajo demanda'}</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-slate-600">
                        {t.ultima_ejecucion?.duracion_segundos !== undefined && t.ultima_ejecucion?.duracion_segundos !== null
                          ? `${t.ultima_ejecucion.duracion_segundos.toFixed(1)} s`
                          : '—'}
                      </td>
                      <td className="py-2.5 px-3">
                        {estadoUltima ? (
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                            esExitoso
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : estadoUltima === 'omitido'
                              ? 'bg-slate-100 text-slate-600 border border-slate-200'
                              : 'bg-red-50 text-red-700 border border-red-200'
                          }`}>
                            {estadoUltima}
                          </span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <div className="inline-flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => {
                              setTareaDetalleModal(t)
                              setEjecucionSeleccionada(t.ultima_ejecucion || null)
                            }}
                            title="Ver detalles de lo ocurrido en la ejecución"
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 transition cursor-pointer"
                          >
                            <Eye size={11} className="text-uct-blue-primary" />
                            <span>Detalles</span>
                          </button>
                          <button
                            type="button"
                            disabled={t.en_curso || tareaEjecutando === t.nombre}
                            onClick={() => ejecutarTareaManual(t.nombre)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-slate-100 hover:bg-uct-blue-primary hover:text-white text-slate-700 border border-slate-200 transition cursor-pointer disabled:opacity-50"
                          >
                            <Play size={11} />
                            <span>{tareaEjecutando === t.nombre ? 'Iniciando...' : 'Ejecutar'}</span>
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

      {/* Modal de Detalles de Ejecución de Tarea */}
      {tareaDetalleModal && (() => {
        const ejecActiva = ejecucionSeleccionada || tareaDetalleModal.ultima_ejecucion || null
        const historialTarea = (resumenTareas?.ultimas_ejecuciones || []).filter(
          (e) => (e.tarea || e.tarea_nombre) === tareaDetalleModal.nombre
        )
        let resumenObj: any = null
        if (ejecActiva?.resumen_json) {
          try {
            resumenObj = JSON.parse(ejecActiva.resumen_json)
          } catch {
            resumenObj = null
          }
        }
        const inicioStr = ejecActiva?.inicio_en || ejecActiva?.inicio || ejecActiva?.iniciado_en
        const finStr = ejecActiva?.fin_en || ejecActiva?.fin || ejecActiva?.finalizado_en
        const errorStr = ejecActiva?.error || ejecActiva?.error_detalle

        return (
          <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-3xl max-h-[88vh] flex flex-col overflow-hidden">
              {/* Cabecera del Modal */}
              <div className="p-5 border-b border-slate-100 flex items-start justify-between gap-4 bg-slate-50/60">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl bg-uct-blue-primary/10 flex items-center justify-center text-uct-blue-primary shrink-0">
                    <FileText size={20} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-bold text-slate-900">{tareaDetalleModal.nombre}</h3>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                        tareaDetalleModal.en_curso ? 'bg-amber-100 text-amber-800' : 'bg-slate-200/80 text-slate-700'
                      }`}>
                        {tareaDetalleModal.en_curso ? 'Ejecutando ahora' : 'En Espera'}
                      </span>
                    </div>
                    {tareaDetalleModal.descripcion && (
                      <p className="text-xs text-slate-500 mt-0.5">{tareaDetalleModal.descripcion}</p>
                    )}
                    <div className="flex flex-wrap items-center gap-3 mt-1.5 text-[11px] text-slate-500">
                      <span>Frecuencia: <strong className="text-slate-700">{tareaDetalleModal.cron_expresion || 'Bajo demanda'}</strong></span>
                      {tareaDetalleModal.proxima_ejecucion && (
                        <span>
                          Siguiente ejecución:{' '}
                          <strong className="text-uct-blue-primary">
                            {new Date(tareaDetalleModal.proxima_ejecucion).toLocaleString('es-CL')}
                          </strong>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setTareaDetalleModal(null)
                    setEjecucionSeleccionada(null)
                  }}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Cuerpo del Modal */}
              <div className="p-5 overflow-y-auto space-y-5 text-xs">
                {!ejecActiva ? (
                  <div className="p-6 text-center bg-slate-50 rounded-xl border border-slate-200 text-slate-500">
                    Esta tarea aún no registra ejecuciones en la base de datos.
                  </div>
                ) : (
                  <>
                    {/* Métricas de la Ejecución Seleccionada */}
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
                      <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">Resultado</span>
                        <span className={`inline-block mt-1 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                          ejecActiva.estado === 'exitoso' || ejecActiva.estado === 'completado'
                            ? 'bg-emerald-100 text-emerald-800'
                            : ejecActiva.estado === 'en_curso'
                            ? 'bg-amber-100 text-amber-800'
                            : 'bg-red-100 text-red-800'
                        }`}>
                          {ejecActiva.estado}
                        </span>
                      </div>
                      <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">Disparador</span>
                        <span className="text-xs font-bold text-slate-800 mt-1 block capitalize">
                          {ejecActiva.disparador || ejecActiva.origen || 'automático'}
                        </span>
                      </div>
                      <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">Inicio</span>
                        <span className="text-[11px] font-semibold text-slate-800 mt-1 block">
                          {inicioStr ? new Date(inicioStr).toLocaleString('es-CL') : '—'}
                        </span>
                      </div>
                      <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">Término</span>
                        <span className="text-[11px] font-semibold text-slate-800 mt-1 block">
                          {finStr ? new Date(finStr).toLocaleString('es-CL') : 'En curso'}
                        </span>
                      </div>
                      <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">Duración / Memoria</span>
                        <span className="text-xs font-bold text-slate-800 mt-1 block">
                          {ejecActiva.duracion_segundos != null ? `${ejecActiva.duracion_segundos.toFixed(1)} s` : '—'}
                          {ejecActiva.memoria_pico_mb != null ? ` (${ejecActiva.memoria_pico_mb} MB)` : ''}
                        </span>
                      </div>
                    </div>

                    {/* Alerta de Error si ocurrió fallo */}
                    {errorStr && (
                      <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-800 space-y-1">
                        <div className="flex items-center gap-1.5 font-bold text-xs">
                          <AlertTriangle size={14} className="text-red-600 shrink-0" />
                          <span>Error registrado durante la ejecución:</span>
                        </div>
                        <p className="text-[11px] font-mono whitespace-pre-wrap break-words">{errorStr}</p>
                      </div>
                    )}

                    {/* Desglose Estructurado según Tipo de Tarea */}
                    <div className="space-y-3">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">
                        Detalle de lo Ocurrido en la Ejecución
                      </h4>

                      {resumenObj ? (
                        <>
                          {/* Caso 1: Sincronización Smart Campus en Vivo */}
                          {(resumenObj.torniquetes || resumenObj.estacionamientos) && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                              {resumenObj.torniquetes && (
                                <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/70 space-y-2">
                                  <div className="flex items-center justify-between">
                                    <span className="font-bold text-slate-800">Torniquetes Biblioteca (CSF)</span>
                                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                                      {resumenObj.rango_torniquetes || resumenObj.fecha || 'Hoy'}
                                    </span>
                                  </div>
                                  <div className="grid grid-cols-3 gap-2 text-center">
                                    <div className="bg-white p-2 rounded-lg border border-slate-100">
                                      <span className="text-[10px] text-slate-400 block">Leídos API</span>
                                      <span className="text-sm font-bold text-slate-800">
                                        {(resumenObj.torniquetes.leidos ?? 0).toLocaleString('es-CL')}
                                      </span>
                                    </div>
                                    <div className="bg-white p-2 rounded-lg border border-slate-100">
                                      <span className="text-[10px] text-slate-400 block">Insertados</span>
                                      <span className="text-sm font-bold text-emerald-600">
                                        +{(resumenObj.torniquetes.insertados ?? 0).toLocaleString('es-CL')}
                                      </span>
                                    </div>
                                    <div className="bg-white p-2 rounded-lg border border-slate-100">
                                      <span className="text-[10px] text-slate-400 block">Duplicados</span>
                                      <span className="text-sm font-bold text-slate-500">
                                        {(resumenObj.torniquetes.duplicados ?? 0).toLocaleString('es-CL')}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              )}

                              {resumenObj.estacionamientos && (
                                <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/70 space-y-2">
                                  <div className="flex items-center justify-between">
                                    <span className="font-bold text-slate-800">Cámaras ANPR Estacionamiento</span>
                                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                                      {resumenObj.rango_estacionamientos || resumenObj.fecha || 'Hoy'}
                                    </span>
                                  </div>
                                  <div className="grid grid-cols-3 gap-2 text-center">
                                    <div className="bg-white p-2 rounded-lg border border-slate-100">
                                      <span className="text-[10px] text-slate-400 block">Leídos API</span>
                                      <span className="text-sm font-bold text-slate-800">
                                        {(resumenObj.estacionamientos.leidos ?? 0).toLocaleString('es-CL')}
                                      </span>
                                    </div>
                                    <div className="bg-white p-2 rounded-lg border border-slate-100">
                                      <span className="text-[10px] text-slate-400 block">Insertados</span>
                                      <span className="text-sm font-bold text-emerald-600">
                                        +{(resumenObj.estacionamientos.insertados ?? 0).toLocaleString('es-CL')}
                                      </span>
                                    </div>
                                    <div className="bg-white p-2 rounded-lg border border-slate-100">
                                      <span className="text-[10px] text-slate-400 block">Duplicados</span>
                                      <span className="text-sm font-bold text-slate-500">
                                        {(resumenObj.estacionamientos.duplicados ?? 0).toLocaleString('es-CL')}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}

                          {/* Caso 2: Consolidación Nocturna D-1 */}
                          {resumenObj.fecha_consolidada && (
                            <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/70 space-y-2.5">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-slate-800">
                                  Día Consolidado (D-1): {resumenObj.fecha_consolidada}
                                </span>
                                <span className="text-[11px] text-slate-600">
                                  Salidas imputadas: <strong>{resumenObj.salidas_imputadas ?? 0}</strong>
                                </span>
                              </div>
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                <div className="bg-white p-3 rounded-lg border border-slate-100">
                                  <span className="text-[10px] font-bold uppercase text-slate-400 block mb-1">
                                    Rollup Asistencia Biblioteca
                                  </span>
                                  {resumenObj.rollup_asistencia ? (
                                    <div className="text-[11px] text-slate-700 space-y-0.5">
                                      <div>Ingresos: <strong>{resumenObj.rollup_asistencia.ingresos}</strong> | Salidas: <strong>{resumenObj.rollup_asistencia.salidas}</strong></div>
                                      <div>Personas únicas: <strong>{resumenObj.rollup_asistencia.personas_unicas}</strong> | Mediana: <strong>{resumenObj.rollup_asistencia.permanencia_mediana_min ?? '—'} min</strong></div>
                                    </div>
                                  ) : (
                                    <span className="text-[11px] text-slate-400">Sin registros consolidados</span>
                                  )}
                                </div>
                                <div className="bg-white p-3 rounded-lg border border-slate-100">
                                  <span className="text-[10px] font-bold uppercase text-slate-400 block mb-1">
                                    Rollup Vehicular Estacionamiento
                                  </span>
                                  {resumenObj.rollup_vehicular ? (
                                    <div className="text-[11px] text-slate-700 space-y-0.5">
                                      <div>Ingresos: <strong>{resumenObj.rollup_vehicular.ingresos}</strong> | Salidas: <strong>{resumenObj.rollup_vehicular.salidas}</strong></div>
                                      <div>Vehículos únicos: <strong>{resumenObj.rollup_vehicular.vehiculos_unicos}</strong></div>
                                    </div>
                                  ) : (
                                    <span className="text-[11px] text-slate-400">Sin registros consolidados</span>
                                  )}
                                </div>
                              </div>
                            </div>
                          )}

                          {/* Caso 3: Reentrenamiento de Modelos ML */}
                          {Array.isArray(resumenObj.modelos) && (
                            <div className="overflow-x-auto border border-slate-200 rounded-xl">
                              <table className="w-full text-left border-collapse text-[11px]">
                                <thead>
                                  <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-bold">
                                    <th className="py-2 px-3">Modelo</th>
                                    <th className="py-2 px-3">Estado</th>
                                    <th className="py-2 px-3">WAPE Retador / Campeón</th>
                                    <th className="py-2 px-3">Detalle / Decisión</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100">
                                  {resumenObj.modelos.map((m: any, idx: number) => (
                                    <tr key={idx} className="hover:bg-slate-50/60">
                                      <td className="py-2 px-3 font-semibold text-slate-800">{m.modelo}</td>
                                      <td className="py-2 px-3">
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                                          m.promovido
                                            ? 'bg-emerald-100 text-emerald-800'
                                            : m.estado === 'fallido'
                                            ? 'bg-red-100 text-red-800'
                                            : 'bg-amber-50 text-amber-800 border border-amber-200'
                                        }`}>
                                          {m.estado}
                                        </span>
                                      </td>
                                      <td className="py-2 px-3 text-slate-600">
                                        {m.wape_retador != null ? `${m.wape_retador}%` : '—'} / {m.wape_campeon != null ? `${m.wape_campeon}%` : '—'}
                                      </td>
                                      <td className="py-2 px-3 text-slate-600">{m.motivo || m.error || 'Evaluación completada'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}

                          {/* Errores parciales informados dentro del resumen_json */}
                          {Array.isArray(resumenObj.errores) && resumenObj.errores.length > 0 && (
                            <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 space-y-1">
                              <span className="font-bold text-[11px] block">Observaciones reportadas durante el proceso:</span>
                              <ul className="list-disc list-inside text-[11px] space-y-0.5">
                                {resumenObj.errores.map((errItem: string, idx: number) => (
                                  <li key={idx}>{errItem}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* JSON estructurado completo para auditoría técnica */}
                          <details className="group bg-slate-900 text-slate-100 rounded-xl p-3">
                            <summary className="cursor-pointer text-[11px] font-semibold text-slate-300 select-none">
                              Ver registro técnico completo (JSON)
                            </summary>
                            <pre className="mt-2 text-[10.5px] font-mono text-emerald-300 overflow-x-auto whitespace-pre-wrap">
                              {JSON.stringify(resumenObj, null, 2)}
                            </pre>
                          </details>
                        </>
                      ) : (
                        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-slate-600">
                          La ejecución finalizó con estado <strong>{ejecActiva.estado}</strong> sin metadatos JSON adicionales.
                        </div>
                      )}
                    </div>
                  </>
                )}

                {/* Historial Reciente de Ejecuciones de esta Tarea */}
                {historialTarea.length > 0 && (
                  <div className="space-y-2 pt-2 border-t border-slate-200">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">
                      Historial Reciente de esta Tarea ({historialTarea.length})
                    </h4>
                    <div className="overflow-x-auto border border-slate-200 rounded-xl max-h-48">
                      <table className="w-full text-left border-collapse text-[11px]">
                        <thead>
                          <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-bold">
                            <th className="py-2 px-3">Fecha y Hora</th>
                            <th className="py-2 px-3">Disparador</th>
                            <th className="py-2 px-3">Duración</th>
                            <th className="py-2 px-3">Estado</th>
                            <th className="py-2 px-3 text-right">Inspeccionar</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {historialTarea.map((h) => {
                            const hInicio = h.inicio_en || h.inicio || h.iniciado_en
                            const esSeleccionada = ejecActiva && String(ejecActiva.id) === String(h.id)
                            return (
                              <tr
                                key={h.id}
                                className={`transition ${esSeleccionada ? 'bg-blue-50/70 font-semibold' : 'hover:bg-slate-50'}`}
                              >
                                <td className="py-2 px-3 text-slate-700">
                                  {hInicio ? new Date(hInicio).toLocaleString('es-CL') : '—'}
                                </td>
                                <td className="py-2 px-3 capitalize text-slate-600">
                                  {h.disparador || h.origen || 'automático'}
                                </td>
                                <td className="py-2 px-3 text-slate-600">
                                  {h.duracion_segundos != null ? `${h.duracion_segundos.toFixed(1)} s` : '—'}
                                </td>
                                <td className="py-2 px-3">
                                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                                    h.estado === 'exitoso' || h.estado === 'completado'
                                      ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                      : 'bg-red-50 text-red-700 border border-red-200'
                                  }`}>
                                    {h.estado}
                                  </span>
                                </td>
                                <td className="py-2 px-3 text-right">
                                  <button
                                    type="button"
                                    onClick={() => setEjecucionSeleccionada(h)}
                                    className="text-[11px] font-semibold text-uct-blue-primary hover:underline cursor-pointer"
                                  >
                                    {esSeleccionada ? 'Viendo' : 'Ver detalle'}
                                  </button>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>

              {/* Pie del Modal */}
              <div className="p-4 border-t border-slate-100 bg-slate-50/60 flex items-center justify-between">
                <button
                  type="button"
                  disabled={tareaDetalleModal.en_curso || tareaEjecutando === tareaDetalleModal.nombre}
                  onClick={() => ejecutarTareaManual(tareaDetalleModal.nombre)}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-uct-blue-primary hover:bg-uct-blue-hover text-white transition cursor-pointer disabled:opacity-50"
                >
                  <Play size={12} />
                  <span>{tareaEjecutando === tareaDetalleModal.nombre ? 'Ejecutando...' : 'Ejecutar tarea ahora'}</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTareaDetalleModal(null)
                    setEjecucionSeleccionada(null)
                  }}
                  className="px-4 py-1.5 rounded-xl text-xs font-semibold bg-slate-200/80 hover:bg-slate-300/80 text-slate-700 transition cursor-pointer"
                >
                  Cerrar
                </button>
              </div>
            </div>
          </div>
        )
      })()}

      {/* Módulo 3 y 4: Calendario Académico y Caché en Memoria */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Calendario Académico UCT */}
        <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Calendar size={16} className="text-emerald-600" />
              <h3 className="text-sm font-bold text-slate-800">Calendario Académico UCT</h3>
            </div>
            <button
              type="button"
              onClick={() => syncCalendarioMutation.mutate()}
              disabled={syncCalendarioMutation.isPending}
              className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 transition cursor-pointer"
            >
              {syncCalendarioMutation.isPending ? 'Sincronizando...' : 'Actualizar'}
            </button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
            <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100">
              <span className="text-[10px] text-slate-400 block font-medium">Días Totales</span>
              <span className="text-sm font-bold text-slate-800">{estadoCalendario?.total_dias ?? '—'}</span>
            </div>
            <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100">
              <span className="text-[10px] text-slate-400 block font-medium">Feriados</span>
              <span className="text-sm font-bold text-red-600">{estadoCalendario?.total_feriados ?? '—'}</span>
            </div>
            <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100">
              <span className="text-[10px] text-slate-400 block font-medium">Recesos</span>
              <span className="text-sm font-bold text-amber-600">{estadoCalendario?.total_recesos ?? '—'}</span>
            </div>
            <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100">
              <span className="text-[10px] text-slate-400 block font-medium">Exámenes</span>
              <span className="text-sm font-bold text-blue-600">{estadoCalendario?.total_examenes ?? '—'}</span>
            </div>
          </div>
          <p className="text-[11px] text-slate-500">
            Fuente oficial: {estadoCalendario?.fuente_oficial || 'Portal de Secretaría General UCT'}
          </p>
        </div>

        {/* Caché en Memoria y Aceleración */}
        <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Layers size={16} className="text-uct-blue-primary" />
              <h3 className="text-sm font-bold text-slate-800">Caché en Memoria (TTLCache)</h3>
            </div>
            <button
              type="button"
              onClick={() => purgarCacheMutation.mutate()}
              disabled={purgarCacheMutation.isPending}
              className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 transition cursor-pointer flex items-center gap-1"
            >
              <Trash2 size={12} />
              <span>{purgarCacheMutation.isPending ? 'Purgando...' : 'Purgar Memoria'}</span>
            </button>
          </div>
          {mensajeCache && (
            <p className="text-xs text-emerald-700 bg-emerald-50 p-2 rounded-lg border border-emerald-100">
              {mensajeCache}
            </p>
          )}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
            <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100">
              <span className="text-[10px] text-slate-400 block font-medium">Aforo Vivo (60s)</span>
              <span className="text-sm font-bold text-slate-800">{statsCache?.aforo_vivo_items ?? 0}</span>
            </div>
            <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100">
              <span className="text-[10px] text-slate-400 block font-medium">KPIs (300s)</span>
              <span className="text-sm font-bold text-slate-800">{statsCache?.kpis_dia_items ?? 0}</span>
            </div>
            <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100">
              <span className="text-[10px] text-slate-400 block font-medium">Históricos (900s)</span>
              <span className="text-sm font-bold text-slate-800">{statsCache?.historicos_items ?? 0}</span>
            </div>
            <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100">
              <span className="text-[10px] text-slate-400 block font-medium">Total Claves</span>
              <span className="text-sm font-bold text-uct-blue-primary">{statsCache?.total_items ?? 0}</span>
            </div>
          </div>
          <p className="text-[11px] text-slate-500">
            Responde consultas concurrentes en &lt; 100 ms con cabecera HTTP X-Cache: HIT.
          </p>
        </div>
      </div>
    </div>
  )
}

