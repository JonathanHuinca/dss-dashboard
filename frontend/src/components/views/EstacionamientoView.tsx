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
} from 'lucide-react'
import { KpiCard } from '../ui/KpiCard'
import { ChartCard } from '../ui/ChartCard'
import { LiveBadge } from '../ui/LiveBadge'
import { BarraLateralSecciones, SeccionModuloItem } from '../layout/BarraLateralSecciones'
import { CompartirReporteModal } from '../reports/CompartirReporteModal'
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
        <span className="text-sm font-medium text-uct-text-muted">Cargando visualización...</span>
      </div>
    </div>
  )
}

const SECTORES_VEHICULARES = [
  { codigo: 'todos', nombre: 'Todos los Sectores', capacidad: 125, descripcion: 'Campus CSF y Simulación (125 plazas totales calibradas)' },
  { codigo: 'CSF11', nombre: 'CSF11 — Edificio 11', capacidad: 40, descripcion: 'Edificio 11 Campus San Francisco (40 plazas)' },
  { codigo: 'CSF21', nombre: 'CSF21 — Edificio 21', capacidad: 50, descripcion: 'Edificio 21 Campus San Francisco (50 plazas)' },
  { codigo: 'CHS01', nombre: 'CHS01 — Hospital Simulación', capacidad: 35, descripcion: 'Hospital de Simulación CHS (35 plazas - Turno clínico)' },
]

const SECCIONES_MODULO_ESTACIONAMIENTO: SeccionModuloItem[] = [
  { id: 'seccion_1', numero: 1, titulo: '1. Aforo y Pronóstico', subtitulo: 'Concurrencia vs Capacidad y Prophet', icono: Layers, cantidadGraficos: 2 },
  { id: 'seccion_2', numero: 2, titulo: '2. Flujo Horario y Diario', subtitulo: 'Ingresos vs Salidas y Evolución', icono: TrendingUp, cantidadGraficos: 2 },
  { id: 'seccion_3', numero: 3, titulo: '3. Flota y Cámaras ANPR', subtitulo: 'Tipos, Marcas y Capturas por Cámara', icono: Car, cantidadGraficos: 3 },
  { id: 'seccion_4', numero: 4, titulo: '4. Movilidad y Clústeres IA', subtitulo: 'Inter-Campus, Calendario y K-Means', icono: ArrowRightLeft, cantidadGraficos: 3 },
]

const TIPOS_VEHICULO = [
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

  const cambiarSeccionEstacionamiento = (nuevaSeccion: string | 'todas') => {
    setSeccionActivaEstacionamiento(nuevaSeccion)
    try {
      localStorage.setItem('uct_seccion_activa_estacionamiento', nuevaSeccion)
    } catch { }
  }

  const esSeccionVisible = (idSeccion: string): boolean => {
    return seccionActivaEstacionamiento === 'todas' || seccionActivaEstacionamiento === idSeccion
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
  const clusters = useBehavioralClusters({ enabled: esSeccionVisible('seccion_4') || precargaSilenciosaVehicular })

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

    const textoFlujo =
      direccionSeleccionada === 'entrada'
        ? 'Solo Ingresos'
        : direccionSeleccionada === 'salida'
        ? 'Solo Salidas'
        : 'Ingresos y Salidas'
    chips.push({ clave: 'flujo', etiqueta: 'Flujo', valor: textoFlujo })

    const textoCalidad =
      calidadSeleccionada === 'conformes'
        ? 'Placas Reconocidas'
        : calidadSeleccionada === 'anomalias'
        ? 'Solo Unknown'
        : 'Todas las Capturas'
    chips.push({ clave: 'calidad', etiqueta: 'Calidad ANPR', valor: textoCalidad })

    const textoRegimen =
      regimenSeleccionado === 'dentro_horario'
        ? 'Operativo (07–22h)'
        : regimenSeleccionado === 'fuera_horario'
        ? 'Nocturno'
        : 'Todos los Horarios'
    chips.push({ clave: 'regimen', etiqueta: 'Régimen', valor: textoRegimen })

    const textoDias =
      diasSeleccionados.length === 0
        ? 'Lun–Dom'
        : diasSeleccionados.length === 5 && !diasSeleccionados.includes('sabado') && !diasSeleccionados.includes('domingo')
        ? 'Lun–Vie'
        : diasSeleccionados.length === 2 && diasSeleccionados.includes('sabado') && diasSeleccionados.includes('domingo')
        ? 'Fin de semana'
        : `${diasSeleccionados.length} días`
    chips.push({ clave: 'dias', etiqueta: 'Días', valor: textoDias })

    const textoTipos =
      tiposSeleccionados.length === 0 ? 'Todos' : `${tiposSeleccionados.length} sel.`
    chips.push({ clave: 'tipos', etiqueta: 'Vehículos', valor: textoTipos })

    return chips
  }, [direccionSeleccionada, calidadSeleccionada, regimenSeleccionado, diasSeleccionados, tiposSeleccionados])

  return (
    <div className={`p-6 space-y-6 w-full max-w-full transition-all duration-200 ${barraLateralExpandida ? 'xl:pl-[276px]' : ''}`}>
      <BarraLateralSecciones
        tituloModulo="Estacionamiento CSF"
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
      {/* Panel Superior: Filtros Múltiples del Módulo de Estacionamiento */}
      <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-4 sm:p-5 space-y-3.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-uct-blue-primary/10 flex items-center justify-center text-uct-blue-primary shrink-0">
              <ParkingCircle size={20} />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-bold text-slate-800">
                  Panel de Filtros y Control ANPR — Estacionamiento Campus San Francisco
                </h2>
                {totalFiltrosActivos > 0 && (
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-uct-blue-primary">
                    {totalFiltrosActivos} filtro{totalFiltrosActivos > 1 ? 's' : ''} activo{totalFiltrosActivos > 1 ? 's' : ''}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-500">
                Aforos y analítica calibrada para los 3 accesos vehiculares ANPR institucionales
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {puedeCompartirReportes && (
              <button
                type="button"
                onClick={() => setModalCompartirAbierto(true)}
                title="Crear enlace de reporte ejecutivo confinado para solicitante, gestionar vigencia, notas e historial"
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-bold border bg-uct-blue-primary hover:bg-uct-blue-secondary text-white border-uct-blue-primary transition-all cursor-pointer shadow-2xs"
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
                  ? 'bg-slate-100 hover:bg-slate-200/80 text-slate-700 border-slate-300'
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
          <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2.5 text-xs">
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
                      title={sec.descripcion}
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

        {/* Cuerpo Desplegable Completo (cuando filtrosVisibles === true) */}
        {filtrosVisibles && (
          <div className="pt-3 border-t border-slate-100 space-y-3.5">
            {/* Bloque Superior: Sectores de Estacionamiento y Tipo de Vehículo */}
            <div className="p-3.5 bg-gradient-to-r from-slate-50 via-white to-blue-50/40 rounded-2xl border border-slate-200/90 space-y-3.5">
              {/* 1. Selector de Sector Vehicular */}
              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-600">
                    Sector de Estacionamiento Institucional
                  </span>
                  <span className="text-[10.5px] text-slate-500 font-medium">
                    Capacidad calibrada total: <strong className="text-uct-blue-primary">125 plazas</strong>
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
                  {SECTORES_VEHICULARES.map((sec) => {
                    const activo = sectorSeleccionado === sec.codigo
                    const porcentajePlazas = Math.min(100, Math.round((sec.capacidad / 125) * 100))
                    return (
                      <button
                        key={sec.codigo}
                        type="button"
                        onClick={() => setSectorSeleccionado(sec.codigo)}
                        className={`p-3 rounded-xl border text-left transition flex flex-col justify-between gap-2 cursor-pointer ${
                          activo
                            ? 'bg-uct-blue-primary text-white border-uct-blue-primary shadow-sm'
                            : 'bg-white hover:bg-slate-50 border-slate-200/90 text-slate-700 shadow-2xs'
                        }`}
                        title={sec.descripcion}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-bold truncate">{sec.nombre}</span>
                          {activo ? (
                            <Check size={15} className="text-white shrink-0" />
                          ) : (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-50 text-uct-blue-primary font-semibold shrink-0">
                              {sec.capacidad} plazas
                            </span>
                          )}
                        </div>
                        <div className="space-y-1">
                          <div className={`text-[10.5px] flex items-center justify-between ${activo ? 'text-blue-100' : 'text-slate-500'}`}>
                            <span>Capacidad: <b>{sec.capacidad} plazas</b></span>
                            <span className="font-mono text-[10px]">{porcentajePlazas}%</span>
                          </div>
                          <div className={`w-full h-1.5 rounded-full overflow-hidden ${activo ? 'bg-white/20' : 'bg-slate-100'}`}>
                            <div
                              className={`h-full rounded-full ${activo ? 'bg-uct-gold-accent' : 'bg-uct-blue-primary/80'}`}
                              style={{ width: `${porcentajePlazas}%` }}
                            />
                          </div>
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* 2. Tipo de Vehículo */}
              <div className="pt-2.5 border-t border-slate-200/80">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-1.5">
                    <Car size={14} className="text-uct-blue-primary" />
                    <span className="text-[11px] font-bold uppercase tracking-wider text-slate-600">
                      Tipo de Vehículo Registrado
                    </span>
                    <span className="text-[10px] text-slate-400 font-medium">
                      ({tiposSeleccionados.length === 0 ? 'Todos activos' : `${tiposSeleccionados.length} seleccionados`})
                    </span>
                  </div>
                  {tiposSeleccionados.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setTiposSeleccionados([])}
                      className="text-[10px] text-uct-blue-primary hover:underline font-semibold cursor-pointer"
                    >
                      Marcar todos los tipos
                    </button>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {TIPOS_VEHICULO.map((t) => {
                    const marcado = tiposSeleccionados.includes(t)
                    return (
                      <button
                        key={t}
                        type="button"
                        onClick={() => toggleTipoVehiculo(t)}
                        className={`px-3 py-1 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                          marcado
                            ? 'bg-uct-blue-primary text-white border-uct-blue-primary shadow-2xs'
                            : 'bg-white hover:bg-slate-100 border-slate-200 text-slate-700'
                        }`}
                      >
                        {t}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>

            {/* Bloque Inferior: Grilla de 4 Tarjetas Operativas (Flujo, Calidad ANPR, Régimen Horario y Días Operativos) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {/* Tarjeta 1: Flujo de Movimiento */}
              <div className="bg-slate-50/80 p-3 rounded-xl border border-slate-200/80 flex flex-col justify-between gap-2">
                <div className="flex items-center gap-1.5 text-slate-700">
                  <ArrowRightLeft size={14} className="text-uct-blue-primary shrink-0" />
                  <label className="text-[11px] font-bold uppercase tracking-wider text-slate-600">
                    Flujo de Movimiento
                  </label>
                </div>
                <select
                  value={direccionSeleccionada}
                  onChange={(e) => setDireccionSeleccionada(e.target.value)}
                  className="w-full px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 focus:outline-none focus:border-uct-blue-primary cursor-pointer"
                >
                  <option value="todos">Todos (Ingresos y Salidas)</option>
                  <option value="entrada">Solo Ingresos (Entradas)</option>
                  <option value="salida">Solo Salidas</option>
                </select>
              </div>

              {/* Tarjeta 2: Calidad de Detección ANPR */}
              <div className="bg-slate-50/80 p-3 rounded-xl border border-slate-200/80 flex flex-col justify-between gap-2">
                <div className="flex items-center gap-1.5 text-slate-700">
                  <Wifi size={14} className="text-uct-blue-primary shrink-0" />
                  <label className="text-[11px] font-bold uppercase tracking-wider text-slate-600">
                    Calidad de Detección ANPR
                  </label>
                </div>
                <select
                  value={calidadSeleccionada}
                  onChange={(e) => setCalidadSeleccionada(e.target.value as 'conformes' | 'todos' | 'anomalias')}
                  className="w-full px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 focus:outline-none focus:border-uct-blue-primary cursor-pointer"
                >
                  <option value="conformes">Lecturas Conformes (Placas Reconocidas)</option>
                  <option value="todos">Todas las Capturas (Incluye Unknown)</option>
                  <option value="anomalias">Solo Fallas de Lectura (Unknown)</option>
                </select>
              </div>

              {/* Tarjeta 3: Régimen Horario */}
              <div className="bg-slate-50/80 p-3 rounded-xl border border-slate-200/80 flex flex-col justify-between gap-2">
                <div className="flex items-center gap-1.5 text-slate-700">
                  <Clock size={14} className="text-uct-blue-primary shrink-0" />
                  <label className="text-[11px] font-bold uppercase tracking-wider text-slate-600">
                    Régimen Horario
                  </label>
                </div>
                <select
                  value={regimenSeleccionado}
                  onChange={(e) => setRegimenSeleccionado(e.target.value)}
                  className="w-full px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 focus:outline-none focus:border-uct-blue-primary cursor-pointer"
                >
                  <option value="todos">Todos los Horarios</option>
                  <option value="dentro_horario">Dentro de Horario Operativo (07:00 - 22:00)</option>
                  <option value="fuera_horario">Fuera de Horario / Nocturno</option>
                </select>
              </div>

              {/* Tarjeta 4: Días Operativos de la Semana */}
              <div className="bg-slate-50/80 p-3 rounded-xl border border-slate-200/80 flex flex-col justify-between gap-2">
                <div className="flex items-center justify-between gap-1">
                  <div className="flex items-center gap-1.5 text-slate-700">
                    <Calendar size={14} className="text-uct-blue-primary shrink-0" />
                    <span className="text-[11px] font-bold uppercase tracking-wider text-slate-600">
                      Días Operativos
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px]">
                    <button
                      type="button"
                      onClick={() => setDiasSeleccionados(['lunes', 'martes', 'miercoles', 'jueves', 'viernes'])}
                      className="text-uct-blue-primary hover:underline font-semibold cursor-pointer"
                      title="Lunes a Viernes"
                    >
                      Lunes a Viernes
                    </button>
                    <span className="text-slate-300">|</span>
                    <button
                      type="button"
                      onClick={() => setDiasSeleccionados(['sabado', 'domingo'])}
                      className="text-uct-blue-primary hover:underline font-semibold cursor-pointer"
                      title="Fin de semana"
                    >
                      Fin de semana
                    </button>
                    <span className="text-slate-300">|</span>
                    <button
                      type="button"
                      onClick={() => setDiasSeleccionados([])}
                      className="text-slate-500 hover:underline font-medium cursor-pointer"
                    >
                      Todos
                    </button>
                  </div>
                </div>
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

      {/* Bloque Principal de Métricas Contextuales de Estacionamiento */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
        <KpiCard
          title="Vehículos Dentro"
          value={live.isLoading ? '…' : `${live.data?.vehiculos_presentes ?? 0} / ${capacidadActual}`}
          subtitle={`${live.data?.ocupacion_pct ?? 0}% ocupación`}
          icon={Car}
          iconColor="#C59B27"
          alert={live.data?.nivel_alerta}
        />
        <KpiCard
          title="Plazas Libres"
          value={live.data?.plazas_disponibles ?? '—'}
          subtitle={`de ${capacidadActual} plazas calibradas`}
          icon={ParkingCircle}
          iconColor="#16A34A"
        />
        <KpiCard
          title="Total Ingresos"
          value={fmt(kpis.data?.total_accesos)}
          subtitle="entradas vehiculares registradas"
          icon={ArrowDownRight}
          iconColor="#0284C7"
        />
        <KpiCard
          title="Total Salidas"
          value={fmt(kpis.data?.total_salidas)}
          subtitle="salidas ANPR validadas"
          icon={ArrowUpRight}
          iconColor="#D97706"
        />
        <KpiCard
          title="Rotación Diaria"
          value={`${fmt(kpis.data?.turnover_rate_diario, 2)}x`}
          subtitle="vehículos / plaza / día"
          icon={RotateCcw}
          iconColor="#003865"
        />
        <KpiCard
          title="Permanencia Mediana"
          value={`${fmt(kpis.data?.permanencia_mediana_min, 0)} min`}
          subtitle="estadía media por vehículo"
          icon={Clock}
          iconColor="#8B5CF6"
        />
      </div>

      {/* SECCIÓN 1: Aforo en Tiempo Real y Pronóstico Predictivo */}
      {esSeccionVisible('seccion_1') && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-700">
            <Layers size={15} className="text-uct-blue-primary" />
            <span>1. Aforo Vehicular Concurrente y Proyecciones de Demanda</span>
          </div>

          <div className="space-y-4">
            <ChartCard
              layout="full"
              minHeight={450}
              title={`Curva de Concurrencia vs Capacidad (${capacidadActual} plazas) — ${sectorActivoObj.nombre}`}
              action={<LiveBadge lastUpdated={lastTs} />}
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
              action={
                forecast.data?.model_status.status === 'ok' ? (
                  <span className="text-xs text-uct-success font-medium">Modelo activo: {forecast.data.model_status.model_date}</span>
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

      {/* SECCIÓN 2: Dinámica de Ingresos vs Salidas por Horario */}
      {esSeccionVisible('seccion_2') && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-700">
            <TrendingUp size={15} className="text-uct-blue-primary" />
            <span>2. Dinámica de Accesos: Ingresos vs Salidas</span>
          </div>

          <div className="flex flex-wrap gap-4 items-start">
            <ChartCard layout="half" title={`Flujo Horario de Ingresos vs Salidas — ${dateRange?.label ?? 'Período'}`}>
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {flow.data && flow.data.length > 0 ? (
                  <HourlyBarChart data={flow.data} />
                ) : (
                  <EmptyState label="Sin datos de flujo horario para este período" />
                )}
              </Suspense>
            </ChartCard>

            <ChartCard layout="half" title={`Evolución Diaria de Accesos Vehiculares — ${sectorActivoObj.nombre}`}>
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

      {/* SECCIÓN 3: Inteligencia de Flota y Calidad de Capturas ANPR */}
      {esSeccionVisible('seccion_3') && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-700">
            <Car size={15} className="text-uct-blue-primary" />
            <span>3. Tipología de Flota y Control de Cámaras ANPR</span>
          </div>

          <div className="flex flex-wrap gap-4 items-start">
            <ChartCard layout="third" title={`Composición por Tipo de Vehículo — ${sectorActivoObj.nombre}`}>
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {fleet.data?.por_tipo && fleet.data.por_tipo.length > 0 ? (
                  <FleetDonutChart data={fleet.data.por_tipo} nameKey="tipo" />
                ) : (
                  <EmptyState label="Sin datos de composición de flota" />
                )}
              </Suspense>
            </ChartCard>

            <ChartCard layout="third" title={`Distribución por Marca de Vehículo — ${sectorActivoObj.nombre}`}>
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {fleet.data?.por_marca && fleet.data.por_marca.length > 0 ? (
                  <FleetDonutChart data={fleet.data.por_marca} nameKey="marca" />
                ) : (
                  <EmptyState label="Sin datos de marcas registradas" />
                )}
              </Suspense>
            </ChartCard>

            <ChartCard layout="third" title="Capturas por Cámara ANPR y Calidad">
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {camera.data && camera.data.length > 0 ? (
                  <CameraStatsPlotlyChart data={camera.data} />
                ) : (
                  <EmptyState label="Sin datos de cámaras para este período" />
                )}
              </Suspense>
            </ChartCard>
          </div>
        </div>
      )}

      {/* SECCIÓN 4: Movilidad Institucional y Segmentación Machine Learning */}
      {esSeccionVisible('seccion_4') && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-700">
            <ArrowRightLeft size={15} className="text-uct-blue-primary" />
            <span>4. Movilidad Inter-Campus y Segmentación de Comportamiento</span>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <div className="xl:col-span-1 space-y-3.5">
              <KpiCard
                title="Traslados Inter-Campus"
                value={fmt(intercampus.data?.total_viajes)}
                subtitle="viajes detectados entre CSF y CHS"
                icon={ArrowRightLeft}
                iconColor="#003865"
              />
              <KpiCard
                title="Tiempo Medio Traslado"
                value={`${intercampus.data?.tiempo_promedio_min ?? 0} min`}
                subtitle={`Mediana: ${intercampus.data?.tiempo_mediano_min ?? 0} min`}
                icon={RotateCcw}
              />
              <KpiCard
                title="Franja Mayor Migración"
                value={intercampus.data?.franja_punta ?? '—'}
                subtitle="cambio de turno y bloque docente"
                icon={Flame}
                iconColor="#C59B27"
              />
            </div>

            <div className="xl:col-span-2">
              <ChartCard layout="full" title="Flujo de Movilidad Inter-Campus (CSF ↔ CHS)">
                <Suspense fallback={<EsqueletoGraficoVehicular />}>
                  {intercampus.data ? (
                    <IntercampusMobilityPlotlyChart data={intercampus.data} />
                  ) : (
                    <EmptyState label="Cargando movilidad intercampus..." />
                  )}
                </Suspense>
              </ChartCard>
            </div>
          </div>

          {/* Impacto del Calendario en Tráfico Vehicular */}
          <div className="w-full">
            <ChartCard layout="full" title="Impacto del Calendario Académico en Flujo Vehicular">
              <Suspense fallback={<EsqueletoGraficoVehicular />}>
                {milestones.data && milestones.data.length > 0 ? (
                  <VehicleMilestonesPlotlyChart data={milestones.data} />
                ) : (
                  <EmptyState label="Sin datos de impacto de calendario" />
                )}
              </Suspense>
            </ChartCard>
          </div>

          {/* Machine Learning K-Means */}
          <div className="space-y-4 pt-2">
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
                <ChartCard layout="full" title="Dispersión de Perfiles: Hora Llegada vs Permanencia" contextoGrafico="permanencia_vehicular">
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
                <ChartCard layout="full" title="Resumen de Clústeres Detectados">
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

      {/* Resumen Final de Integridad ANPR y Picos */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title="Parque Vehicular Único"
          value={fmt(kpis.data?.vehiculos_unicos)}
          subtitle="patentes distintas detectadas"
          icon={Car}
        />
        <KpiCard
          title="Tasa Lecturas Fallidas"
          value={`${fmt(kpis.data?.tasa_lectura_fallida_pct, 1)}%`}
          subtitle="calidad de captura ANPR"
          icon={Wifi}
        />
        <KpiCard
          title="Hora Punta Vehicular"
          value={kpis.data?.hora_punta ?? '—'}
          subtitle="bloque con mayor ingreso"
          icon={Flame}
          iconColor="#DC2626"
        />
        <KpiCard
          title="Máximo Aforo Simultáneo"
          value={`${fmt(kpis.data?.max_aforo_historico)} veh`}
          subtitle="pico horario registrado"
          icon={TrendingUp}
          iconColor="#2563EB"
        />
      </div>
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
