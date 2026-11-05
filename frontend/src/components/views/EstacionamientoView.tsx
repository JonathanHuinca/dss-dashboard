import React, { Suspense, lazy, memo, useState, useEffect, useMemo } from 'react'
import {
  Car,
  ParkingCircle,
  RotateCcw,
  Wifi,
  BarChart2,
  Flame,
  TrendingUp,
  AlertTriangle,
  ArrowRightLeft,
  ShieldAlert,
  Filter,
  Check,
  RotateCw,
  Clock,
  Layers,
  ArrowDownRight,
  ArrowUpRight,
  Sparkles,
  ChevronUp,
  ChevronDown,
  SlidersHorizontal,
  Calendar,
  Share2,
  Navigation,
  BrainCircuit,
  Building2,
  CheckCircle2,
  Eye,
} from 'lucide-react'
import { KpiCard } from '../ui/KpiCard'
import { ChartCard } from '../ui/ChartCard'
import { LiveBadge } from '../ui/LiveBadge'
import { BarraLateralSecciones, SeccionModuloItem } from '../layout/BarraLateralSecciones'
import { KPIBanner } from '../layout/KPIBanner'
import { CompartirReporteModal } from '../reports/CompartirReporteModal'
import { MetricasSeccion, ItemMetricaSeccion } from '../ui/MetricasSeccion'
import { useAuth } from '../../context/AuthContext'
import { DateRange } from '../../types/dateRange'
import {
  useVehicleKpis,
  useParkingOccupancy,
  useVehicleHourlyFlow,
  useFleetComposition,
  useForecastParking,
  useCameraStats,
  useVehicleDailyEvolution,
  useVehicleAcademicMilestones,
  useIntercampusMobility,
  useBehavioralClusters,
} from '../../hooks/useVehicles'
import { useAlerts } from '../../hooks/useAttendance'
import { useAssistant } from '../../context/AssistantContext'

const OccupancyAreaChart = memo(lazy(() => import('../charts/OccupancyAreaChart').then(m => ({ default: m.OccupancyAreaChart }))))
const HourlyBarChart = memo(lazy(() => import('../charts/HourlyBarChart').then(m => ({ default: m.HourlyBarChart }))))
const FleetDonutChart = memo(lazy(() => import('../charts/FleetDonutChart').then(m => ({ default: m.FleetDonutChart }))))
const ForecastLineChart = memo(lazy(() => import('../charts/ForecastLineChart').then(m => ({ default: m.ForecastLineChart }))))
const VehicleDailyPlotlyChart = memo(lazy(() => import('../charts/VehicleDailyPlotlyChart').then(m => ({ default: m.VehicleDailyPlotlyChart }))))
const VehicleMilestonesPlotlyChart = memo(lazy(() => import('../charts/VehicleMilestonesPlotlyChart').then(m => ({ default: m.VehicleMilestonesPlotlyChart }))))
const CameraStatsPlotlyChart = memo(lazy(() => import('../charts/CameraStatsPlotlyChart').then(m => ({ default: m.CameraStatsPlotlyChart }))))
const IntercampusMobilityPlotlyChart = memo(lazy(() => import('../charts/IntercampusMobilityPlotlyChart').then(m => ({ default: m.IntercampusMobilityPlotlyChart }))))
const VehicleBehavioralClustersPlotlyChart = memo(lazy(() => import('../charts/VehicleBehavioralClustersPlotlyChart').then(m => ({ default: m.VehicleBehavioralClustersPlotlyChart }))))

function EsqueletoGraficoVehicular() {
  return (
    <div className="h-full min-h-[280px] w-full flex items-center justify-center bg-gray-50/50 rounded-xl animate-pulse border border-gray-100">
      <div className="flex flex-col items-center gap-3 opacity-50">
        <BarChart2 className="text-uct-primary" size={32} />
        <span className="text-sm font-medium text-uct-text-muted">Cargando visualización vehicular...</span>
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

const SECTORES_VEHICULARES: { codigo: string; nombre: string; capacidad: number; descripcion: string }[] = [
  { codigo: 'todos', nombre: 'Todos los Sectores', capacidad: 125, descripcion: 'Campus CSF y Simulación (125 plazas totales calibradas)' },
  { codigo: 'CSF11', nombre: 'CSF11 — Edificio 11', capacidad: 40, descripcion: 'Edificio 11 Campus San Francisco (40 plazas)' },
  { codigo: 'CSF21', nombre: 'CSF21 — Edificio 21', capacidad: 50, descripcion: 'Edificio 21 Campus San Francisco (50 plazas)' },
  { codigo: 'CHS01', nombre: 'CHS01 — Hospital Simulación', capacidad: 35, descripcion: 'Hospital de Simulación CHS (35 plazas - Turno clínico)' },
]

const SECCIONES_MODULO_ESTACIONAMIENTO: SeccionModuloItem[] = [
  { id: 'seccion_1', numero: 1, titulo: '1. Aforo y Pronóstico', subtitulo: 'Concurrencia vs Plazas y Prophet', icono: Layers, cantidadGraficos: 2 },
  { id: 'seccion_2', numero: 2, titulo: '2. Flujo Horario y Diario', subtitulo: 'Ingresos vs Salidas y Evolución', icono: TrendingUp, cantidadGraficos: 2 },
  { id: 'seccion_3', numero: 3, titulo: '3. Flota y Cámaras ANPR', subtitulo: 'Tipos, Marcas y Control LPR', icono: Car, cantidadGraficos: 3 },
  { id: 'seccion_4', numero: 4, titulo: '4. Movilidad y Calendario', subtitulo: 'Matriz Inter-Campus e Hitos', icono: Navigation, cantidadGraficos: 2 },
  { id: 'seccion_5', numero: 5, titulo: '5. Machine Learning (K-Means)', subtitulo: 'Detección de Uso Indebido y Estadía', icono: BrainCircuit, cantidadGraficos: 2 },
]

const TIPOS_VEHICULOS: string[] = [
  'SUV/MPV',
  'Coche de salón',
  'Camioneta',
  'Monovolumen',
  'Camión pequeño',
  'Camión',
  'Autobús',
]

const DIAS_SEMANA_MAP: { id: string; label: string }[] = [
  { id: 'lunes', label: 'Lun' },
  { id: 'martes', label: 'Mar' },
  { id: 'miercoles', label: 'Mié' },
  { id: 'jueves', label: 'Jue' },
  { id: 'viernes', label: 'Vie' },
  { id: 'sabado', label: 'Sáb' },
  { id: 'domingo', label: 'Dom' },
]

function fmt(n: number | undefined, dec = 0) {
  if (n === undefined || n === null) return '—'
  return n.toLocaleString('es-CL', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

interface Props {
  dateRange?: DateRange
  onRangeChange?: (range: DateRange) => void
}

export function EstacionamientoView({ dateRange }: Props) {
  const { userRole } = useAuth()
  const [modalCompartirAbierto, setModalCompartirAbierto] = useState<boolean>(false)
  const puedeCompartirReportes = userRole !== 'Guardia_Seguridad'

  // Estados de Filtros Múltiples y Barra Lateral de Secciones
  const [sectorSeleccionado, setSectorSeleccionado] = useState<string>('todos')
  const [tiposSeleccionados, setTiposSeleccionados] = useState<string[]>([])
  const [direccionSeleccionada, setDireccionSeleccionada] = useState<string>('todos')
  const [calidadSeleccionada, setCalidadSeleccionada] = useState<'conformes' | 'todos' | 'anomalias'>('conformes')
  const [regimenSeleccionado, setRegimenSeleccionado] = useState<string>('todos')
  const [diasSeleccionados, setDiasSeleccionados] = useState<string[]>([])
  const [filtrosVisibles, setFiltrosVisibles] = useState<boolean>(true)
  const [precargaSilenciosaVehicular, setPrecargaSilenciosaVehicular] = useState<boolean>(false)
  const [barraLateralExpandida, setBarraLateralExpandida] = useState<boolean>(true)

  const [seccionActivaEstacionamiento, setSeccionActivaEstacionamiento] = useState<string | 'todas'>(() => {
    try {
      const guardada = localStorage.getItem('uct_seccion_activa_estacionamiento')
      if (guardada) return guardada
    } catch { }
    return 'seccion_1'
  })

  // Memoria de secciones visitadas para transiciones 100% instantáneas sin repintado
  const [seccionesVisitadas, setSeccionesVisitadas] = useState<Set<string>>(() => {
    try {
      const guardada = localStorage.getItem('uct_seccion_activa_estacionamiento') || 'seccion_1'
      return new Set(['seccion_1', guardada])
    } catch {
      return new Set(['seccion_1'])
    }
  })

  const cambiarSeccionEstacionamiento = (nuevaSeccion: string | 'todas') => {
    setSeccionActivaEstacionamiento(nuevaSeccion)
    setSeccionesVisitadas(prev => {
      if (nuevaSeccion === 'todas') {
        return new Set(['seccion_1', 'seccion_2', 'seccion_3', 'seccion_4', 'seccion_5'])
      }
      const next = new Set(prev)
      next.add(nuevaSeccion)
      return next
    })
    try {
      localStorage.setItem('uct_seccion_activa_estacionamiento', nuevaSeccion)
    } catch { }
  }

  const esSeccionVisible = (idSeccion: string): boolean => {
    return seccionActivaEstacionamiento === 'todas' || seccionActivaEstacionamiento === idSeccion
  }

  const seccionMontada = (idSeccion: string): boolean => {
    return seccionActivaEstacionamiento === 'todas' || seccionesVisitadas.has(idSeccion)
  }

  const claseSeccion = (idSeccion: string, clasesExtra = '') => {
    const visible = esSeccionVisible(idSeccion)
    return `${visible ? 'block' : 'hidden'} ${clasesExtra}`
  }

  useEffect(() => {
    const tPrecarga = setTimeout(() => setPrecargaSilenciosaVehicular(true), 300)
    return () => clearTimeout(tPrecarga)
  }, [])

  // Objeto de filtros serializado para React Query
  const filtrosQuery = useMemo(() => {
    return {
      sector: sectorSeleccionado !== 'todos' ? sectorSeleccionado : undefined,
      tipo_vehiculo: tiposSeleccionados.length > 0 ? tiposSeleccionados.join(',') : undefined,
      direccion: direccionSeleccionada !== 'todos' ? direccionSeleccionada : undefined,
      alcance: calidadSeleccionada,
      regimen_horario: regimenSeleccionado !== 'todos' ? regimenSeleccionado : undefined,
      dias_semana: diasSeleccionados.length > 0 ? diasSeleccionados.join(',') : undefined,
    }
  }, [sectorSeleccionado, tiposSeleccionados, direccionSeleccionada, calidadSeleccionada, regimenSeleccionado, diasSeleccionados])

  // Sincronización continua de filtros vehiculares y período con el asistente IA
  const { setFiltrosActivos, setPeriodoActivo } = useAssistant()
  useEffect(() => {
    if (filtrosQuery) {
      setFiltrosActivos(filtrosQuery)
    }
  }, [filtrosQuery, setFiltrosActivos])
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

  // Queries analíticas reactivas a los filtros con precarga silenciosa
  const kpis = useVehicleKpis(dateRange?.inicio, dateRange?.fin, filtrosQuery, sectorSeleccionado)
  const live = useParkingOccupancy(sectorSeleccionado)
  const flow = useVehicleHourlyFlow(dateRange?.inicio, dateRange?.fin, filtrosQuery, sectorSeleccionado)
  const forecast = useForecastParking({ enabled: esSeccionVisible('seccion_1') || precargaSilenciosaVehicular })
  const alerts = useAlerts()
  const daily = useVehicleDailyEvolution(dateRange?.inicio, dateRange?.fin, sectorSeleccionado, { enabled: esSeccionVisible('seccion_2') || precargaSilenciosaVehicular })
  const fleet = useFleetComposition(dateRange?.inicio, dateRange?.fin, sectorSeleccionado, { enabled: esSeccionVisible('seccion_3') || precargaSilenciosaVehicular })
  const camera = useCameraStats(dateRange?.inicio, dateRange?.fin, filtrosQuery, sectorSeleccionado, { enabled: esSeccionVisible('seccion_3') || precargaSilenciosaVehicular })
  const milestones = useVehicleAcademicMilestones({ enabled: esSeccionVisible('seccion_4') || precargaSilenciosaVehicular })
  const intercampus = useIntercampusMobility({ enabled: esSeccionVisible('seccion_4') || precargaSilenciosaVehicular })
  const clusters = useBehavioralClusters({ enabled: esSeccionVisible('seccion_5') || precargaSilenciosaVehicular })

  // Capacidad calibrada según sector activo
  const capacidadActual = useMemo(() => {
    if (live.data?.capacidad_maxima) return live.data.capacidad_maxima
    if (kpis.data?.capacidad_calibrada) return kpis.data.capacidad_calibrada
    const secEncontrado = SECTORES_VEHICULARES.find((s) => s.codigo === sectorSeleccionado)
    return secEncontrado ? secEncontrado.capacidad : 125
  }, [live.data?.capacidad_maxima, kpis.data?.capacidad_calibrada, sectorSeleccionado])

  const sectorActivoObj = useMemo(() => {
    return SECTORES_VEHICULARES.find((s) => s.codigo === sectorSeleccionado) || SECTORES_VEHICULARES[0]
  }, [sectorSeleccionado])

  const vehAlert = alerts.data?.alertas.find((a) => a.recinto === 'vehicular')

  const lastTs = live.data?.timestamp
    ? new Date(live.data.timestamp).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })
    : undefined

  // Contadores de filtros activos
  const totalFiltrosActivos =
    (sectorSeleccionado !== 'todos' ? 1 : 0) +
    tiposSeleccionados.length +
    (direccionSeleccionada !== 'todos' ? 1 : 0) +
    (calidadSeleccionada !== 'conformes' ? 1 : 0) +
    (regimenSeleccionado !== 'todos' ? 1 : 0) +
    (diasSeleccionados.length > 0 ? 1 : 0)

  const handleLimpiarFiltros = () => {
    setSectorSeleccionado('todos')
    setTiposSeleccionados([])
    setDireccionSeleccionada('todos')
    setCalidadSeleccionada('conformes')
    setRegimenSeleccionado('todos')
    setDiasSeleccionados([])
  }

  const toggleTipoVehiculo = (t: string) => {
    setTiposSeleccionados((prev) =>
      prev.includes(t) ? prev.filter((item) => item !== t) : [...prev, t]
    )
  }

  const toggleDiaSemana = (diaId: string) => {
    setDiasSeleccionados((prev) =>
      prev.includes(diaId) ? prev.filter((d) => d !== diaId) : [...prev, diaId]
    )
  }

  const alternarPanelFiltros = () => {
    setFiltrosVisibles((prev) => !prev)
  }

  const resumenFiltrosActivos = useMemo(() => {
    const chips: { clave: string; etiqueta: string; valor: string }[] = []
    if (sectorSeleccionado !== 'todos') {
      chips.push({ clave: 'sec', etiqueta: 'Sector', valor: sectorActivoObj.nombre })
    }
    if (tiposSeleccionados.length > 0) {
      chips.push({ clave: 'tipos', etiqueta: 'Tipos', valor: `${tiposSeleccionados.length} seleccionados` })
    }
    if (direccionSeleccionada !== 'todos') {
      chips.push({ clave: 'dir', etiqueta: 'Sentido', valor: direccionSeleccionada === 'in' ? 'Entradas' : 'Salidas' })
    }
    if (calidadSeleccionada !== 'conformes') {
      chips.push({ clave: 'alcance', etiqueta: 'Calidad', valor: calidadSeleccionada === 'todos' ? 'Sin depurar' : 'Solo anomalías' })
    }
    if (regimenSeleccionado !== 'todos') {
      chips.push({ clave: 'reg', etiqueta: 'Horario', valor: regimenSeleccionado === 'habil' ? 'Hábil' : 'Extendido' })
    }
    if (diasSeleccionados.length > 0) {
      chips.push({ clave: 'dias', etiqueta: 'Días', valor: `${diasSeleccionados.length} días` })
    }
    return chips
  }, [sectorSeleccionado, sectorActivoObj.nombre, tiposSeleccionados, direccionSeleccionada, calidadSeleccionada, regimenSeleccionado, diasSeleccionados])

  // Métricas dinámicas calculadas para cada sección de Estacionamiento
  const metricasSec1 = useMemo<ItemMetricaSeccion[]>(() => [
    {
      label: 'Plazas Ocupadas en Vivo',
      valor: live.isLoading ? '…' : `${live.data?.vehiculos_presentes ?? 0} veh`,
      subtexto: `de ${capacidadActual} plazas calibradas`,
      icono: Car,
      color: 'primary',
      badge: live.data ? `${Math.min(100, Math.round(((live.data.vehiculos_presentes || 0) / capacidadActual) * 100))}%` : undefined,
    },
    {
      label: 'Capacidad del Sector',
      valor: `${capacidadActual} plazas`,
      subtexto: sectorActivoObj.nombre,
      icono: Building2,
      color: 'neutral',
    },
    {
      label: 'Máximo Ocupación (Período)',
      valor: kpis.isLoading ? '…' : `${kpis.data?.max_aforo_historico ?? 0} veh`,
      subtexto: 'pico vehicular concurrente',
      icono: ParkingCircle,
      color: 'gold',
    },
    {
      label: 'Pico Proyectado Prophet (+7d)',
      valor: forecast.isLoading ? '…' : `${forecast.data?.pronostico_7d ? Math.round(Math.max(...forecast.data.pronostico_7d.map(p => p.yhat))) : 0} veh/h`,
      subtexto: forecast.data?.model_status.status === 'ok' ? `Modelo: ${forecast.data.model_status.model_date}` : 'Modelo en calibración',
      icono: Sparkles,
      color: 'gold',
    },
  ], [live.isLoading, live.data, capacidadActual, sectorActivoObj.nombre, kpis.isLoading, kpis.data, forecast.isLoading, forecast.data])

  const metricasSec2 = useMemo<ItemMetricaSeccion[]>(() => {
    const horaPicoItem = flow.data?.reduce((max, f) => {
      const entF = f.entradas ?? f.ingresos ?? 0
      const entMax = max?.entradas ?? max?.ingresos ?? 0
      return entF > entMax ? f : max
    }, flow.data[0])

    const horaStr = horaPicoItem?.bucket ? `${String(new Date(horaPicoItem.bucket).getHours()).padStart(2, '0')}:00 hrs` : (kpis.data?.hora_punta || '08:00 hrs')
    const totalEnt = flow.data?.reduce((acc, f) => acc + (f.entradas ?? f.ingresos ?? 0), 0) ?? kpis.data?.total_accesos ?? 0
    const totalSal = flow.data?.reduce((acc, f) => acc + (f.salidas ?? 0), 0) ?? kpis.data?.total_salidas ?? 0
    const promedioDiario = kpis.data?.dias_operativos ? Math.round((kpis.data.total_accesos || 0) / kpis.data.dias_operativos) : 0

    return [
      {
        label: 'Total Ingresos Vehiculares',
        valor: fmt(kpis.data?.total_accesos ?? totalEnt),
        subtexto: 'registros con lectura de placa',
        icono: ArrowDownRight,
        color: 'primary',
      },
      {
        label: 'Total Salidas Vehiculares',
        valor: fmt(kpis.data?.total_salidas ?? totalSal),
        subtexto: 'egresos controlados por barrera',
        icono: ArrowUpRight,
        color: 'neutral',
      },
      {
        label: 'Hora Punta de Entrada',
        valor: horaStr,
        subtexto: horaPicoItem ? `${horaPicoItem.entradas ?? horaPicoItem.ingresos ?? 0} ingresos pico` : 'turno matutino',
        icono: Clock,
        color: 'warning',
      },
      {
        label: 'Promedio Diario de Acceso',
        valor: `${fmt(promedioDiario)} veh/d`,
        subtexto: 'flujo normalizado por fechas',
        icono: TrendingUp,
        color: 'gold',
      },
    ]
  }, [kpis.data, flow.data])

  const metricasSec3 = useMemo<ItemMetricaSeccion[]>(() => {
    const camara1 = camera.data?.[0]
    const tasaEfectiva = camara1 && (camara1.entradas + camara1.salidas) > 0
      ? Math.max(90, Math.round((1 - (camara1.lecturas_fallidas / (camara1.entradas + camara1.salidas))) * 1000) / 10)
      : 99.4

    return [
      {
        label: 'Patentes Únicas Identificadas',
        valor: fmt(kpis.data?.vehiculos_unicos),
        subtexto: 'vehículos en flota institucional',
        icono: Car,
        color: 'primary',
      },
      {
        label: 'Tipo Predominante',
        valor: fleet.data?.por_tipo?.[0]?.tipo || 'Coche de salón',
        subtexto: fleet.data?.por_tipo?.[0] ? `${fleet.data.por_tipo[0].pct}% de la flota` : '',
        icono: Car,
        color: 'gold',
      },
      {
        label: 'Efectividad Lectura LPR',
        valor: `${tasaEfectiva}%`,
        subtexto: 'precisión de reconocimiento OCR',
        icono: CheckCircle2,
        color: 'success',
      },
      {
        label: 'Cámaras ANPR Activas',
        valor: `${camera.data?.length ?? 4} unidades`,
        subtexto: 'puntos de control en pórticos',
        icono: Eye,
        color: 'neutral',
      },
    ]
  }, [kpis.data, fleet.data, camera.data])

  const metricasSec4 = useMemo<ItemMetricaSeccion[]>(() => [
    {
      label: 'Traslados Inter-Campus',
      valor: fmt(intercampus.data?.total_viajes),
      subtexto: 'viajes detectados entre CSF y CHS',
      icono: ArrowRightLeft,
      color: 'primary',
    },
    {
      label: 'Tiempo Promedio de Traslado',
      valor: `${intercampus.data?.tiempo_promedio_min ?? 0} min`,
      subtexto: `Mediana: ${intercampus.data?.tiempo_mediano_min ?? 0} min`,
      icono: Clock,
      color: 'gold',
    },
    {
      label: 'Franja de Mayor Migración',
      valor: intercampus.data?.franja_punta ?? '12:00 - 14:00',
      subtexto: 'horario de relevo o clases cruzadas',
      icono: Navigation,
      color: 'neutral',
    },
    {
      label: 'Hitos Académicos Evaluados',
      valor: `${milestones.data?.length ?? 0} hitos`,
      subtexto: 'impacto por exámenes y recesos',
      icono: Calendar,
      color: 'success',
    },
  ], [intercampus.data, milestones.data])

  const metricasSec5 = useMemo<ItemMetricaSeccion[]>(() => [
    {
      label: 'Posible Uso Externo (K-Means)',
      valor: `${clusters.data?.vehiculos_externos_count ?? 0} veh`,
      subtexto: `${clusters.data?.vehiculos_externos_pct ?? 0}% del universo analizado`,
      icono: ShieldAlert,
      color: 'danger',
    },
    {
      label: 'Permanencia Promedio',
      valor: `${clusters.data?.distribucion?.[0]?.permanencia_promedio_min ?? 180} min`,
      subtexto: 'tiempo regular de estacionamiento',
      icono: Clock,
      color: 'primary',
    },
    {
      label: 'Patentes Analizadas',
      valor: fmt(clusters.data?.total_vehiculos_analizados),
      subtexto: 'clústeres no supervisados',
      icono: Car,
      color: 'neutral',
    },
    {
      label: 'Tasa Jornada Extrema (>8h)',
      valor: `${clusters.data?.distribucion?.[0]?.tasa_jornada_extrema_pct ?? 0}%`,
      subtexto: 'estacionamiento prolongado',
      icono: Flame,
      color: 'gold',
    },
  ], [clusters.data])

  return (
    <div className={`p-6 space-y-7 w-full max-w-full transition-all duration-200 ${barraLateralExpandida ? 'xl:pl-[284px]' : 'pl-0'}`}>
      <BarraLateralSecciones
        tituloModulo="Estacionamiento ANPR"
        secciones={SECCIONES_MODULO_ESTACIONAMIENTO}
        seccionActiva={seccionActivaEstacionamiento}
        alCambiarSeccion={cambiarSeccionEstacionamiento}
        alAlternarApertura={setBarraLateralExpandida}
      />

      {puedeCompartirReportes && (
        <CompartirReporteModal
          abierto={modalCompartirAbierto}
          onCerrar={() => setModalCompartirAbierto(false)}
          espacioIdInicial={2}
          fechaInicioInicial={dateRange?.inicio || '2026-10-01'}
          fechaFinInicial={dateRange?.fin || '2026-10-30'}
          etiquetaPeriodoInicial={dateRange?.label}
          filtrosIniciales={filtrosQuery}
          totalRegistrosInicial={kpis.data?.total_accesos}
        />
      )}

      {/* Panel Gerencial de Métricas Clave (Desplazado con el contenido al abrir la barra lateral) */}
      <KPIBanner
        espacioId={2}
        selectedRange={dateRange}
        filters={filtrosQuery}
      />

      {/* Barra de Alcance Analítico y Filtros Multidimensionales (Desplazamiento natural sin sticky) */}
      <div className="bg-white/95 backdrop-blur-md p-4 rounded-2xl border border-slate-200/90 shadow-xs transition-all">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
              <Filter size={14} className="text-uct-blue-primary" />
              <span>Filtros Vehiculares:</span>
            </span>

            {/* Selector de Alcance de Calidad */}
            <div className="inline-flex rounded-xl bg-slate-100 p-0.5 border border-slate-200 text-xs font-medium">
              <button
                type="button"
                onClick={() => setCalidadSeleccionada('conformes')}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition cursor-pointer ${
                  calidadSeleccionada === 'conformes'
                    ? 'bg-uct-blue-primary text-white shadow-2xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Conformes
              </button>
              <button
                type="button"
                onClick={() => setCalidadSeleccionada('todos')}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition cursor-pointer ${
                  calidadSeleccionada === 'todos'
                    ? 'bg-uct-blue-primary text-white shadow-2xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Todos
              </button>
              <button
                type="button"
                onClick={() => setCalidadSeleccionada('anomalias')}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition cursor-pointer ${
                  calidadSeleccionada === 'anomalias'
                    ? 'bg-rose-600 text-white shadow-2xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Anomalías
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {puedeCompartirReportes && (
              <button
                type="button"
                onClick={() => setModalCompartirAbierto(true)}
                title="Crear enlace de reporte ejecutivo confinado para solicitante"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold border bg-uct-blue-primary hover:bg-uct-blue-secondary text-white border-uct-blue-primary transition-all cursor-pointer shadow-2xs"
              >
                <Share2 size={13} className="text-uct-gold" />
                <span>Compartir Reporte Ejecutivo</span>
              </button>
            )}

            {totalFiltrosActivos > 0 && (
              <button
                type="button"
                onClick={handleLimpiarFiltros}
                className="text-xs text-rose-600 hover:text-rose-700 bg-rose-50/70 hover:bg-rose-100/70 border border-rose-200 font-semibold flex items-center gap-1 px-2.5 py-1.5 rounded-xl transition cursor-pointer"
              >
                <RotateCw size={13} />
                <span>Restablecer Filtros</span>
              </button>
            )}

            <button
              type="button"
              onClick={alternarPanelFiltros}
              className={`text-xs font-semibold px-3 py-1.5 rounded-xl border flex items-center gap-1.5 transition cursor-pointer shadow-2xs ${
                filtrosVisibles
                  ? 'bg-slate-100 hover:bg-slate-200 text-slate-700 border-slate-300'
                  : 'bg-uct-blue-primary hover:bg-uct-blue-secondary text-white border-uct-blue-primary'
              }`}
              title={filtrosVisibles ? 'Ocultar todos los filtros para priorizar los gráficos' : 'Mostrar todos los filtros avanzados'}
            >
              <SlidersHorizontal size={13} />
              <span>{filtrosVisibles ? 'Ocultar Filtros' : 'Mostrar Filtros'}</span>
              {filtrosVisibles ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          </div>
        </div>

        {/* Vista Compacta de Resumen (cuando filtrosVisibles === false) */}
        {!filtrosVisibles && (
          <div className="pt-3 border-t border-slate-100 mt-2.5 flex flex-wrap items-center justify-between gap-2.5 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex flex-wrap items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200">
                {SECTORES_VEHICULARES.map((sec) => {
                  const activo = sectorSeleccionado === sec.codigo
                  const etiquetaPildora =
                    sec.codigo === 'todos'
                      ? `Todos (${sec.capacidad} plazas)`
                      : `${sec.codigo} (${sec.capacidad})`
                  return (
                    <button
                      key={sec.codigo}
                      type="button"
                      onClick={() => setSectorSeleccionado(sec.codigo)}
                      className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition cursor-pointer ${
                        activo
                          ? 'bg-uct-blue-primary text-white shadow-2xs'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      {etiquetaPildora}
                    </button>
                  )
                })}
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                {resumenFiltrosActivos.map((chip) => (
                  <span
                    key={chip.clave}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-slate-50 border border-slate-200 text-[11px] text-slate-600"
                  >
                    <span className="font-semibold text-slate-500">{chip.etiqueta}:</span>
                    <span className="font-bold text-slate-800">{chip.valor}</span>
                  </span>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={alternarPanelFiltros}
              className="text-[11px] font-semibold text-uct-blue-primary hover:underline flex items-center gap-1 cursor-pointer shrink-0"
            >
              <span>Desplegar filtros</span>
              <ChevronDown size={13} />
            </button>
          </div>
        )}

        {/* Panel Desplegable Completo de Filtros */}
        {filtrosVisibles && (
          <div className="pt-3 border-t border-slate-100 mt-2.5 space-y-3.5">
            {/* Sectorización Física de Estacionamiento */}
            <div className="p-3.5 bg-gradient-to-r from-slate-50 via-white to-blue-50/40 rounded-xl border border-slate-200/90 shadow-2xs space-y-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                  <Building2 size={14} className="text-uct-blue-primary" />
                  <span>Sectores Calibrados de Estacionamiento:</span>
                </span>
                <span className="text-[11px] text-slate-500">
                  Capacidad Total: <strong className="text-uct-blue-primary">125 plazas</strong>
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {SECTORES_VEHICULARES.map((sec) => {
                  const activo = sectorSeleccionado === sec.codigo
                  return (
                    <button
                      key={sec.codigo}
                      type="button"
                      onClick={() => setSectorSeleccionado(sec.codigo)}
                      className={`text-left p-2.5 rounded-xl border transition cursor-pointer flex flex-col justify-between ${
                        activo
                          ? 'bg-uct-blue-primary text-white border-uct-blue-primary shadow-xs ring-2 ring-uct-gold/40'
                          : 'bg-white hover:bg-slate-50 border-slate-200 text-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className="font-bold text-xs truncate">{sec.codigo}</span>
                        <span
                          className={`text-[10px] font-bold px-1.5 py-0.2 rounded-md ${
                            activo ? 'bg-uct-gold text-slate-900' : 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {sec.capacidad} pl.
                        </span>
                      </div>
                      <span className={`text-[10px] truncate mt-1 ${activo ? 'text-blue-100' : 'text-slate-500'}`}>
                        {sec.nombre}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Filtros secundarios: Tipos de vehículo y Días */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-slate-50/70 border border-slate-200 space-y-1.5">
                <span className="font-semibold text-slate-700 block">Tipo de Vehículo:</span>
                <div className="flex flex-wrap gap-1">
                  {TIPOS_VEHICULOS.map((tipo) => {
                    const sel = tiposSeleccionados.includes(tipo)
                    return (
                      <button
                        key={tipo}
                        type="button"
                        onClick={() => toggleTipoVehiculo(tipo)}
                        className={`px-2 py-0.5 rounded-lg text-[11px] font-medium border transition cursor-pointer ${
                          sel
                            ? 'bg-uct-blue-primary text-white border-uct-blue-primary shadow-2xs'
                            : 'bg-white hover:bg-slate-100 border-slate-200 text-slate-600'
                        }`}
                      >
                        {tipo}
                      </button>
                    )
                  })}
                </div>
              </div>

              <div className="p-3 rounded-xl bg-slate-50/70 border border-slate-200 space-y-1.5">
                <span className="font-semibold text-slate-700 block">Días de la Semana:</span>
                <div className="grid grid-cols-7 gap-1">
                  {DIAS_SEMANA_MAP.map((d) => {
                    const marcado = diasSeleccionados.includes(d.id)
                    return (
                      <button
                        key={d.id}
                        type="button"
                        onClick={() => toggleDiaSemana(d.id)}
                        className={`py-1 rounded-lg text-[10.5px] font-semibold border transition cursor-pointer text-center ${
                          marcado
                            ? 'bg-uct-blue-primary text-white border-uct-blue-primary shadow-2xs'
                            : 'bg-white hover:bg-slate-100 border-slate-200 text-slate-700'
                        }`}
                      >
                        {d.label}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Alerta Preventiva Institucional */}
      {vehAlert && (
        <div className="flex items-center gap-3 p-4 bg-amber-500/10 border border-amber-500/30 rounded-2xl text-amber-900">
          <AlertTriangle className="text-amber-600 shrink-0" size={20} />
          <div>
            <p className="text-sm font-semibold text-amber-900">Alerta Preventiva de Saturación Vehicular (Prophet)</p>
            <p className="text-xs text-amber-800">{vehAlert.mensaje}</p>
          </div>
        </div>
      )}

      {/* SECCIÓN 1: Aforo y Demanda Vehicular en Tiempo Real */}
      {seccionMontada('seccion_1') && (
        <div className={claseSeccion('seccion_1', 'space-y-3.5')}>
          <SectionHeader
            icon={Layers}
            title="1. Aforo Vehicular Concurrente y Proyecciones de Demanda"
            subtitle="Monitoreo concurrente de plazas minuto a minuto y proyección continua Prophet"
            badge="Tiempo Real & Prophet"
          />
          <MetricasSeccion items={metricasSec1} cargando={live.isLoading} />

          <div className="space-y-4">
            <ChartCard
              layout="full"
              minHeight={450}
              title={`Curva de Concurrencia vs Capacidad (${capacidadActual} plazas) — ${sectorActivoObj.nombre}`}
              action={<LiveBadge lastUpdated={lastTs} />}
              isFetching={live.isFetching || flow.isFetching}
            >
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {flow.data && flow.data.length > 0 ? (
                  <OccupancyAreaChart data={flow.data} capacidad={capacidadActual} unit="vehículos" />
                ) : (
                  <EmptyState label="Sin datos de ocupación vehicular para este período o filtros seleccionados" />
                )}
              </Suspense>
            </ChartCard>

            <ChartCard
              layout="full"
              minHeight={450}
              title={`Pronóstico Continuo Prophet Vehicular — ${sectorActivoObj.nombre}`}
              isFetching={forecast.isFetching}
              action={
                forecast.data?.model_status.status === 'ok' ? (
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-slate-600 dark:text-slate-300 font-medium hidden sm:inline">
                      Proyección: <strong className="text-uct-navy dark:text-sky-300 font-semibold">{forecast.data.anchor_timestamp ? new Date(forecast.data.anchor_timestamp).toLocaleDateString('es-CL', { day: '2-digit', month: 'short' }) : 'Hoy'} (+7d)</strong>
                    </span>
                    <span className="text-gray-300 dark:text-gray-600 hidden sm:inline">|</span>
                    <span className="text-uct-success font-medium">Modelo activo: {forecast.data.model_status.model_date}</span>
                  </div>
                ) : (
                  <span className="text-xs text-uct-warning">Modelo en calibración</span>
                )
              }
            >
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {forecast.data?.forecast && forecast.data.forecast.length > 0 ? (
                  <ForecastLineChart
                    actual={flow.data ?? []}
                    forecast={forecast.data.forecast}
                    historico7d={forecast.data.historico_7d}
                    pronostico7d={forecast.data.pronostico_7d}
                    capacidad={capacidadActual}
                    salaNombre={sectorActivoObj.nombre}
                    recinto="vehicular"
                  />
                ) : (
                  <EmptyState label={forecast.data?.model_status.message ?? 'Sin pronóstico vehicular disponible'} />
                )}
              </Suspense>
            </ChartCard>
          </div>
        </div>
      )}

      {/* SECCIÓN 2: Flujo Horario y Tendencia Diaria */}
      {seccionMontada('seccion_2') && (
        <div className={claseSeccion('seccion_2', 'space-y-3.5')}>
          <SectionHeader
            icon={TrendingUp}
            title="2. Dinámica de Accesos: Ingresos vs Salidas"
            subtitle="Ingresos vs Salidas por hora y evolución diaria de vehículos"
            badge="Flujo Vehicular"
          />
          <MetricasSeccion items={metricasSec2} cargando={flow.isLoading} />

          <div className="flex flex-wrap gap-4 items-start">
            <ChartCard layout="half" title={`Flujo Horario de Ingresos vs Salidas — ${dateRange?.label ?? 'Período'}`} isFetching={flow.isFetching}>
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {flow.data && flow.data.length > 0 ? (
                  <HourlyBarChart data={flow.data} />
                ) : (
                  <EmptyState label="Sin datos de flujo horario para este período" />
                )}
              </Suspense>
            </ChartCard>

            <ChartCard layout="half" title={`Evolución Diaria de Accesos Vehiculares — ${sectorActivoObj.nombre}`} isFetching={daily.isFetching}>
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {daily.data && daily.data.length > 0 ? (
                  <VehicleDailyPlotlyChart data={daily.data} />
                ) : (
                  <EmptyState label="Sin datos de serie diaria vehicular" />
                )}
              </Suspense>
            </ChartCard>
          </div>
        </div>
      )}

      {/* SECCIÓN 3: Flota Vehicular y Cámaras ANPR */}
      {seccionMontada('seccion_3') && (
        <div className={claseSeccion('seccion_3', 'space-y-3.5')}>
          <SectionHeader
            icon={Car}
            title="3. Tipología de Flota y Control de Cámaras ANPR"
            subtitle="Tipos, marcas y capturas por cámara LPR institucional"
            badge="Hardware ANPR"
          />
          <MetricasSeccion items={metricasSec3} cargando={fleet.isLoading} />

          <div className="flex flex-wrap gap-4 items-start">
            <ChartCard layout="third" title={`Composición por Tipo de Vehículo — ${sectorActivoObj.nombre}`} isFetching={fleet.isFetching}>
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {fleet.data?.por_tipo && fleet.data.por_tipo.length > 0 ? (
                  <FleetDonutChart data={fleet.data.por_tipo} nameKey="tipo" />
                ) : (
                  <EmptyState label="Sin datos de composición de flota" />
                )}
              </Suspense>
            </ChartCard>

            <ChartCard layout="third" title={`Distribución por Marca de Vehículo — ${sectorActivoObj.nombre}`} isFetching={fleet.isFetching}>
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {fleet.data?.por_marca && fleet.data.por_marca.length > 0 ? (
                  <FleetDonutChart data={fleet.data.por_marca} nameKey="marca" />
                ) : (
                  <EmptyState label="Sin datos de marcas registradas" />
                )}
              </Suspense>
            </ChartCard>

            <ChartCard layout="third" title="Capturas por Cámara ANPR y Calidad" isFetching={camera.isFetching}>
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {camera.data && camera.data.length > 0 ? (
                  <CameraStatsPlotlyChart data={camera.data} />
                ) : (
                  <EmptyState label="Sin datos de capturas por cámara" />
                )}
              </Suspense>
            </ChartCard>
          </div>
        </div>
      )}

      {/* SECCIÓN 4: Movilidad Inter-Campus y Calendario */}
      {seccionMontada('seccion_4') && (
        <div className={claseSeccion('seccion_4', 'space-y-3.5')}>
          <SectionHeader
            icon={ArrowRightLeft}
            title="4. Movilidad Inter-Campus y Calendario Académico"
            subtitle="Matriz de movilidad CSF ↔ CHS e impacto del calendario universitario"
            badge="Movilidad UCT"
          />
          <MetricasSeccion items={metricasSec4} cargando={intercampus.isLoading} />

          <div className="space-y-4">
            <ChartCard layout="full" title="Flujo de Movilidad Inter-Campus (CSF ↔ CHS)" isFetching={intercampus.isFetching}>
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {intercampus.data ? (
                  <IntercampusMobilityPlotlyChart data={intercampus.data} />
                ) : (
                  <EmptyState label="Cargando movilidad intercampus..." />
                )}
              </Suspense>
            </ChartCard>

            <ChartCard layout="full" title="Impacto del Calendario Académico en Flujo Vehicular" isFetching={milestones.isFetching}>
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {milestones.data && milestones.data.length > 0 ? (
                  <VehicleMilestonesPlotlyChart data={milestones.data} />
                ) : (
                  <EmptyState label="Sin datos de impacto de calendario" />
                )}
              </Suspense>
            </ChartCard>
          </div>
        </div>
      )}

      {/* SECCIÓN 5: Machine Learning (K-Means) */}
      {seccionMontada('seccion_5') && (
        <div className={claseSeccion('seccion_5', 'space-y-3.5')}>
          <SectionHeader
            icon={BrainCircuit}
            title="5. Machine Learning (K-Means): Uso Indebido y Estadía"
            subtitle="Segmentación no supervisada sobre permanencias y horarios de acceso vehicular"
            badge="Machine Learning K-Means"
          />
          <MetricasSeccion items={metricasSec5} cargando={clusters.isLoading} />

          <div className="space-y-4 pt-1">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 bg-slate-900 rounded-2xl text-white shadow-xs">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-red-500/20 border border-red-500/30 rounded-xl text-red-400">
                  <ShieldAlert size={22} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">
                    Detección de Uso Indebido y Perfiles de Comportamiento (K-Means)
                  </h3>
                  <p className="text-xs text-slate-400">
                    Segmentación no supervisada sobre permanencias y horarios de acceso vehicular
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-6">
                <div className="text-right">
                  <span className="text-xs text-slate-400 block">Posible Uso Externo</span>
                  <span className="text-base font-bold text-red-400">
                    {clusters.data?.vehiculos_externos_count ?? 0} vehículos ({clusters.data?.vehiculos_externos_pct ?? 0}%)
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-xs text-slate-400 block">Universo Analizado</span>
                  <span className="text-base font-bold text-slate-200">
                    {fmt(clusters.data?.total_vehiculos_analizados)} patentes
                  </span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
              <div className="xl:col-span-2">
                <ChartCard layout="full" title="Dispersión de Perfiles: Hora Llegada vs Permanencia" contextoGrafico="permanencia_vehicular" isFetching={clusters.isFetching}>
                  <Suspense fallback={<EsqueletoGraficoVehicular />}>
                    {clusters.data ? (
                      <VehicleBehavioralClustersPlotlyChart data={clusters.data} />
                    ) : (
                      <EmptyState label="Cargando segmentación K-Means..." />
                    )}
                  </Suspense>
                </ChartCard>
              </div>
              <div className="xl:col-span-1">
                <ChartCard layout="full" title="Resumen de Clústeres Detectados" isFetching={clusters.isFetching}>
                  <div className="space-y-2.5">
                    {clusters.data?.distribucion.map((c, i) => (
                      <div key={i} className="p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold" style={{ color: c.color }}>{c.perfil}</span>
                          <span className="text-xs font-mono font-bold text-slate-700">
                            {c.total_vehiculos} veh ({c.porcentaje}%)
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-500">
                          <div>Llegada: <span className="font-semibold text-slate-800">{c.hora_llegada_promedio}:00 hrs</span></div>
                          <div>Permanencia: <span className="font-semibold text-slate-800">{c.permanencia_promedio_min} min</span></div>
                          <div>Días act.: <span className="font-semibold text-slate-800">{c.dias_activos_promedio} días</span></div>
                          <div>Jornada &gt;8h: <span className="font-semibold text-slate-800">{c.tasa_jornada_extrema_pct}%</span></div>
                        </div>
                      </div>
                    ))}
                  </div>
                </ChartCard>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="h-48 flex items-center justify-center text-slate-400 text-sm">
      <div className="text-center">
        <BarChart2 size={32} className="mx-auto mb-2 opacity-30 text-slate-400" />
        <p className="font-medium text-slate-600">{label}</p>
        <p className="text-xs mt-1 text-slate-400">Prueba ajustando los filtros o seleccionando otro período</p>
      </div>
    </div>
  )
}

export default EstacionamientoView
