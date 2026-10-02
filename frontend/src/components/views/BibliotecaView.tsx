import { Users, Clock, BarChart2, TrendingDown, Wifi, Flame, TrendingUp, AlertTriangle } from 'lucide-react'
import { KpiCard } from '../ui/KpiCard'
import { ChartCard } from '../ui/ChartCard'
import { LiveBadge } from '../ui/LiveBadge'
import { OccupancyAreaChart } from '../charts/OccupancyAreaChart'
import { ForecastLineChart } from '../charts/ForecastLineChart'
import { HeatmapChart } from '../charts/HeatmapChart'
import { HourlyBarChart } from '../charts/HourlyBarChart'
import { PeakValleyPlotlyChart } from '../charts/PeakValleyPlotlyChart'
import { WeeklyEvolutionPlotlyChart } from '../charts/WeeklyEvolutionPlotlyChart'
import { MonthlyVolumePlotlyChart } from '../charts/MonthlyVolumePlotlyChart'
import { AcademicMilestonesPlotlyChart } from '../charts/AcademicMilestonesPlotlyChart'
import { DoorUsagePlotlyChart } from '../charts/DoorUsagePlotlyChart'
import { CheckinDistributionPlotlyChart } from '../charts/CheckinDistributionPlotlyChart'
import { Forecast14DaysPlotlyChart } from '../charts/Forecast14DaysPlotlyChart'
import { VisitProfilesPlotlyChart } from '../charts/VisitProfilesPlotlyChart'
import { DateRange } from '../../types/dateRange'
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
  useForecast14Days,
  useVisitProfiles,
} from '../../hooks/useAttendance'

const CAPACIDAD = 350

function fmt(n: number | undefined, dec = 0) {
  if (n === undefined || n === null) return '—'
  return n.toLocaleString('es-CL', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

interface Props {
  dateRange?: DateRange
}

export function BibliotecaView({ dateRange }: Props) {
  const kpis          = useAttendanceKpis()
  const live          = useOccupancyRealtime()
  const flow          = useAttendanceHourlyFlow(dateRange?.inicio, dateRange?.fin)
  const heatmap       = useHeatmap()
  const forecast      = useForecastAttendance()
  const alerts        = useAlerts()
  const peakValley    = usePeakValley()
  const weekly        = useWeeklyEvolution()
  const monthly       = useMonthlyVolume()
  const milestones    = useAcademicMilestones()
  const doors         = useDoorsUsage()
  const checkins      = useCheckinsDistribution()
  const forecast14d   = useForecast14Days(1)
  const visitProfiles = useVisitProfiles(1)

  const bibAlert = alerts.data?.alertas.find(a => a.recinto === 'biblioteca')

  const lastTs = live.data?.timestamp
    ? new Date(live.data.timestamp).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })
    : undefined

  return (
    <div className="p-6 space-y-6 max-w-screen-2xl mx-auto">
      {bibAlert && (
        <div className="flex items-center gap-3 p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-200">
          <AlertTriangle className="text-amber-400 shrink-0" size={20} />
          <div>
            <p className="text-sm font-semibold text-amber-300">Alerta Preventiva de Saturación (Prophet)</p>
            <p className="text-xs text-amber-200/80">{bibAlert.mensaje}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard
          title="Afluencia Total"
          value={fmt(kpis.data?.total_registros)}
          subtitle={`${fmt(kpis.data?.usuarios_unicos)} personas únicas`}
          icon={Users}
          iconColor="#003865"
        />
        <KpiCard
          title="Aforo en Vivo"
          value={live.isLoading ? '…' : `${live.data?.aforo_actual ?? 0} / ${CAPACIDAD}`}
          subtitle={`${live.data?.ocupacion_pct ?? 0}% ocupación`}
          icon={Wifi}
          iconColor="#C59B27"
          alert={live.data?.nivel_alerta}
        />
        <KpiCard
          title="Estadía Promedio"
          value={`${fmt(kpis.data?.permanencia_promedio_min, 0)} min`}
          subtitle={`Mediana: ${fmt(kpis.data?.permanencia_mediana_min, 0)} min`}
          icon={Clock}
          iconColor="#16A34A"
        />
        <KpiCard
          title="Tasa de Rebote"
          value={`${fmt(kpis.data?.tasa_rebote_pct, 1)}%`}
          subtitle="Visitas < 15 minutos"
          icon={TrendingDown}
          iconColor="#D97706"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard
          title={`Curva de Aforo Concurrente vs Capacidad — ${dateRange?.label ?? 'Período'}`}
          action={<LiveBadge lastUpdated={lastTs} />}
        >
          {flow.data && flow.data.length > 0 ? (
            <OccupancyAreaChart data={flow.data} capacidad={CAPACIDAD} />
          ) : (
            <EmptyState label="Sin datos de flujo horario para este período" />
          )}
          <div className="flex items-center gap-4 mt-2 text-xs text-uct-text-muted">
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-uct-success inline-block" /> 70% ({Math.round(CAPACIDAD * 0.70)})</span>
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-uct-warning inline-block" /> 85% ({Math.round(CAPACIDAD * 0.85)})</span>
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-uct-danger inline-block" /> Límite ({CAPACIDAD})</span>
          </div>
        </ChartCard>

        <ChartCard
          title="Pronóstico Prophet — Próximos 3 días"
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
            <EmptyState label={forecast.data?.model_status.message ?? 'Sin pronóstico disponible'} />
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title={`Flujo Horario de Ingresos y Salidas — ${dateRange?.label ?? 'Período'}`}>
          {flow.data && flow.data.length > 0 ? (
            <HourlyBarChart data={flow.data} />
          ) : (
            <EmptyState label="Sin datos de flujo para este período" />
          )}
        </ChartCard>

        <ChartCard title="Mapa de Calor — Ocupación por Día y Hora">
          {heatmap.data && heatmap.data.length > 0 ? (
            <HeatmapChart data={heatmap.data} />
          ) : (
            <EmptyState label="Sin datos de heatmap" />
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="Franjas Pico y Valle Operativo (Plotly)">
          {peakValley.data && peakValley.data.length > 0 ? (
            <PeakValleyPlotlyChart data={peakValley.data} />
          ) : (
            <EmptyState label="Sin datos de franjas" />
          )}
        </ChartCard>

        <ChartCard title="Evolución Semanal ISO (Plotly)" contextoGrafico="aforo_semanal">
          {weekly.data && weekly.data.length > 0 ? (
            <WeeklyEvolutionPlotlyChart data={weekly.data} />
          ) : (
            <EmptyState label="Sin datos semanales" />
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="Volumen y Promedio Diario Mensual (Plotly)">
          {monthly.data && monthly.data.length > 0 ? (
            <MonthlyVolumePlotlyChart data={monthly.data} />
          ) : (
            <EmptyState label="Sin datos mensuales" />
          )}
        </ChartCard>

        <ChartCard title="Comparativa por Hito Académico UCT (Plotly)">
          {milestones.data && milestones.data.length > 0 ? (
            <AcademicMilestonesPlotlyChart data={milestones.data} />
          ) : (
            <EmptyState label="Sin datos de calendario" />
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="Uso de Torniquetes de Acceso (Plotly)">
          {doors.data && doors.data.length > 0 ? (
            <DoorUsagePlotlyChart data={doors.data} />
          ) : (
            <EmptyState label="Sin datos de torniquetes" />
          )}
        </ChartCard>

        <ChartCard title="Distribución de Marcajes por Registro (Plotly)">
          {checkins.data && checkins.data.length > 0 ? (
            <CheckinDistributionPlotlyChart data={checkins.data} />
          ) : (
            <EmptyState label="Sin datos de marcajes" />
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2">
          <ChartCard title="Proyección de Demanda Futura — 14 Días (HistGradientBoosting + Calendario)">
            {forecast14d.data?.predicciones && forecast14d.data.predicciones.length > 0 ? (
              <Forecast14DaysPlotlyChart data={forecast14d.data.predicciones} />
            ) : (
              <EmptyState label="Sin proyección de 14 días" />
            )}
          </ChartCard>
        </div>

        <ChartCard title="Perfiles de Visita (Random Forest Classifier)">
          {visitProfiles.data?.perfiles && visitProfiles.data.perfiles.length > 0 ? (
            <VisitProfilesPlotlyChart
              data={visitProfiles.data.perfiles}
              accuracy={visitProfiles.data.accuracy}
            />
          ) : (
            <EmptyState label="Sin datos de perfiles" />
          )}
        </ChartCard>
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
        <p className="text-xs mt-1 opacity-60">Ejecuta el seed y el backend para ver datos reales</p>
      </div>
    </div>
  )
}
