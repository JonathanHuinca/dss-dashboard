import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Calendar,
  Flag,
  Plus,
  Trash2,
  RefreshCw,
  Globe,
  Trash,
  AlertTriangle,
  Search,
  Filter,
  Eye,
  EyeOff,
  CheckCircle2,
  AlertCircle,
  X,
  Save,
  Info,
  Clock,
} from 'lucide-react'
import {
  fetchCalendarStatus,
  syncCalendarScrape,
  obtenerContingencias,
  crearContingencia,
  eliminarContingencia,
  ContingenciaAcademica,
  ContingenciaCrear,
  fetchCalendarEvents,
  depurarCalendarBasura,
  EventoCalendarioDetalle,
} from '../../../api/client'

interface Props {
  selectedAnio: number
}

const formatIsoDate = (dStr?: string | null): string => {
  if (!dStr) return ''
  try {
    const [y, m, d] = String(dStr).slice(0, 10).split('-')
    if (!y || !m || !d) return String(dStr).slice(0, 10)
    return `${d}/${m}/${y}`
  } catch {
    return String(dStr)
  }
}

const obtenerFechaHoyISO = (): string => {
  const date = new Date()
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export const CalendarioContingenciasSection: React.FC<Props> = ({ selectedAnio }) => {
  const queryClient = useQueryClient()
  const [calendarSyncMsg, setCalendarSyncMsg] = useState<string | null>(null)
  const [calendarSearch, setCalendarSearch] = useState('')
  const [calendarCategory, setCalendarCategory] = useState<string>('todos')
  const [showCalendarTable, setShowCalendarTable] = useState<boolean>(true)
  const [agruparPeriodos, setAgruparPeriodos] = useState<boolean>(true)

  // Modal de contingencias
  const [isContingenciaModalOpen, setIsContingenciaModalOpen] = useState(false)
  const [contingenciaDetalle, setContingenciaDetalle] = useState<ContingenciaAcademica | null>(null)
  const [contingenciaFormError, setContingenciaFormError] = useState<string | null>(null)
  const [contingenciaForm, setContingenciaForm] = useState<ContingenciaCrear>({
    fecha_inicio: obtenerFechaHoyISO(),
    fecha_fin: obtenerFechaHoyISO(),
    tipo: 'paro_federado',
    titulo: 'Paro General Estudiantil FEUCT',
    descripcion: 'Suspensión de actividades y acceso restringido al campus',
    espacio_id: null,
    subespacio: 'todos',
    hora_inicio: null,
    hora_fin: null,
    carreras_afectadas: 'Todas',
    implica_cierre_total: true,
  })

  const { data: calendarStatus } = useQuery({
    queryKey: ['calendar-status'],
    queryFn: fetchCalendarStatus,
    staleTime: 60_000,
  })

  const {
    data: calendarEvents = [],
    isLoading: isCalendarLoading,
    refetch: refetchCalendarEvents,
  } = useQuery<EventoCalendarioDetalle[]>({
    queryKey: ['calendar-events', selectedAnio, calendarCategory, calendarSearch, agruparPeriodos],
    queryFn: () =>
      fetchCalendarEvents({
        anio: selectedAnio,
        categoria: calendarCategory === 'todos' ? undefined : calendarCategory,
        busqueda: calendarSearch.trim() || undefined,
        agrupar_periodos: agruparPeriodos,
      }),
  })

  const { data: contingenciasList = [], isLoading: isLoadingContingencias } = useQuery({
    queryKey: ['contingencias', selectedAnio],
    queryFn: () => obtenerContingencias(selectedAnio),
  })

  const invalidarConsultasCalendarioYGraficos = () => {
    queryClient.invalidateQueries({ queryKey: ['contingencias'] })
    queryClient.invalidateQueries({ queryKey: ['calendar-status'] })
    queryClient.invalidateQueries({ queryKey: ['calendar-events'] })
    queryClient.invalidateQueries({ queryKey: ['calendario-resumen-anual'] })
    queryClient.invalidateQueries({ queryKey: ['hourly-flow'] })
    queryClient.invalidateQueries({ queryKey: ['vehicle-hourly-flow'] })
    queryClient.invalidateQueries({ queryKey: ['attendance-kpis'] })
    queryClient.invalidateQueries({ queryKey: ['vehicle-kpis'] })
    queryClient.invalidateQueries({ queryKey: ['weekly-evolution'] })
    queryClient.invalidateQueries({ queryKey: ['forecast-attendance'] })
    queryClient.invalidateQueries({ queryKey: ['forecast-parking'] })
    queryClient.invalidateQueries({ queryKey: ['forecast-14days'] })
  }

  const syncCalendarMutation = useMutation({
    mutationFn: syncCalendarScrape,
    onSuccess: (res) => {
      invalidarConsultasCalendarioYGraficos()
      setCalendarSyncMsg(`Sincronización web exitosa: ${res.total_days} días registrados desde UCT oficial`)
      setTimeout(() => setCalendarSyncMsg(null), 6000)
    },
    onError: (err: any) => {
      setCalendarSyncMsg(err.response?.data?.detail || 'Error al sincronizar con UCT web')
      setTimeout(() => setCalendarSyncMsg(null), 6000)
    },
  })

  const depurarMutation = useMutation({
    mutationFn: depurarCalendarBasura,
    onSuccess: (res) => {
      invalidarConsultasCalendarioYGraficos()
      setCalendarSyncMsg(`Depuración completada: ${res.registros_eliminados} registros obsoletos eliminados.`)
      setTimeout(() => setCalendarSyncMsg(null), 6000)
    },
    onError: (err: any) => {
      setCalendarSyncMsg(err.response?.data?.detail || 'Error al depurar registros basura')
      setTimeout(() => setCalendarSyncMsg(null), 6000)
    },
  })

  const createContingenciaMutation = useMutation({
    mutationFn: (data: ContingenciaCrear) => crearContingencia(data),
    onSuccess: () => {
      invalidarConsultasCalendarioYGraficos()
      setIsContingenciaModalOpen(false)
      setContingenciaFormError(null)
    },
    onError: (err: any) => {
      setContingenciaFormError(err.response?.data?.detail || 'Error al registrar contingencia')
    },
  })

  const deleteContingenciaMutation = useMutation({
    mutationFn: (id: number) => eliminarContingencia(id),
    onSuccess: () => {
      invalidarConsultasCalendarioYGraficos()
    },
  })

  return (
    <div className="space-y-6">
      {/* Tarjeta de Contingencias y Paros Académicos */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <div className="p-1.5 bg-red-50 text-red-600 rounded-lg border border-red-100">
                <Flag size={16} />
              </div>
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                Contingencias y Paros Académicos ({contingenciasList.length})
              </h3>
            </div>
            <p className="text-[11px] text-slate-500 mt-1">
              Registre paros estudiantiles, tomas o eventos sobrevenidos vinculados al año {selectedAnio}.
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              const hoy = obtenerFechaHoyISO()
              setContingenciaForm({
                fecha_inicio: hoy,
                fecha_fin: hoy,
                tipo: 'suspension_sala',
                titulo: 'Suspensión de Actividades Sala 2 Pecera',
                descripcion: '',
                espacio_id: 1,
                subespacio: 'sala_2',
                hora_inicio: null,
                hora_fin: null,
                carreras_afectadas: 'Todas',
                implica_cierre_total: true,
              })
              setContingenciaFormError(null)
              setIsContingenciaModalOpen(true)
            }}
            className="flex items-center gap-1.5 px-3.5 py-1.5 bg-red-600 text-white text-xs font-semibold rounded-xl hover:bg-red-700 transition shadow-xs cursor-pointer shrink-0"
          >
            <Plus size={14} />
            <span>Registrar Paro / Contingencia</span>
          </button>
        </div>

        {isLoadingContingencias ? (
          <div className="p-6 text-center text-xs text-slate-400">Cargando contingencias...</div>
        ) : contingenciasList.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-400">
            No se han registrado paros ni contingencias extraordinarias en el año {selectedAnio}.
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {contingenciasList.map((c) => (
              <div key={c.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 hover:bg-slate-50/60 transition">
                <div className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-bold text-slate-900">{c.titulo}</span>
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md border bg-red-50 text-red-700 border-red-200 uppercase">
                      {c.tipo.replace('_', ' ')}
                    </span>
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md border bg-slate-100 text-slate-700 border-slate-300">
                      {c.subespacio === 'sala_1'
                        ? 'Sala 1 (CSF02)'
                        : c.subespacio === 'sala_2'
                        ? 'Sala 2 (CSF04 Pecera)'
                        : c.subespacio && c.subespacio !== 'todos'
                        ? `Sector ${c.subespacio}`
                        : c.espacio_id === 1
                        ? 'Biblioteca (Todas las Salas)'
                        : c.espacio_id === 2
                        ? 'Estacionamiento (Todos los Sectores)'
                        : 'Campus General'}
                    </span>
                    {c.hora_inicio && c.hora_fin && (
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200">
                        {c.hora_inicio} a {c.hora_fin} hrs
                      </span>
                    )}
                    {c.implica_cierre_total && (
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-rose-100 text-rose-800 border border-rose-200">
                        Cierre de Sala / Recinto
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
                    <span className="flex items-center gap-1 font-medium text-slate-700">
                      <Calendar size={12} className="text-slate-400" />
                      {formatIsoDate(c.fecha_inicio)} al {formatIsoDate(c.fecha_fin)}
                    </span>
                    {c.carreras_afectadas && (
                      <span><strong>Alcance:</strong> {c.carreras_afectadas}</span>
                    )}
                    {c.descripcion && <span className="italic text-slate-400">"{c.descripcion}"</span>}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => setContingenciaDetalle(c)}
                    className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition cursor-pointer"
                    title="Ver hechos y detalles de la contingencia"
                  >
                    <Info size={14} className="text-uct-blue-primary" />
                    <span>Ver Detalles</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm(`¿Eliminar la contingencia "${c.titulo}"?`)) {
                        deleteContingenciaMutation.mutate(c.id)
                      }
                    }}
                    className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition cursor-pointer"
                    title="Eliminar contingencia"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tarjeta de Sincronización Scraper Calendario Secretaría General UCT */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <div className="p-1.5 bg-emerald-50 text-emerald-600 rounded-lg border border-emerald-100">
                <Globe size={16} />
              </div>
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                Calendario Académico Oficial UCT — Scraper Web
              </h3>
            </div>
            <p className="text-[11px] text-slate-500 mt-1">
              Sincroniza feriados oficiales, recesos de invierno/fiestas patrias y semanas de exámenes desde el portal de Secretaría General.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => depurarMutation.mutate()}
              disabled={depurarMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 text-xs font-semibold rounded-xl hover:bg-slate-200 border border-slate-200 transition cursor-pointer"
              title="Elimina registros duplicados o texto residual del scraper"
            >
              <Trash size={13} className="text-slate-500" />
              <span>{depurarMutation.isPending ? 'Depurando...' : 'Depurar Basura'}</span>
            </button>

            <button
              type="button"
              onClick={() => syncCalendarMutation.mutate()}
              disabled={syncCalendarMutation.isPending}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-emerald-600 text-white text-xs font-semibold rounded-xl hover:bg-emerald-700 transition shadow-xs cursor-pointer"
            >
              <RefreshCw size={14} className={syncCalendarMutation.isPending ? 'animate-spin' : ''} />
              <span>{syncCalendarMutation.isPending ? 'Sincronizando...' : 'Sincronizar Scraper'}</span>
            </button>
          </div>
        </div>

        {calendarSyncMsg && (
          <div className="p-3 mx-4 mt-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-xs flex items-center gap-2">
            <CheckCircle2 size={15} />
            <span>{calendarSyncMsg}</span>
          </div>
        )}

        {/* Resumen de Días Catalogados */}
        <div className="p-4 grid grid-cols-2 sm:grid-cols-5 gap-3 border-b border-slate-100 bg-slate-50/50">
          <div className="bg-white p-3 rounded-xl border border-slate-100 shadow-2xs">
            <span className="text-[10px] text-slate-400 block font-medium">Total Días</span>
            <span className="text-base font-bold text-slate-800">{calendarStatus?.total_dias ?? '—'}</span>
          </div>
          <div className="bg-white p-3 rounded-xl border border-slate-100 shadow-2xs">
            <span className="text-[10px] text-slate-400 block font-medium">Feriados</span>
            <span className="text-base font-bold text-red-600">{calendarStatus?.total_feriados ?? '—'}</span>
          </div>
          <div className="bg-white p-3 rounded-xl border border-slate-100 shadow-2xs">
            <span className="text-[10px] text-slate-400 block font-medium">Recesos</span>
            <span className="text-base font-bold text-amber-600">{calendarStatus?.total_recesos ?? '—'}</span>
          </div>
          <div className="bg-white p-3 rounded-xl border border-slate-100 shadow-2xs">
            <span className="text-[10px] text-slate-400 block font-medium">Exámenes</span>
            <span className="text-base font-bold text-blue-600">{calendarStatus?.total_examenes ?? '—'}</span>
          </div>
          <div className="bg-white p-3 rounded-xl border border-slate-100 shadow-2xs">
            <span className="text-[10px] text-slate-400 block font-medium">Paros/Tomas</span>
            <span className="text-base font-bold text-purple-600">
              {(calendarStatus?.total_paros_federados ?? 0) + (calendarStatus?.total_paros_carrera ?? 0)}
            </span>
          </div>
        </div>
      </div>

      {/* Modal Registrar Contingencia o Paro */}
      {isContingenciaModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 overflow-y-auto">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-lg w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Flag size={18} className="text-red-600" />
                <h3 className="text-sm font-bold text-slate-900">
                  Registrar Paro o Contingencia Académica
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsContingenciaModalOpen(false)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-lg transition cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault()
                createContingenciaMutation.mutate(contingenciaForm)
              }}
              className="p-5 space-y-4"
            >
              {contingenciaFormError && (
                <div className="p-3 bg-rose-50 text-rose-700 text-xs rounded-xl border border-rose-100 flex items-center gap-2">
                  <AlertCircle size={14} className="shrink-0" />
                  <span>{contingenciaFormError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Tipo de Hecho Relevante
                </label>
                <select
                  value={contingenciaForm.tipo}
                  onChange={(e) => setContingenciaForm((prev) => ({ ...prev, tipo: e.target.value }))}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-red-100 focus:outline-none"
                >
                  <option value="suspension_sala">Suspensión Puntual de Sala / Sector</option>
                  <option value="paro_federado">Paro Federado (Huelga General Estudiantil FEUCT)</option>
                  <option value="paro_carrera">Paro por Carrera o Facultad</option>
                  <option value="toma_campus">Toma de Instalaciones / Campus</option>
                  <option value="climatica">Contingencia o Alerta Climática</option>
                  <option value="duelo">Duelo o Suspensión Institucional</option>
                  <option value="otro">Otro Hecho Relevante</option>
                </select>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Recinto Afectado
                  </label>
                  <select
                    value={contingenciaForm.espacio_id ?? ''}
                    onChange={(e) => {
                      const val = e.target.value === '' ? null : parseInt(e.target.value, 10)
                      setContingenciaForm((prev) => ({
                        ...prev,
                        espacio_id: val,
                        subespacio: 'todos',
                      }))
                    }}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-red-100 focus:outline-none"
                  >
                    <option value="">Campus General (Ambos Recintos)</option>
                    <option value="1">Biblioteca Campus San Francisco</option>
                    <option value="2">Estacionamiento Campus San Francisco</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Sala o Sector Específico
                  </label>
                  <select
                    value={contingenciaForm.subespacio || 'todos'}
                    onChange={(e) => setContingenciaForm((prev) => ({ ...prev, subespacio: e.target.value }))}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-red-100 focus:outline-none"
                  >
                    {contingenciaForm.espacio_id === 1 ? (
                      <>
                        <option value="todos">Todas las Salas (Biblioteca Completa)</option>
                        <option value="sala_1">Solo Sala 1: CSF02 (2° Piso)</option>
                        <option value="sala_2">Solo Sala 2: CSF04 Pecera (1° Piso)</option>
                      </>
                    ) : contingenciaForm.espacio_id === 2 ? (
                      <>
                        <option value="todos">Todos los Sectores (Estacionamiento Completo)</option>
                        <option value="CSF11">Solo Sector CSF11 — Edificio 11</option>
                        <option value="CSF21">Solo Sector CSF21 — Edificio 21</option>
                        <option value="CHS01">Solo Sector CHS01 — Hospital Simulación</option>
                      </>
                    ) : (
                      <option value="todos">Todas las Salas y Sectores</option>
                    )}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Título del Evento
                </label>
                <input
                  type="text"
                  required
                  placeholder="Ej. Paro General FEUCT — Movilización"
                  value={contingenciaForm.titulo}
                  onChange={(e) => setContingenciaForm((prev) => ({ ...prev, titulo: e.target.value }))}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-red-100 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Fecha de Inicio</label>
                  <input
                    type="date"
                    required
                    value={contingenciaForm.fecha_inicio}
                    onChange={(e) => setContingenciaForm((prev) => ({ ...prev, fecha_inicio: e.target.value }))}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-red-100 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Fecha de Término</label>
                  <input
                    type="date"
                    required
                    value={contingenciaForm.fecha_fin}
                    onChange={(e) => setContingenciaForm((prev) => ({ ...prev, fecha_fin: e.target.value }))}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-red-100 focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Hora Inicio (Opcional — Vacío = Todo el día)
                  </label>
                  <input
                    type="time"
                    value={contingenciaForm.hora_inicio || ''}
                    onChange={(e) =>
                      setContingenciaForm((prev) => ({
                        ...prev,
                        hora_inicio: e.target.value ? e.target.value : null,
                      }))
                    }
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-red-100 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Hora Término (Opcional — Vacío = Todo el día)
                  </label>
                  <input
                    type="time"
                    value={contingenciaForm.hora_fin || ''}
                    onChange={(e) =>
                      setContingenciaForm((prev) => ({
                        ...prev,
                        hora_fin: e.target.value ? e.target.value : null,
                      }))
                    }
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-red-100 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Carreras Afectadas</label>
                <input
                  type="text"
                  placeholder="Ej. Todas (Campus San Francisco)"
                  value={contingenciaForm.carreras_afectadas || ''}
                  onChange={(e) => setContingenciaForm((prev) => ({ ...prev, carreras_afectadas: e.target.value }))}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-red-100 focus:outline-none"
                />
              </div>

              <div className="flex items-center gap-2 p-3 bg-red-50/60 rounded-xl border border-red-100">
                <input
                  type="checkbox"
                  id="cierreTotalCheck"
                  checked={contingenciaForm.implica_cierre_total}
                  onChange={(e) => setContingenciaForm((prev) => ({ ...prev, implica_cierre_total: e.target.checked }))}
                  className="rounded text-red-600 focus:ring-red-500 h-4 w-4 cursor-pointer"
                />
                <label htmlFor="cierreTotalCheck" className="text-xs text-slate-700 font-medium cursor-pointer">
                  Implicó suspensión total de actividades o cierre de recintos
                </label>
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsContingenciaModalOpen(false)}
                  className="px-3.5 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={createContingenciaMutation.isPending}
                  className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-xl text-xs font-semibold hover:bg-red-700 transition shadow-xs cursor-pointer disabled:opacity-50"
                >
                  <Save size={14} />
                  <span>{createContingenciaMutation.isPending ? 'Guardando...' : 'Guardar'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Detalle de Hechos y Contingencia */}
      {contingenciaDetalle && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 overflow-y-auto">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-lg w-full p-5 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="p-1.5 bg-red-50 text-red-600 rounded-lg border border-red-100">
                  <Flag size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Detalle de Hechos y Contingencia
                  </h3>
                  <span className="text-[11px] text-slate-500">
                    Registro institucional extraordinario — Año {selectedAnio}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setContingenciaDetalle(null)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-lg transition cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-3.5 text-xs">
              {/* Título y Badges */}
              <div>
                <h4 className="text-sm font-bold text-slate-900 mb-1.5">
                  {contingenciaDetalle.titulo}
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase bg-red-50 text-red-700 border border-red-200">
                    {contingenciaDetalle.tipo.replace('_', ' ')}
                  </span>
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
                    {contingenciaDetalle.subespacio === 'sala_1'
                      ? 'Sala 1 (CSF02 2° Piso)'
                      : contingenciaDetalle.subespacio === 'sala_2'
                      ? 'Sala 2 (CSF04 Pecera 1° Piso)'
                      : contingenciaDetalle.subespacio && contingenciaDetalle.subespacio !== 'todos'
                      ? `Sector ${contingenciaDetalle.subespacio}`
                      : contingenciaDetalle.espacio_id === 1
                      ? 'Biblioteca (Todas las Salas)'
                      : contingenciaDetalle.espacio_id === 2
                      ? 'Estacionamiento (Todos los Sectores)'
                      : 'Campus San Francisco General'}
                  </span>
                  {contingenciaDetalle.implica_cierre_total ? (
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
                      Cierre Total de Recinto
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                      Operación Parcial
                    </span>
                  )}
                </div>
              </div>

              {/* Hechos y Observaciones */}
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block">
                  Descripción de los Hechos:
                </span>
                <p className="text-slate-700 text-xs leading-relaxed">
                  {contingenciaDetalle.descripcion || (
                    <span className="italic text-slate-400">Sin descripción o hechos adicionales registrados al momento de la creación.</span>
                  )}
                </p>
              </div>

              {/* Parámetros Operativos */}
              <div className="grid grid-cols-2 gap-2.5">
                <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-[10px] font-semibold text-slate-500 block mb-0.5">Vigencia Temporal:</span>
                  <span className="font-bold text-slate-800 block text-xs">
                    {formatIsoDate(contingenciaDetalle.fecha_inicio)} al {formatIsoDate(contingenciaDetalle.fecha_fin)}
                  </span>
                </div>
                <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-[10px] font-semibold text-slate-500 block mb-0.5">Horario Afectado:</span>
                  <span className="font-bold text-slate-800 block text-xs">
                    {contingenciaDetalle.hora_inicio && contingenciaDetalle.hora_fin
                      ? `${contingenciaDetalle.hora_inicio} a ${contingenciaDetalle.hora_fin} hrs`
                      : 'Jornada Completa'}
                  </span>
                </div>
              </div>

              {/* Alcance de Carreras */}
              <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-200">
                <span className="text-[10px] font-semibold text-slate-500 block mb-0.5">Alcance Institucional:</span>
                <span className="font-medium text-slate-800 block text-xs">
                  {contingenciaDetalle.carreras_afectadas || 'Todas las carreras y facultades'}
                </span>
              </div>

              {/* Impacto en Modelos Analíticos */}
              <div className="p-3 bg-purple-50/80 border border-purple-200 rounded-xl space-y-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-purple-900 block">
                  Tratamiento en Motor Analítico y Modelos Predictivos:
                </span>
                <p className="text-[11px] text-purple-800 leading-relaxed">
                  Este período se aísla automáticamente en el entrenamiento de Prophet y GBR para evitar distorsiones en los pronósticos de demanda habitual, reconociendo el aforo nulo o reducido como un evento extraordinario justificado.
                </p>
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-end">
              <button
                type="button"
                onClick={() => setContingenciaDetalle(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded-xl text-xs transition cursor-pointer"
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

