import { Car, ParkingCircle, RotateCcw, Wifi, BarChart2, Flame, TrendingUp, AlertTriangle, ArrowRightLeft, ShieldAlert } from 'lucide-react'
import { KpiCard } from '../ui/KpiCard'
import { ChartCard } from '../ui/ChartCard'
import { LiveBadge } from '../ui/LiveBadge'
import { OccupancyAreaChart } from '../charts/OccupancyAreaChart'
import { HourlyBarChart } from '../charts/HourlyBarChart'
import { FleetDonutChart } from '../charts/FleetDonutChart'
import { ForecastLineChart } from '../charts/ForecastLineChart'
import { VehicleDailyPlotlyChart } from '../charts/VehicleDailyPlotlyChart'
import { VehicleMilestonesPlotlyChart } from '../charts/VehicleMilestonesPlotlyChart'
import { CameraStatsPlotlyChart } from '../charts/CameraStatsPlotlyChart'
import { IntercampusMobilityPlotlyChart } from '../charts/IntercampusMobilityPlotlyChart'
import { VehicleBehavioralClustersPlotlyChart } from '../charts/VehicleBehavioralClustersPlotlyChart'
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

const CAPACIDAD = 180

function fmt(n: number | undefined, dec = 0) {
  if (n === undefined || n === null) return '—'
  return n.toLocaleString('es-CL', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

interface Props {
  dateRange?: DateRange
}

export function EstacionamientoView({ dateRange }: Props) {
  const kpis       = useVehicleKpis()
  const live       = useParkingOccupancy()
  const flow       = useVehicleHourlyFlow(dateRange?.inicio, dateRange?.fin)
  const fleet      = useFleetComposition()
  const forecast   = useForecastParking()
  const alerts     = useAlerts()
  const camera     = useCameraStats()
  const daily       = useVehicleDailyEvolution()
  const milestones  = useVehicleAcademicMilestones()
  const intercampus = useIntercampusMobility()
  const clusters    = useBehavioralClusters()

  const vehAlert = alerts.data?.alertas.find(a => a.recinto === 'vehicular')

  const lastTs = live.data?.timestamp
    ? new Date(live.data.timestamp).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })
    : undefined

  return (
    <div className="p-6 space-y-6 max-w-screen-2xl mx-auto">
      {vehAlert && (
        <div className="flex items-center gap-3 p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-200">
          <AlertTriangle className="text-amber-400 shrink-0" size={20} />
          <div>
            <p className="text-sm font-semibold text-amber-300">Alerta Preventiva de Saturación Vehicular (Prophet)</p>
            <p className="text-xs text-amber-200/80">{vehAlert.mensaje}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard
          title="Vehículos Dentro"
          value={live.isLoading ? '…' : `${live.data?.vehiculos_presentes ?? 0} / ${CAPACIDAD}`}
          subtitle={`${live.data?.ocupacion_pct ?? 0}% ocupación`}
          icon={Car}
          iconColor="#C59B27"
          alert={live.data?.nivel_alerta}
        />
        <KpiCard
          title="Plazas Disponibles"
          value={live.data?.plazas_disponibles ?? '—'}
          subtitle={`de ${CAPACIDAD} plazas totales`}
          icon={ParkingCircle}
          iconColor="#16A34A"
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
          subtitle="por visita vehicular"
          icon={RotateCcw}
          iconColor="#D97706"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard
          title={`Curva de Ocupación vs Capacidad (180 plazas) — ${dateRange?.label ?? 'Período'}`}
          action={<LiveBadge lastUpdated={lastTs} />}
        >
          {flow.data && flow.data.length > 0 ? (
            <OccupancyAreaChart data={flow.data} capacidad={CAPACIDAD} unit="vehículos" />
          ) : (
            <EmptyState label="Sin datos de ocupación vehicular para este período" />
          )}
        </ChartCard>

        <ChartCard
          title="Pronóstico Prophet Vehicular — Próximos 3 días"
          action={
            forecast.data?.model_status.status === 'ok'
              ? <span className="text-xs text-uct-success font-medium">Modelo: {forecast.data.model_status.model_date}</span>
              : <span className="text-xs text-uct-warning">Modelo no entrenado</span>
          }
        >
          {forecast.data?.forecast && forecast.data.forecast.length > 0 ? (
            <ForecastLineChart
              actual={flow.data ?? []}
              forecast={forecast.data.forecast}
            />
          ) : (
            <EmptyState label={forecast.data?.model_status.message ?? 'Sin pronóstico vehicular disponible'} />
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <ChartCard title={`Flujo Horario de Accesos — ${dateRange?.label ?? 'Período'}`}>
          {flow.data && flow.data.length > 0 ? (
            <HourlyBarChart data={flow.data} />
          ) : (
            <EmptyState label="Sin datos de flujo horario" />
          )}
        </ChartCard>

        <ChartCard title="Composición de la Flota">
          {fleet.data?.por_tipo && fleet.data.por_tipo.length > 0 ? (
            <FleetDonutChart data={fleet.data.por_tipo} nameKey="tipo" />
          ) : (
            <EmptyState label="Sin datos de composición de flota" />
          )}
        </ChartCard>

        <ChartCard title="Top Marcas de Vehículos">
          {fleet.data?.por_marca && fleet.data.por_marca.length > 0 ? (
            <FleetDonutChart data={fleet.data.por_marca} nameKey="marca" />
          ) : (
            <EmptyState label="Sin datos de marcas" />
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-4">
        <ChartCard title="Evolución Diaria de Accesos Vehiculares (Plotly)">
          {daily.data && daily.data.length > 0 ? (
            <VehicleDailyPlotlyChart data={daily.data} />
          ) : (
            <EmptyState label="Sin datos de serie diaria vehicular" />
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="Impacto del Calendario en Flujo Vehicular (Plotly)">
          {milestones.data && milestones.data.length > 0 ? (
            <VehicleMilestonesPlotlyChart data={milestones.data} />
          ) : (
            <EmptyState label="Sin datos de impacto de calendario" />
          )}
        </ChartCard>

        <ChartCard title="Distribución de Capturas por Cámara ANPR (Plotly)">
          {camera.data && camera.data.length > 0 ? (
            <CameraStatsPlotlyChart data={camera.data} />
          ) : (
            <EmptyState label="Sin datos de cámaras" />
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-1 space-y-4">
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
          <ChartCard title="Flujo de Movilidad Inter-Campus (CSF ↔ CHS)">
            {intercampus.data ? (
              <IntercampusMobilityPlotlyChart data={intercampus.data} />
            ) : (
              <EmptyState label="Cargando movilidad intercampus..." />
            )}
          </ChartCard>
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 bg-slate-900/60 border border-slate-700/60 rounded-xl">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400">
              <ShieldAlert size={22} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-100">Detección de Uso Indebido y Perfiles de Comportamiento (K-Means)</h3>
              <p className="text-xs text-slate-400">Segmentación no supervisada ante ausencia de ground truth (bajo enrolamiento voluntario)</p>
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
            <ChartCard title="Dispersión de Perfiles: Hora Llegada vs Permanencia (Plotly)" contextoGrafico="permanencia_vehicular">
              {clusters.data ? (
                <VehicleBehavioralClustersPlotlyChart data={clusters.data} />
              ) : (
                <EmptyState label="Cargando segmentación K-Means..." />
              )}
            </ChartCard>
          </div>
          <div className="xl:col-span-1">
            <ChartCard title="Resumen de Clústeres Detectados">
              <div className="space-y-3">
                {clusters.data?.distribucion.map((c, i) => (
                  <div key={i} className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold" style={{ color: c.color }}>{c.perfil}</span>
                      <span className="text-xs font-mono font-bold text-slate-300">{c.total_vehiculos} veh ({c.porcentaje}%)</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-400">
                      <div>Llegada: <span className="text-slate-200">{c.hora_llegada_promedio}:00 hrs</span></div>
                      <div>Permanencia: <span className="text-slate-200">{c.permanencia_promedio_min} min</span></div>
                      <div>Días act.: <span className="text-slate-200">{c.dias_activos_promedio} días</span></div>
                      <div>Jornada &gt;8h: <span className="text-slate-200">{c.tasa_jornada_extrema_pct}%</span></div>
                    </div>
                  </div>
                ))}
              </div>
            </ChartCard>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard
          title="Vehículos Únicos"
          value={fmt(kpis.data?.vehiculos_unicos)}
          subtitle="patentes distintas registradas"
          icon={Car}
        />
        <KpiCard
          title="Lecturas Fallidas"
          value={`${fmt(kpis.data?.tasa_lectura_fallida_pct, 1)}%`}
          subtitle="calidad de lectura ANPR"
          icon={Wifi}
        />
        <KpiCard
          title="Hora Pico Vehicular"
          value={kpis.data?.hora_punta ?? '—'}
          subtitle="mayor ingreso vehicular"
          icon={Flame}
          iconColor="#DC2626"
        />
        <KpiCard
          title="Pico de Entradas"
          value={`${fmt(kpis.data?.max_aforo_historico)} veh`}
          subtitle="máximo horario registrado"
          icon={TrendingUp}
          iconColor="#2563EB"
        />
      </div>
    </div>
  )
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="h-48 flex items-center justify-center text-uct-text-muted text-sm">
      <div className="text-center">
        <BarChart2 size={32} className="mx-auto mb-2 opacity-30" />
        <p>{label}</p>
        <p className="text-xs mt-1 opacity-60">Selecciona otro período en la barra superior</p>
      </div>
    </div>
  )
}
