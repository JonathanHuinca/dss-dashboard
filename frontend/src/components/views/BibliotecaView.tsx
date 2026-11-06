import React, { Suspense, lazy, memo, useState, useEffect, useMemo } from 'react'
import {
  Users,
  Clock,
  BarChart2,
  TrendingDown,
  Wifi,
  Flame,
  TrendingUp,
  AlertTriangle,
  DoorClosed,
  Calendar,
  BrainCircuit,
  Activity,
  Layers,
  RotateCcw,
  RotateCw,
  LayoutGrid,
  GraduationCap,
  Building2,
  FileSpreadsheet,
  Loader2,
  Share2,
  Moon,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { ModalReporte24Horas } from '../reports/ModalReporte24Horas'
import { fetchAnalisis24h } from '../../api/asistencia'
import { SeccionCampana24Horas } from './biblioteca/SeccionCampana24Horas'
import { KpiCard } from '../ui/KpiCard'
import { ChartCard } from '../ui/ChartCard'
import { LiveBadge } from '../ui/LiveBadge'
import { DateRange } from '../../types/dateRange'
import { RawDataTable } from '../ui/RawDataTable'
import { ScopeSelector } from '../ui/ScopeSelector'
import { ChartVisibilitySelector, ChartConfigItem } from '../ui/ChartVisibilitySelector'
import { ExcelBatchExportModal } from '../ui/ExcelBatchExportModal'
import { CompartirReporteModal } from '../reports/CompartirReporteModal'
import { BarraLateralSecciones, SeccionModuloItem } from '../layout/BarraLateralSecciones'
import { KPIBanner } from '../layout/KPIBanner'
import { DataFilters, fetchEspacioInfo, dispararActualizacionModelos, consultarResumenTareasAdmin } from '../../api/client'
import { exportarPlantillaOficialSalasEstudio } from '../../utils/excelExport'
import { useDownloadProgress } from '../../context/DownloadProgressContext'
import { useAuth } from '../../context/AuthContext'
import { useAssistant } from '../../context/AssistantContext'
import { useQuery, useQueryClient } from '@tanstack/react-query'


import {
  useAttendanceKpis,
  useOccupancyRealtime,
  useAttendanceHourlyFlow,
  useHeatmap,
  useForecastAttendance,
  useAlerts,
  usePeakValley,
  useWeeklyEvolution,
  useMonthlyVolume,
  useAcademicMilestones,
  useDoorsUsage,
  useCheckinsDistribution,
  useVisitProfilesDonut,
  useRoomsComparison,
  useCurricularDistribution,
  useSalasBiblioteca,
  useDailyAverageAttendance,
} from '../../hooks/useAttendance'

// Lazy load y Memoización de los gráficos
const OccupancyAreaChart = memo(lazy(() => import('../charts/OccupancyAreaChart').then(m => ({ default: m.OccupancyAreaChart }))))
const ForecastLineChart = memo(lazy(() => import('../charts/ForecastLineChart').then(m => ({ default: m.ForecastLineChart }))))
const HeatmapChart = memo(lazy(() => import('../charts/HeatmapChart').then(m => ({ default: m.HeatmapChart }))))
const HourlyBarChart = memo(lazy(() => import('../charts/HourlyBarChart').then(m => ({ default: m.HourlyBarChart }))))
const PeakValleyPlotlyChart = memo(lazy(() => import('../charts/PeakValleyPlotlyChart').then(m => ({ default: m.PeakValleyPlotlyChart }))))
const WeeklyEvolutionPlotlyChart = memo(lazy(() => import('../charts/WeeklyEvolutionPlotlyChart').then(m => ({ default: m.WeeklyEvolutionPlotlyChart }))))
const MonthlyVolumePlotlyChart = memo(lazy(() => import('../charts/MonthlyVolumePlotlyChart').then(m => ({ default: m.MonthlyVolumePlotlyChart }))))
const AcademicMilestonesPlotlyChart = memo(lazy(() => import('../charts/AcademicMilestonesPlotlyChart').then(m => ({ default: m.AcademicMilestonesPlotlyChart }))))
const DoorUsagePlotlyChart = memo(lazy(() => import('../charts/DoorUsagePlotlyChart').then(m => ({ default: m.DoorUsagePlotlyChart }))))
const RoomComparisonPlotlyChart = memo(lazy(() => import('../charts/RoomComparisonPlotlyChart').then(m => ({ default: m.RoomComparisonPlotlyChart }))))
const CurricularDistributionPlotlyChart = memo(lazy(() => import('../charts/CurricularDistributionPlotlyChart').then(m => ({ default: m.CurricularDistributionPlotlyChart }))))
const CheckinDistributionPlotlyChart = memo(lazy(() => import('../charts/CheckinDistributionPlotlyChart').then(m => ({ default: m.CheckinDistributionPlotlyChart }))))
const VisitProfilesPlotlyChart = memo(lazy(() => import('../charts/VisitProfilesPlotlyChart').then(m => ({ default: m.VisitProfilesPlotlyChart }))))
const DailyAverageAttendancePlotlyChart = memo(lazy(() => import('../charts/DailyAverageAttendancePlotlyChart').then(m => ({ default: m.DailyAverageAttendancePlotlyChart }))))

const DEFAULT_CAPACIDAD = 350

function fmt(n: number | undefined, dec = 0) {
  if (n === undefined || n === null) return '—'
  return n.toLocaleString('es-CL', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

function ChartSkeleton() {
  return (
    <div className="h-full min-h-[280px] w-full flex items-center justify-center bg-gray-50/50 dark:bg-gray-800/20 rounded-xl animate-pulse border border-gray-100 dark:border-gray-800">
      <div className="flex flex-col items-center gap-3 opacity-50">
        <BarChart2 className="text-uct-primary" size={32} />
        <span className="text-sm font-medium text-uct-text-muted">Cargando visualización...</span>
      </div>
    </div>
  )
}

function SectionHeader({
  icon: Icon,
  title,
  subtitle,
  badge,
}: {
  icon: React.ElementType
  title: string
  subtitle: string
  badge?: string
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-slate-200/80">
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-xl bg-uct-blue-primary/10 flex items-center justify-center text-uct-blue-primary shadow-2xs">
          <Icon size={16} />
        </div>
        <div>
          <h3 className="text-sm font-bold text-slate-800 tracking-tight">{title}</h3>
          <p className="text-[11px] text-slate-500">{subtitle}</p>
        </div>
      </div>
      {badge && (
        <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold border border-slate-200">
          {badge}
        </span>
      )}
    </div>
  )
}

const BIBLIOTECA_CHARTS: ChartConfigItem[] = [
  // 1. Aforo y Demanda en Tiempo Real
  { id: 'aforo_curva', label: 'Curva de Aforo Concurrente', category: 'Aforo en Tiempo Real', description: 'Ocupación por minuto vs umbrales 70%, 85% y límite 350' },
  { id: 'prophet_diario', label: 'Pronóstico Prophet (3 Días)', category: 'Aforo en Tiempo Real', description: 'Demanda predictiva horaria a corto plazo' },
  // 2. Demografía Institucional y Distribución Curricular
  { id: 'distribucion_curricular', label: 'Distribución por Carrera Institucional (Ley 21.719)', category: 'Demografía y Carreras', description: 'Padrón académico disociado por carreras universitarias' },
  // 3. Análisis de Comportamiento y Perfiles de Visita
  { id: 'perfiles_visita', label: 'Perfiles de Visita y Tasa de Rebote (Donut)', category: 'Comportamiento y Estadía', description: 'Distribución porcentual de Rebote (<15 min), Estándar (15–120 min) y Profundo (>120 min)' },
  // 4. Patrones Temporales y Distribución Horaria
  { id: 'flujo_horario', label: 'Flujo Horario (Entradas vs Salidas)', category: 'Distribución Horaria', description: 'Distribución horaria ciclo 00:00 a 23:00' },
  { id: 'mapa_calor', label: 'Mapa de Calor (Día × Hora)', category: 'Distribución Horaria', description: 'Matriz de calor de afluencia diurna o 24 horas' },
  // 5. Puntos de Acceso Físico, Torniquetes y Salas
  { id: 'comparativa_salas', label: 'Comparativa de Salas (Sala 1 vs Sala 2)', category: 'Accesos y Hardware', description: 'Afluencia comparada y curvas horarias entre salas físicas' },
  { id: 'torniquetes', label: 'Torniquetes y Accesos Universales', category: 'Accesos y Hardware', description: 'Distribución física de hardware Sala 1 (2202/2184, 2177/2170) y Sala 2 (2592/2587, 3411/3416)' },
  { id: 'distribucion_marcajes', label: 'Frecuencia de Marcajes Diarios', category: 'Accesos y Hardware', description: 'Distribución de marcajes únicos, dobles o excesivos' },
  // 6. Tendencias Históricas y Calendario Académico
  { id: 'volumen_mensual', label: 'Volumen Mensual Consolidado', category: 'Tendencias Históricas', description: 'Total acumulado mes a mes de asistencias' },
  { id: 'evolucion_semanal', label: 'Evolución Semanal de Usuarios', category: 'Tendencias Históricas', description: 'Comparación semanal de usuarios únicos y promedio diario' },
  { id: 'promedio_dias_semana', label: 'Promedio Diario por Día de la Semana (Lun–Dom)', category: 'Tendencias Históricas', description: 'Promedio de ingresos desglosando Sala 1, Sala 2 y total general de la Biblioteca' },
  { id: 'hitos_academicos', label: 'Comparativa Hitos Académicos', category: 'Tendencias Históricas', description: 'Afluencia según clases regulares, exámenes y recesos' },
]

const SECCIONES_MODULO_BIBLIOTECA: SeccionModuloItem[] = [
  { id: 'seccion_1', numero: 1, titulo: '1. Resumen y Demanda General', subtitulo: 'Aforo, Padrón, Perfiles y Demanda Horaria', icono: Activity, cantidadGraficos: 6 },
  { id: 'seccion_2', numero: 2, titulo: '2. Salas y Torniquetes', subtitulo: 'Sala 1 vs Sala 2, Torniquetes', icono: DoorClosed, cantidadGraficos: 3 },
  { id: 'seccion_3', numero: 3, titulo: '3. Evolución e Hitos', subtitulo: 'Mensual, Semanal, Lun-Dom, Hitos', icono: Calendar, cantidadGraficos: 4 },
  { id: 'seccion_4', numero: 4, titulo: '4. Explorador de Microdatos', subtitulo: 'Tabla paginada de eventos', icono: Layers, cantidadGraficos: 1 },
  { id: 'seccion_5', numero: 5, titulo: '5. Campaña 24 Horas Exámenes', subtitulo: 'Flujo Nocturno y Justificación', icono: Moon, cantidadGraficos: 5 },
]

interface Props {
  dateRange?: DateRange
  onRangeChange?: (range: DateRange) => void
  filters?: DataFilters
  onFiltersChange?: (filters: DataFilters) => void
}

export function BibliotecaView({ dateRange, onRangeChange, filters: externalFilters, onFiltersChange }: Props) {
  const { ejecutarDescarga } = useDownloadProgress()
  const [modalCompartirAbierto, setModalCompartirAbierto] = useState(false)
  const [loadStage, setLoadStage] = useState(2)
  const [precargaSilenciosaLista, setPrecargaSilenciosaLista] = useState(false)
  const [barraLateralExpandida, setBarraLateralExpandida] = useState(true)
  const [seccionActivaBiblioteca, setSeccionActivaBiblioteca] = useState<string | 'todas'>(() => {
    try {
      const guardada = localStorage.getItem('uct_seccion_activa_biblioteca')
      if (guardada) return guardada
    } catch { }
    return 'seccion_1'
  })

  // Memoria de secciones visitadas para transiciones 100% instantáneas sin repintado
  const [seccionesVisitadas, setSeccionesVisitadas] = useState<Set<string>>(() => {
    try {
      const guardada = localStorage.getItem('uct_seccion_activa_biblioteca') || 'seccion_1'
      return new Set(['seccion_1', guardada])
    } catch {
      return new Set(['seccion_1'])
    }
  })

  const cambiarSeccionBiblioteca = (nuevaSeccion: string | 'todas') => {
    setSeccionActivaBiblioteca(nuevaSeccion)
    setSeccionesVisitadas(prev => {
      if (nuevaSeccion === 'todas') {
        return new Set(['seccion_1', 'seccion_2', 'seccion_3', 'seccion_4', 'seccion_5', 'seccion_6', 'seccion_7', 'seccion_8'])
      }
      const next = new Set(prev)
      next.add(nuevaSeccion)
      return next
    })
    try {
      localStorage.setItem('uct_seccion_activa_biblioteca', nuevaSeccion)
    } catch { }
  }

  const esSeccionVisible = (idSeccion: string): boolean => {
    return seccionActivaBiblioteca === 'todas' || seccionActivaBiblioteca === idSeccion
  }

  const seccionMontada = (idSeccion: string): boolean => {
    return seccionActivaBiblioteca === 'todas' || seccionesVisitadas.has(idSeccion)
  }

  const claseSeccion = (idSeccion: string, clasesExtra = '') => {
    const visible = esSeccionVisible(idSeccion)
    return `${visible ? 'block' : 'hidden'} ${clasesExtra}`
  }
  const [internalFilters, setInternalFilters] = useState<DataFilters>({
    alcance: 'conformes',
    regimen_horario: 'todos',
    direccion: 'todos',
    dias_semana: '',
    door: '',
    perfil_visita: 'todos',
    marcajes: 'todos',
    incluir_pausas_bano: true,
    desduplicar_rafagas: true,
  })

  const filters = externalFilters ?? internalFilters
  const setFilters: React.Dispatch<React.SetStateAction<DataFilters>> = (valOrFn) => {
    const nextVal = typeof valOrFn === 'function' ? (valOrFn as any)(filters) : valOrFn
    if (onFiltersChange) {
      onFiltersChange(nextVal)
    } else {
      setInternalFilters(nextVal)
    }
  }

  // Sincronización continua de filtros y período con el asistente IA
  const { setFiltrosActivos, setPeriodoActivo } = useAssistant()
  useEffect(() => {
    if (filters) {
      setFiltrosActivos(filters)
    }
  }, [filters, setFiltrosActivos])
  useEffect(() => {
    if (dateRange) {
      setPeriodoActivo({
        inicio: dateRange.inicio,
        fin: dateRange.fin,
        startDate: dateRange.inicio,
        endDate: dateRange.fin,
        label: dateRange.label,
      })
    }
  }, [dateRange, setPeriodoActivo])

  // Estado para visibilidad personalizada de gráficos
  const [visibleCharts, setVisibleCharts] = useState<Record<string, boolean>>(() => {
    try {
      const saved = localStorage.getItem('uct_charts_visible_biblioteca')
      if (saved) return JSON.parse(saved)
    } catch { }
    return BIBLIOTECA_CHARTS.reduce<Record<string, boolean>>((acc, c) => ({ ...acc, [c.id]: true }), {})
  })

  const toggleChart = (id: string) => {
    setVisibleCharts(prev => {
      const next = { ...prev, [id]: prev[id] === false ? true : false }
      try { localStorage.setItem('uct_charts_visible_biblioteca', JSON.stringify(next)) } catch { }
      return next
    })
  }

  const selectAllCharts = () => {
    const next = BIBLIOTECA_CHARTS.reduce<Record<string, boolean>>((acc, c) => ({ ...acc, [c.id]: true }), {})
    setVisibleCharts(next)
    try { localStorage.setItem('uct_charts_visible_biblioteca', JSON.stringify(next)) } catch { }
  }

  const deselectAllCharts = () => {
    const next = BIBLIOTECA_CHARTS.reduce<Record<string, boolean>>((acc, c) => ({ ...acc, [c.id]: false }), {})
    setVisibleCharts(next)
    try { localStorage.setItem('uct_charts_visible_biblioteca', JSON.stringify(next)) } catch { }
  }

  useEffect(() => {
    const t1 = setTimeout(() => setLoadStage(1), 50)
    const t2 = setTimeout(() => setLoadStage(2), 120)
    const tPrecarga = setTimeout(() => setPrecargaSilenciosaLista(true), 300)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
      clearTimeout(tPrecarga)
    }
  }, [])

  // Nivel 0 (Inmediato): KPIs vitales y datos en tiempo real
  const kpis = useAttendanceKpis(dateRange?.inicio, dateRange?.fin, filters)
  const live = useOccupancyRealtime()
  const flow = useAttendanceHourlyFlow(dateRange?.inicio, dateRange?.fin, filters)
  const alerts = useAlerts()

  const espacioQuery = useQuery({
    queryKey: ['espacio-info', 1],
    queryFn: () => fetchEspacioInfo(1),
    staleTime: 60_000,
  })

  // Capacidades por sala física de biblioteca
  const salasQuery = useSalasBiblioteca(1)
  const salasBiblioteca = salasQuery.data ?? []
  const sala1 = salasBiblioteca.find(s => s.codigo?.includes('CSF02') || s.id === 1)
  const sala2 = salasBiblioteca.find(s => s.codigo?.includes('CSF04') || s.id === 2)
  const capSala1 = sala1?.capacidad_asientos ?? 124
  const capSala2 = sala2?.capacidad_asientos ?? 226
  const capTotal = capSala1 + capSala2

  const capacidadActiva = useMemo(() => {
    if (filters.sala) {
      const sLow = filters.sala.toLowerCase()
      if (sLow.includes('csf02') || sLow.includes('sala_1') || sLow === '1') return capSala1
      if (sLow.includes('csf04') || sLow.includes('sala_2') || sLow === '2') return capSala2
    }
    return espacioQuery.data?.capacidad_max || capTotal || DEFAULT_CAPACIDAD
  }, [filters.sala, capSala1, capSala2, capTotal, espacioQuery.data?.capacidad_max])

  const salaLabel = useMemo(() => {
    if (!filters.sala) return undefined
    const sLow = filters.sala.toLowerCase()
    if (sLow.includes('csf02') || sLow.includes('sala_1') || sLow === '1') return 'Sala 1 (CSF02 2° Piso)'
    if (sLow.includes('csf04') || sLow.includes('sala_2') || sLow === '2') return 'Sala 2 (CSF04 Pecera 1° Piso)'
    return filters.sala
  }, [filters.sala])

  const { roles = [], userRole } = useAuth()
  const puedeCompartirReportes = userRole !== 'Guardia_Seguridad'
  const esAdminSistema = useMemo(() => {
    return (
      roles.includes('Admin_Sistema') ||
      roles.includes('SuperAdmin') ||
      userRole === 'Admin_Sistema' ||
      userRole === 'SuperAdmin'
    )
  }, [roles, userRole])

  const capacidad = capacidadActiva
  const queryClient = useQueryClient()
  const [isRetraining, setIsRetraining] = useState(false)
  const [retrainMsg, setRetrainMsg] = useState<string | null>(null)
  const sondeoRef = React.useRef<any>(null)

  useEffect(() => {
    return () => {
      if (sondeoRef.current) clearInterval(sondeoRef.current)
    }
  }, [])

  const handleRetrain = async () => {
    if (isRetraining) return
    try {
      setIsRetraining(true)
      setRetrainMsg('Iniciando...')
      await dispararActualizacionModelos()
      setRetrainMsg('Actualizando modelo...')

      const inicioSondeo = Date.now()
      if (sondeoRef.current) clearInterval(sondeoRef.current)

      sondeoRef.current = setInterval(async () => {
        try {
          const resumen = await consultarResumenTareasAdmin()
          const tareaMl = resumen.catalogo.find((t: any) => t.nombre === 'reentrenar_modelos_ml')
          const transcurrido = Date.now() - inicioSondeo

          if (!tareaMl?.en_curso || transcurrido > 60000) {
            clearInterval(sondeoRef.current)
            sondeoRef.current = null
            queryClient.invalidateQueries({ queryKey: ['forecast-attendance'] })
            setIsRetraining(false)
            setRetrainMsg('Modelo actualizado')
            setTimeout(() => setRetrainMsg(null), 3500)
          }
        } catch {
          if (Date.now() - inicioSondeo > 60000) {
            clearInterval(sondeoRef.current)
            sondeoRef.current = null
            setIsRetraining(false)
            setRetrainMsg(null)
          }
        }
      }, 2500)
    } catch (err: any) {
      if (sondeoRef.current) {
        clearInterval(sondeoRef.current)
        sondeoRef.current = null
      }
      setIsRetraining(false)
      setRetrainMsg(err.response?.data?.detail || 'Error al actualizar modelo')
      setTimeout(() => setRetrainMsg(null), 3500)
    }
  }

  const [salaPronostico, setSalaPronostico] = useState<'todas' | 'sala1' | 'sala2'>('todas')
  const forecast = useForecastAttendance(salaPronostico)


  // Carga inmediata de la sección activa y precarga silenciosa en segundo plano a los 300ms
  const heatmap = useHeatmap(dateRange?.inicio, dateRange?.fin, 1, filters, { enabled: esSeccionVisible('seccion_4') || precargaSilenciosaLista })
  const peakValley = usePeakValley(dateRange?.inicio, dateRange?.fin, { enabled: esSeccionVisible('seccion_4') || precargaSilenciosaLista })
  const weekly = useWeeklyEvolution(dateRange?.inicio, dateRange?.fin, 1, filters, { enabled: esSeccionVisible('seccion_6') || precargaSilenciosaLista })
  const roomsComp = useRoomsComparison(dateRange?.inicio, dateRange?.fin, filters, 1, { enabled: esSeccionVisible('seccion_1') || esSeccionVisible('seccion_5') || precargaSilenciosaLista })
  const dailyAvg = useDailyAverageAttendance(dateRange?.inicio, dateRange?.fin, filters, 1, { enabled: esSeccionVisible('seccion_6') || precargaSilenciosaLista })

  const monthly = useMonthlyVolume(dateRange?.inicio, dateRange?.fin, 1, filters, { enabled: esSeccionVisible('seccion_6') || precargaSilenciosaLista })
  const milestones = useAcademicMilestones(dateRange?.inicio, dateRange?.fin, 1, filters, { enabled: esSeccionVisible('seccion_6') || precargaSilenciosaLista })
  const doors = useDoorsUsage(dateRange?.inicio, dateRange?.fin, filters, { enabled: esSeccionVisible('seccion_5') || precargaSilenciosaLista })
  const checkins = useCheckinsDistribution(dateRange?.inicio, dateRange?.fin, filters, { enabled: esSeccionVisible('seccion_3') || esSeccionVisible('seccion_5') || precargaSilenciosaLista })
  const curricular = useCurricularDistribution(dateRange?.inicio, dateRange?.fin, filters, 1, { enabled: esSeccionVisible('seccion_2') || precargaSilenciosaLista })
  const visitProfiles = useVisitProfilesDonut(dateRange?.inicio, dateRange?.fin, filters, 1, { enabled: esSeccionVisible('seccion_3') || precargaSilenciosaLista })

  const bibAlert = alerts.data?.alertas.find(a => a.recinto === 'biblioteca')

  const lastTs = live.data?.timestamp
    ? new Date(live.data.timestamp).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })
    : undefined

  const handleResetAllCharts = () => {
    document.querySelectorAll<HTMLElement>('.chart-resizable-card').forEach((el) => {
      el.style.width = ''
      el.style.height = ''
    })
    window.dispatchEvent(new CustomEvent('uct:reset-charts-layout'))
    setTimeout(() => {
      window.dispatchEvent(new Event('resize'))
    }, 100)
  }

  const [isExportingPlantilla, setIsExportingPlantilla] = useState(false)
  const [modalReporte24hAbierto, setModalReporte24hAbierto] = useState(false)
  const [campana24hSeleccionada, setCampana24hSeleccionada] = useState<number | undefined>(undefined)
  const [bloqueHorario24h, setBloqueHorario24h] = useState<'todos' | 'lunes_jueves' | 'viernes'>('todos')
  const [fechaInicio24h, setFechaInicio24h] = useState<string>(dateRange?.inicio || '2026-06-01')
  const [fechaFin24h, setFechaFin24h] = useState<string>(dateRange?.fin || '2026-06-30')

  useEffect(() => {
    if (dateRange?.inicio && dateRange?.fin && campana24hSeleccionada === -1) {
      setFechaInicio24h(dateRange.inicio)
      setFechaFin24h(dateRange.fin)
    }
  }, [dateRange?.inicio, dateRange?.fin, campana24hSeleccionada])

  // Campaña 24 Horas (Sección 8): Por defecto se focaliza en las campañas oficiales 24h
  const campanaEfectivaId = useMemo(() => {
    if (campana24hSeleccionada !== undefined) {
      return campana24hSeleccionada
    }
    const rIni = dateRange?.inicio?.slice(0, 10) || ''
    const rFin = dateRange?.fin?.slice(0, 10) || ''
    if (rIni >= '2026-11-01' && rFin <= '2026-11-30') return 9
    return 11
  }, [campana24hSeleccionada, dateRange?.inicio, dateRange?.fin])

  const esModoPersonalizado = campanaEfectivaId === -1
  const esCampanaFija = campanaEfectivaId >= 0

  const analisis24h = useQuery({
    queryKey: [
      'analisis24h',
      campanaEfectivaId,
      bloqueHorario24h,
      esModoPersonalizado ? fechaInicio24h : null,
      esModoPersonalizado ? fechaFin24h : null,
    ],
    queryFn: () =>
      fetchAnalisis24h({
        campanaId: esCampanaFija ? campanaEfectivaId : undefined,
        fechaInicio: esModoPersonalizado ? fechaInicio24h : undefined,
        fechaFin: esModoPersonalizado ? fechaFin24h : undefined,
        bloqueHorario: bloqueHorario24h,
      }),
  })

  const tieneCampana24hActiva = useMemo(() => {
    if (analisis24h.data?.campana?.tiene_campana_activa !== undefined) {
      return analisis24h.data.campana.tiene_campana_activa
    }
    const dInicio = dateRange?.inicio
    const dFin = dateRange?.fin
    if (!dInicio || !dFin) return false
    const campanas = analisis24h.data?.campanas_disponibles || []
    return campanas.some(c =>
      c.id > 0 &&
      c.fecha_inicio &&
      c.fecha_fin &&
      c.fecha_inicio <= dFin &&
      c.fecha_fin >= dInicio
    )
  }, [analisis24h.data?.campana?.tiene_campana_activa, analisis24h.data?.campanas_disponibles, dateRange?.inicio, dateRange?.fin])

  const handleDescargarPlantillaOficial = async () => {
    const filename = `Informe_Oficial_Salas_Estudio_Biblioteca_${new Date().toISOString().slice(0, 10)}.xlsx`
    setIsExportingPlantilla(true)
    try {
      await ejecutarDescarga({
        titulo: 'Plantilla Informe Oficial (Salas de Estudio)',
        subtitulo: 'Biblioteca CSF • Tablas maestras y gráficos nativos vinculados',
        tipo: 'excel',
        nombreArchivo: filename,
        tarea: async ({ setProgreso }) => {
          setProgreso(20, 'Consultando métricas de aforo, concurrencia y permanencia...')
          await new Promise(r => setTimeout(r, 400))
          setProgreso(55, 'Generando libro Excel OpenXML con 4 tablas y 5 gráficos oscuros...')
          const exito = await exportarPlantillaOficialSalasEstudio({
            espacio_id: 1,
            fecha_inicio: dateRange?.inicio,
            fecha_fin: dateRange?.fin,
            alcance: filters.alcance,
            regimen_horario: filters.regimen_horario,
            direccion: filters.direccion,
            dias_semana: filters.dias_semana,
            door: filters.door,
            carrera: filters.carrera,
            facultad: filters.facultad,
            periodo_label: dateRange?.label || 'Periodo Activo',
          })
          if (!exito) {
            throw new Error('No se pudo generar la plantilla oficial en el servidor.')
          }
          setProgreso(95, 'Finalizando ensamblado y descargando libro Excel...')
          await new Promise(r => setTimeout(r, 400))
        },
      })
    } finally {
      setIsExportingPlantilla(false)
    }
  }

  // Helpers para visibilidad de secciones combinados con la barra lateral (5 secciones unificadas)
  const showSec1 = esSeccionVisible('seccion_1') && (
    visibleCharts.aforo_curva !== false ||
    visibleCharts.prophet_diario !== false ||
    visibleCharts.distribucion_curricular !== false ||
    visibleCharts.perfiles_visita !== false ||
    visibleCharts.flujo_horario !== false ||
    visibleCharts.mapa_calor !== false
  )
  const showSec2 = esSeccionVisible('seccion_2') && (
    visibleCharts.comparativa_salas !== false ||
    visibleCharts.torniquetes !== false ||
    visibleCharts.distribucion_marcajes !== false
  )
  const showSec3 = esSeccionVisible('seccion_3') && (
    visibleCharts.volumen_mensual !== false ||
    visibleCharts.evolucion_semanal !== false ||
    visibleCharts.promedio_dias_semana !== false ||
    visibleCharts.hitos_academicos !== false
  )
  const showSec4 = esSeccionVisible('seccion_4')
  const showSec5 = esSeccionVisible('seccion_5')

  // Banner ejecutivo de Campaña 24 Horas
  const renderBannerCampana24Horas = (mostrarBotonSeccion5 = true) => (
    <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white p-5 rounded-2xl border border-indigo-800/50 shadow-md relative overflow-hidden">
      <div className="absolute top-0 right-0 -mr-12 -mt-12 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
      
      <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-indigo-800/40">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-indigo-600/30 text-indigo-300 border border-indigo-500/30">
            <Moon className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-white tracking-tight">
                Campaña 24 Horas & Análisis de Justificación Operativa
              </h3>
              <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-400/30">
                Sala 2 CSF04 Pecera (226 Asientos)
              </span>
            </div>
            <p className="text-xs text-indigo-200/80">
              Evaluación de demanda nocturna (L-J 23:00 a 07:00 h | Vie 22:00 a 06:00 h) durante régimen de exámenes
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() => {
              if (filters.regimen_horario === '24h_delta') {
                setFilters(prev => ({ ...prev, regimen_horario: 'todos' }))
              } else {
                setFilters(prev => ({ ...prev, regimen_horario: '24h_delta' }))
              }
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all shadow-xs cursor-pointer ${
              filters.regimen_horario === '24h_delta'
                ? 'bg-indigo-500 text-white ring-2 ring-indigo-300'
                : 'bg-white/10 hover:bg-white/20 text-indigo-100 border border-white/20'
            }`}
            title="Filtrar todas las métricas y gráficos del panel para mostrar únicamente accesos nocturnos"
          >
            <Layers className="w-3.5 h-3.5 text-indigo-300" />
            <span>
              {filters.regimen_horario === '24h_delta'
                ? 'Viendo: Solo Turno Nocturno (24h Delta)'
                : 'Filtrar por Turno Nocturno (Delta 24h)'}
            </span>
          </button>

          {mostrarBotonSeccion5 && (
            <button
              type="button"
              onClick={() => cambiarSeccionBiblioteca('seccion_5')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-white/10 hover:bg-white/20 text-white border border-white/20 transition-all cursor-pointer"
              title="Abrir la sección analítica completa dedicada a la Campaña 24 Horas"
            >
              <Moon className="w-3.5 h-3.5 text-indigo-300" />
              <span>Ver Sección 5 Completa</span>
            </button>
          )}

          <button
            type="button"
            onClick={() => setModalReporte24hAbierto(true)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-xs transition-all cursor-pointer border border-indigo-400/40"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-amber-300" />
            <span>Informe Justificativo Autoridades (Excel)</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-3">
        <div className="bg-white/5 border border-white/10 rounded-xl p-3">
          <div className="text-[11px] text-indigo-200/70">Aporte Nocturno (Delta 24h)</div>
          <div className="text-xl font-bold text-white mt-0.5">
            {analisis24h.data ? `${analisis24h.data.kpis_comparativa.porcentaje_delta_24h}%` : '...'}
          </div>
          <div className="text-[10px] text-indigo-300/80 mt-0.5">
            {analisis24h.data ? `${analisis24h.data.kpis_comparativa.ingresos_nocturnos.toLocaleString('es-CL')} de ${analisis24h.data.kpis_comparativa.total_ingresos.toLocaleString('es-CL')} accesos` : ''}
          </div>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-xl p-3">
          <div className="text-[11px] text-indigo-200/70">Concurrencia Máxima Simultánea</div>
          <div className="text-xl font-bold text-amber-300 mt-0.5">
            {analisis24h.data ? `${analisis24h.data.pico_nocturno.aforo_maximo} alumnos` : '...'}
          </div>
          <div className="text-[10px] text-indigo-300/80 mt-0.5">
            {analisis24h.data ? `${analisis24h.data.pico_nocturno.tasa_ocupacion_asientos_pct}% sobre 226 asientos (${analisis24h.data.pico_nocturno.hora_pico})` : ''}
          </div>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-xl p-3">
          <div className="text-[11px] text-indigo-200/70">Horas de Estudio Nocturnas</div>
          <div className="text-xl font-bold text-emerald-300 mt-0.5">
            {analisis24h.data ? `${analisis24h.data.kpis_comparativa.horas_estudio_nocturnas.toLocaleString('es-CL')} hrs` : '...'}
          </div>
          <div className="text-[10px] text-indigo-300/80 mt-0.5">
            {analisis24h.data ? `${analisis24h.data.kpis_comparativa.estudiantes_nocturnos_unicos.toLocaleString('es-CL')} estudiantes (est. 2 h / ingreso)` : ''}
          </div>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-xl p-3">
          <div className="text-[11px] text-indigo-200/70">Segmentación Curricular Clave</div>
          <div className="text-sm font-semibold text-indigo-100 truncate mt-1">
            {analisis24h.data?.top_carreras[0]?.carrera || 'Derecho'}
          </div>
          <div className="text-[10px] text-indigo-300/80 mt-0.5">
            {analisis24h.data?.top_carreras[0] ? `${analisis24h.data.top_carreras[0].porcentaje}% del uso nocturno` : ''}
          </div>
        </div>
      </div>
    </div>
  )

  return (
    <div className={`p-6 space-y-7 w-full max-w-full transition-all duration-200 ${barraLateralExpandida ? 'xl:pl-[284px]' : 'pl-0'}`}>
      <BarraLateralSecciones
        tituloModulo="Biblioteca CSF"
        secciones={SECCIONES_MODULO_BIBLIOTECA}
        seccionActiva={seccionActivaBiblioteca}
        alCambiarSeccion={cambiarSeccionBiblioteca}
        alAlternarApertura={setBarraLateralExpandida}
      />
      {puedeCompartirReportes && (
        <CompartirReporteModal
          abierto={modalCompartirAbierto}
          onCerrar={() => setModalCompartirAbierto(false)}
          espacioIdInicial={1}
          fechaInicioInicial={dateRange?.inicio || '2026-10-01'}
          fechaFinInicial={dateRange?.fin || '2026-10-30'}
          etiquetaPeriodoInicial={dateRange?.label}
          filtrosIniciales={filters}
          totalRegistrosInicial={kpis.data?.total_registros}
          tieneCampana24hActiva={tieneCampana24hActiva}
        />
      )}
      <ModalReporte24Horas
        isOpen={modalReporte24hAbierto}
        onClose={() => setModalReporte24hAbierto(false)}
        data={analisis24h.data ?? null}
        loading={analisis24h.isLoading}
        selectedCampanaId={campanaEfectivaId}
        onSelectCampana={(id) => setCampana24hSeleccionada(id)}
      />
      {/* Panel Gerencial de Métricas Clave (Desplazado con el contenido al abrir la barra lateral) */}
      <KPIBanner
        espacioId={1}
        selectedRange={dateRange}
        filters={filters}
      />

      {/* Barra de Alcance Analítico y Filtros Multidimensionales (Desplazamiento natural sin sticky) */}
      <div className="bg-white/95 backdrop-blur-md p-4 rounded-2xl border border-slate-200/90 shadow-xs transition-all">
        <ScopeSelector
          modulo="biblioteca"
          dateRange={dateRange}
          onRangeChange={onRangeChange}
          filters={filters}
          onChangeFilters={setFilters}
          totalCount={kpis.data?.total_registros}
          actionRight={
            <div className="flex flex-wrap items-center gap-2">
              {puedeCompartirReportes && (
                <button
                  type="button"
                  onClick={() => setModalCompartirAbierto(true)}
                  title="Crear enlace de reporte ejecutivo confinado para solicitante, gestionar vigencia, notas e historial"
                  className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-bold border bg-uct-blue-primary hover:bg-uct-blue-secondary text-white border-uct-blue-primary transition-all cursor-pointer shadow-2xs"
                >
                  <Share2 size={13} className="text-uct-gold" />
                  <span>Compartir Reporte Ejecutivo</span>
                </button>
              )}

              {/* Botón Plantilla Informe Oficial Salas de Estudio */}
              <button
                type="button"
                onClick={handleDescargarPlantillaOficial}
                disabled={isExportingPlantilla}
                title="Generar y descargar informe final en formato oficial idéntico a la plantilla institucional (4 tablas y 5 gráficos dinámicos oscuros)"
                className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-bold border transition-all cursor-pointer shadow-2xs ${
                  isExportingPlantilla
                    ? 'bg-amber-100/90 text-amber-900 border-amber-300 cursor-wait'
                    : 'bg-amber-500 hover:bg-amber-600 text-white border-amber-600 hover:shadow-xs'
                }`}
              >
                {isExportingPlantilla ? (
                  <>
                    <Loader2 size={13} className="animate-spin text-amber-900" />
                    <span>Generando Plantilla...</span>
                  </>
                ) : (
                  <>
                    <FileSpreadsheet size={13} className="text-white" />
                    <span>Plantilla Informe Oficial (Excel)</span>
                  </>
                )}
              </button>

              <ExcelBatchExportModal
                charts={BIBLIOTECA_CHARTS}
                dateRangeLabel={dateRange?.label ?? 'Período Completo'}
                moduloNombre="Biblioteca Campus San Francisco"
                activeFiltersDesc={{
                  'Alcance': String(filters.alcance || 'Todos'),
                  'Régimen Horario': String(filters.regimen_horario || 'Todos'),
                  'Carrera': String(filters.carrera || 'Todas'),
                  'Facultad': String(filters.facultad || 'Todas'),
                  'Sala': String(filters.sala || 'Ambas (CSF02 y CSF04)'),
                }}
              />
              <ChartVisibilitySelector
                charts={BIBLIOTECA_CHARTS}
                visibleCharts={visibleCharts}
                onToggleChart={toggleChart}
                onSelectAll={selectAllCharts}
                onDeselectAll={deselectAllCharts}
                moduloName="Biblioteca CSF"
              />
            </div>
          }
        />
      </div>

      {/* SECCIÓN 1: Aforo y Pronósticos IA (Resumen Ejecutivo) */}
      {seccionMontada('seccion_1') && (
        <div className={claseSeccion('seccion_1', 'space-y-4')}>
          {bibAlert && (
            <div className="flex items-center gap-3 p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-200">
              <AlertTriangle className="text-amber-400 shrink-0" size={20} />
              <div>
                <p className="text-sm font-semibold text-amber-300">Alerta Preventiva de Saturación (Prophet)</p>
                <p className="text-xs text-amber-200/80">{bibAlert.mensaje}</p>
              </div>
            </div>
          )}

          {/* Tarjeta Ejecutiva: Se muestra en Sección 1 SOLO si el rango de fecha coincide con régimen 24 Horas */}
          {tieneCampana24hActiva && renderBannerCampana24Horas(true)}

          {/* Tarjetas de Resumen Global (KPIs Principales del Dashboard) */}
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
            <KpiCard
              title="Afluencia Total"
              value={fmt(kpis.data?.total_registros)}
              subtitle={`${fmt(kpis.data?.usuarios_unicos)} estudiantes únicos`}
              icon={Users}
              iconColor="#003865"
            />
            <KpiCard
              title="Aforo Máximo Registrado"
              value={kpis.isLoading ? '…' : `${kpis.data?.max_aforo_historico ?? 0} personas`}
              subtitle={`Máximo vs ${capacidadActiva} asientos ${salaLabel ? `(${salaLabel})` : '(Global)'}`}
              icon={Activity}
              iconColor="#C59B27"
            />
            <KpiCard
              title="Estadía Promedio"
              value={`${fmt(visitProfiles.data?.items.find(i => i.perfil.includes('Estándar'))?.promedio_min ?? kpis.data?.permanencia_promedio_min, 0)} min`}
              subtitle="tiempo promedio de visita regular"
              icon={Clock}
              iconColor="#16A34A"
            />
            <KpiCard
              title="Tasa de Rebote"
              value={`${fmt(visitProfiles.data?.tasa_rebote_pct ?? kpis.data?.tasa_rebote_pct, 1)}%`}
              subtitle="visitas menores a 15 min"
              icon={TrendingDown}
              iconColor="#DC2626"
            />
          </div>

          {/* Barra de control y restablecimiento de diseño de gráficos */}
          <div className="flex flex-wrap items-center justify-between gap-3 bg-white px-4 py-2.5 rounded-xl border border-slate-200/90 shadow-2xs">
            <div className="flex items-center gap-2 text-xs text-slate-600 font-medium">
              <LayoutGrid size={15} className="text-uct-blue-primary" />
              <span>Diseño de gráficos dinámico:</span>
              <span className="hidden md:inline text-slate-400">Arrastre la esquina inferior de cualquier tarjeta para ajustar ancho y alto libremente</span>
            </div>
            <button
              type="button"
              onClick={handleResetAllCharts}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 hover:text-slate-900 border border-slate-200 transition cursor-pointer shadow-2xs"
              title="Restablecer todos los gráficos a sus dimensiones y orden por defecto"
            >
              <RotateCcw size={13} className="text-slate-500" />
              <span>Restablecer gráficos por defecto</span>
            </button>
          </div>

          <SectionHeader
            icon={Activity}
            title="1. Resumen y Demanda General"
            subtitle="Monitoreo concurrente en tiempo real, proyección Prophet 14 días, padrón curricular, permanencia y distribución horaria"
            badge="Reporte Institucional"
          />

          <div className="flex flex-wrap gap-4 items-start">
            {/* 1.1 Curva de Aforo Concurrente */}
            {visibleCharts.aforo_curva !== false && (
              <ChartCard
                contextoGrafico="aforo_curva"
                layout="full"
                title={salaLabel ? `Curva de Aforo Concurrente — ${salaLabel}` : "Curva de Aforo Concurrente vs Capacidad Máxima"}
                action={<LiveBadge lastUpdated={lastTs} />}
                minHeight={450}
                isFetching={flow.isFetching || roomsComp.isFetching}
              >
                <Suspense fallback={<ChartSkeleton />}>
                  {flow.data && flow.data.length > 0 ? (
                    <OccupancyAreaChart
                      data={flow.data}
                      capacidad={capacidadActiva}
                      salaLabel={salaLabel}
                      capSala1={capSala1}
                      capSala2={capSala2}
                      comparativaSalas={roomsComp.data?.flujo_horario_comparado}
                    />
                  ) : (
                    <EmptyState label="Sin datos de aforo para este período" />
                  )}
                </Suspense>
              </ChartCard>
            )}

            {/* 1.2 Pronóstico Prophet 14 Días */}
            {visibleCharts.prophet_diario !== false && (
              <ChartCard
                contextoGrafico="prophet_diario"
                layout="full"
                minHeight={460}
                isFetching={forecast.isFetching}
                title={`Pronóstico Continuo Prophet — 14 Días (7 Días Históricos Reales + 7 Días Proyectados) — ${salaPronostico === 'sala1'
                  ? 'Sala 1 (CSF02 2° Piso)'
                  : salaPronostico === 'sala2'
                    ? 'Sala 2 (CSF04 Pecera 1° Piso)'
                    : 'Todas las Salas (Campus San Francisco)'
                  }`}
                action={
                  <div className="flex items-center gap-2">
                    <div className="flex items-center bg-gray-100 dark:bg-gray-800 p-0.5 rounded-lg border border-gray-200 dark:border-gray-700 text-xs">
                      <button
                        type="button"
                        onClick={() => setSalaPronostico('todas')}
                        className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${salaPronostico === 'todas'
                          ? 'bg-white dark:bg-gray-700 text-uct-navy dark:text-white shadow-xs font-semibold'
                          : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                          }`}
                      >
                        Todas (426)
                      </button>
                      <button
                        type="button"
                        onClick={() => setSalaPronostico('sala1')}
                        className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${salaPronostico === 'sala1'
                          ? 'bg-white dark:bg-gray-700 text-uct-navy dark:text-white shadow-xs font-semibold'
                          : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                          }`}
                      >
                        Sala 1 (200)
                      </button>
                      <button
                        type="button"
                        onClick={() => setSalaPronostico('sala2')}
                        className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${salaPronostico === 'sala2'
                          ? 'bg-white dark:bg-gray-700 text-uct-navy dark:text-white shadow-xs font-semibold'
                          : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                          }`}
                      >
                        Sala 2 Pecera (226)
                      </button>
                    </div>

                    {forecast.data?.model_status.status === 'ok' ? (
                      <div className="hidden sm:flex items-center gap-1.5 text-[11px]">
                        <span className="text-slate-600 dark:text-slate-300 font-medium">
                          Proyección: <strong className="text-uct-navy dark:text-sky-300 font-semibold">{forecast.data.anchor_timestamp ? new Date(forecast.data.anchor_timestamp).toLocaleDateString('es-CL', { day: '2-digit', month: 'short' }) : 'Hoy'} (+7d)</strong>
                        </span>
                        <span className="text-gray-300 dark:text-gray-600">|</span>
                        <span className="text-uct-success font-medium">
                          Calibrado: {forecast.data.model_status.model_date}
                        </span>
                      </div>
                    ) : (
                      <span className="text-[11px] text-uct-warning hidden sm:inline">Modelo no entrenado</span>
                    )}
                  </div>
                }
              >
                <Suspense fallback={<ChartSkeleton />}>
                  {forecast.data?.forecast && forecast.data.forecast.length > 0 ? (
                    <ForecastLineChart
                      forecast={forecast.data.forecast}
                      historico7d={forecast.data.historico_7d}
                      pronostico7d={forecast.data.pronostico_7d}
                      capacidad={forecast.data.capacidad_asientos ?? capacidadActiva}
                      salaNombre={
                        salaPronostico === 'sala1'
                          ? 'Sala 1 CSF02'
                          : salaPronostico === 'sala2'
                            ? 'Sala 2 CSF04'
                            : 'Todas las Salas'
                      }
                      recinto="biblioteca"
                    />
                  ) : (
                    <EmptyState label={forecast.data?.model_status?.message ?? 'Sin pronóstico disponible'} />
                  )}
                </Suspense>
              </ChartCard>
            )}

            {/* 1.3 Padrón Académico y Distribución Curricular */}
            {visibleCharts.distribucion_curricular !== false && (
              <ChartCard
                contextoGrafico="distribucion_curricular"
                layout="full"
                title={`Población Académica y Distribución Curricular — ${dateRange?.label ?? 'Padrón Institucional'}`}
                isFetching={curricular.isFetching}
              >
                <Suspense fallback={<ChartSkeleton />}>
                  {curricular.data ? (
                    <CurricularDistributionPlotlyChart data={curricular.data} />
                  ) : (
                    <EmptyState label="Sin datos curriculares disponibles" />
                  )}
                </Suspense>
              </ChartCard>
            )}

            {/* 1.4 Perfiles de Visita y Tasa de Rebote */}
            {visibleCharts.perfiles_visita !== false && (
              <ChartCard
                contextoGrafico="perfiles_visita"
                layout="full"
                title="Perfiles de Visita y Tasa de Rebote (Cálculo Exacto Base de Datos)"
                isFetching={visitProfiles.isFetching}
              >
                <Suspense fallback={<ChartSkeleton />}>
                  {visitProfiles.data && visitProfiles.data.items && visitProfiles.data.items.length > 0 ? (
                    <VisitProfilesPlotlyChart data={visitProfiles.data} />
                  ) : (
                    <EmptyState label="Sin datos de perfiles de visita para los filtros aplicados" />
                  )}
                </Suspense>
              </ChartCard>
            )}

            {/* 1.5 Flujo Horario */}
            {visibleCharts.flujo_horario !== false && (
              <ChartCard contextoGrafico="flujo_horario" title={`Flujo Horario de Ingresos y Salidas — ${dateRange?.label ?? 'Período'}`} isFetching={flow.isFetching}>
                <Suspense fallback={<ChartSkeleton />}>
                  {flow.data && flow.data.length > 0 ? (
                    <HourlyBarChart data={flow.data} />
                  ) : (
                    <EmptyState label="Sin datos de flujo para este período" />
                  )}
                </Suspense>
              </ChartCard>
            )}

            {/* 1.6 Mapa de Calor */}
            {visibleCharts.mapa_calor !== false && (
              <ChartCard contextoGrafico="mapa_calor" title="Mapa de Calor — Ocupación por Día y Hora" isFetching={heatmap.isFetching}>
                <Suspense fallback={<ChartSkeleton />}>
                  {heatmap.data && heatmap.data.length > 0 ? (
                    <HeatmapChart data={heatmap.data} />
                  ) : (
                    <EmptyState label="Sin datos de heatmap" />
                  )}
                </Suspense>
              </ChartCard>
            )}
          </div>
        </div>
      )}

      {/* SECCIÓN 2: Puntos de Acceso Físico, Torniquetes y Comparativa de Salas */}
      {seccionMontada('seccion_2') && (
        <div className={claseSeccion('seccion_2', 'space-y-3.5')}>
          <SectionHeader
            icon={DoorClosed}
            title="2. Salas y Torniquetes"
            subtitle="Monitoreo de afluencia por sala (CSF02 2° Piso vs CSF04 Pecera 1° Piso) y distribución por torniquetes y accesos universales"
            badge="Hardware & Salas CSF"
          />

          <div className="flex flex-wrap gap-4 items-start">
            {visibleCharts.comparativa_salas !== false && (
              <ChartCard
                contextoGrafico="comparativa_salas"
                layout="full"
                title={
                  salaLabel
                    ? `Comparativa de Afluencia entre Salas — ${salaLabel} seleccionada (${dateRange?.label ?? 'Período'})`
                    : `Comparativa de Afluencia entre Salas (Sala 1 vs Sala 2) — ${dateRange?.label ?? 'Período'}`
                }
                isFetching={roomsComp.isFetching}
              >
                <Suspense fallback={<ChartSkeleton />}>
                  {roomsComp.data ? (
                    <RoomComparisonPlotlyChart data={roomsComp.data} />
                  ) : (
                    <EmptyState label="Sin datos de comparativa de salas" />
                  )}
                </Suspense>
              </ChartCard>
            )}

            {visibleCharts.torniquetes !== false && (
              <ChartCard contextoGrafico="torniquetes" title={`Uso de Torniquetes y Accesos Universales — ${dateRange?.label ?? 'Período'}`} isFetching={doors.isFetching}>
                <Suspense fallback={<ChartSkeleton />}>
                  {doors.data && doors.data.length > 0 ? (
                    <DoorUsagePlotlyChart data={doors.data} />
                  ) : (
                    <EmptyState label="Sin datos de torniquetes" />
                  )}
                </Suspense>
              </ChartCard>
            )}

            {visibleCharts.distribucion_marcajes !== false && (
              <ChartCard contextoGrafico="distribucion_marcajes" title={`Distribución de Marcajes por Registro — ${dateRange?.label ?? 'Período'}`} isFetching={checkins.isFetching}>
                <Suspense fallback={<ChartSkeleton />}>
                  {checkins.data && checkins.data.length > 0 ? (
                    <CheckinDistributionPlotlyChart data={checkins.data} />
                  ) : (
                    <EmptyState label="Sin datos de distribución" />
                  )}
                </Suspense>
              </ChartCard>
            )}
          </div>
        </div>
      )}

      {/* SECCIÓN 3: Tendencias Históricas y Calendario Académico */}
      {seccionMontada('seccion_3') && (
        <div className={claseSeccion('seccion_3', 'space-y-3.5')}>
          <SectionHeader
            icon={Calendar}
            title="3. Evolución e Hitos"
            subtitle="Evolución macro de la afluencia universitaria y contraste con hitos de clases, exámenes y recesos"
            badge="Evolución Institucional"
          />

          <div className="flex flex-wrap gap-4 items-start">
            {visibleCharts.promedio_dias_semana !== false && (
              <ChartCard
                contextoGrafico="promedio_dias_semana"
                layout="half"
                title={`Promedio Diario de Ingresos por Día de la Semana (Sala 1 vs Sala 2) — ${dateRange?.label ?? 'Período'}`}
                isFetching={dailyAvg.isFetching}
              >
                <Suspense fallback={<ChartSkeleton />}>
                  {dailyAvg.data ? (
                    <DailyAverageAttendancePlotlyChart data={dailyAvg.data} />
                  ) : (
                    <EmptyState label="Sin datos de promedio diario por día de semana" />
                  )}
                </Suspense>
              </ChartCard>
            )}

            {visibleCharts.hitos_academicos !== false && (
              <ChartCard contextoGrafico="hitos_academicos" layout="half" title="Comparativa por Hito Académico" isFetching={milestones.isFetching}>
                <Suspense fallback={<ChartSkeleton />}>
                  {milestones.data && milestones.data.length > 0 ? (
                    <AcademicMilestonesPlotlyChart data={milestones.data} />
                  ) : (
                    <EmptyState label="Sin datos de calendario" />
                  )}
                </Suspense>
              </ChartCard>
            )}

            {visibleCharts.volumen_mensual !== false && (
              <ChartCard contextoGrafico="volumen_mensual" layout="half" title="Volumen Mensual de Asistencia" isFetching={monthly.isFetching}>
                <Suspense fallback={<ChartSkeleton />}>
                  {monthly.data && monthly.data.length > 0 ? (
                    <MonthlyVolumePlotlyChart data={monthly.data} />
                  ) : (
                    <EmptyState label="Sin datos mensuales" />
                  )}
                </Suspense>
              </ChartCard>
            )}

            {visibleCharts.evolucion_semanal !== false && (
              <ChartCard contextoGrafico="evolucion_semanal" layout="half" title="Evolución Semanal de Usuarios" isFetching={weekly.isFetching}>
                <Suspense fallback={<ChartSkeleton />}>
                  {weekly.data && weekly.data.length > 0 ? (
                    <WeeklyEvolutionPlotlyChart data={weekly.data} />
                  ) : (
                    <EmptyState label="Sin datos semanales" />
                  )}
                </Suspense>
              </ChartCard>
            )}
          </div>
        </div>
      )}

      {/* SECCIÓN 4: Microdatos y Auditoría de Integridad en Crudo */}
      {seccionMontada('seccion_4') && (
        <div className={claseSeccion('seccion_4', 'space-y-3.5')}>
          <SectionHeader
            icon={Layers}
            title="4. Explorador de Microdatos"
            subtitle="Exploración a nivel de registro con seudonimización Ley 21.719, descalces de hardware y exportación oficial"
            badge="Ley 21.719"
          />

          <RawDataTable
            modulo="biblioteca"
            fechaInicio={dateRange?.inicio}
            fechaFin={dateRange?.fin}
            appliedFilters={filters}
            labelPeriodo={dateRange?.label}
          />
        </div>
      )}

      {/* SECCIÓN 5: Campaña 24 Horas Exámenes & Análisis de Flujo Nocturno */}
      {seccionMontada('seccion_5') && (
        <div id="seccion_5" className={claseSeccion('seccion_5', 'space-y-4 scroll-mt-6')}>
          {/* Banner Ejecutivo de la Campaña 24 Horas: Siempre visible en Sección 5 */}
          {renderBannerCampana24Horas(false)}

          <SectionHeader
            icon={Moon}
            title="5. Campaña 24 Horas Exámenes"
            subtitle="Monitoreo de demanda fuera de horario habitual (20:30 a 07:00 hrs) y justificación de capacidad en Sala 2 Pecera"
            badge="Régimen Continuo 24h"
          />

          <SeccionCampana24Horas
            data={analisis24h.data ?? null}
            isLoading={analisis24h.isLoading}
            selectedCampanaId={campanaEfectivaId}
            onSelectCampana={(id) => {
              setCampana24hSeleccionada(id)
              if (id === -1 && dateRange?.inicio && dateRange?.fin) {
                setFechaInicio24h(dateRange.inicio)
                setFechaFin24h(dateRange.fin)
              }
            }}
            fechaInicioPersonalizada={fechaInicio24h}
            fechaFinPersonalizada={fechaFin24h}
            onChangeFechaPersonalizada={(inicio: string, fin: string) => {
              setFechaInicio24h(inicio)
              setFechaFin24h(fin)
            }}
            bloqueHorario={bloqueHorario24h}
            onSelectBloqueHorario={setBloqueHorario24h}
            currentDateRange={dateRange}
            onApplyDateRange={(range: any) => onRangeChange?.(range)}
            onOpenReporteModal={() => setModalReporte24hAbierto(true)}
            isRegimenDeltaActive={filters.regimen_horario === '24h_delta'}
            onToggleRegimenDelta={() => {
              if (filters.regimen_horario === '24h_delta') {
                setFilters(prev => ({ ...prev, regimen_horario: 'todos' }))
              } else {
                setFilters(prev => ({ ...prev, regimen_horario: '24h_delta' }))
              }
            }}
          />
        </div>
      )}
    </div>
  )
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="h-full min-h-[220px] flex items-center justify-center text-uct-text-muted text-sm border border-dashed border-gray-200 dark:border-gray-800 rounded-xl p-6">
      {label}
    </div>
  )
}

export default BibliotecaView
