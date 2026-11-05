import React, { useState, memo, lazy, Suspense } from 'react'
import { Bot, Table as TableIcon, FileText, FileSpreadsheet } from 'lucide-react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { exportarConsultaPdf, exportarConsultaExcel } from '../../utils/exportadorConsulta'

const HeatmapChart = lazy(() => import('../charts/HeatmapChart').then(m => ({ default: m.HeatmapChart })))
const HourlyBarChart = lazy(() => import('../charts/HourlyBarChart').then(m => ({ default: m.HourlyBarChart })))
const PeakValleyPlotlyChart = lazy(() => import('../charts/PeakValleyPlotlyChart').then(m => ({ default: m.PeakValleyPlotlyChart })))
const OccupancyAreaChart = lazy(() => import('../charts/OccupancyAreaChart').then(m => ({ default: m.OccupancyAreaChart })))
const ForecastLineChart = lazy(() => import('../charts/ForecastLineChart').then(m => ({ default: m.ForecastLineChart })))
const FleetDonutChart = lazy(() => import('../charts/FleetDonutChart').then(m => ({ default: m.FleetDonutChart })))
const DoorUsagePlotlyChart = lazy(() => import('../charts/DoorUsagePlotlyChart').then(m => ({ default: m.DoorUsagePlotlyChart })))
const RoomComparisonPlotlyChart = lazy(() => import('../charts/RoomComparisonPlotlyChart').then(m => ({ default: m.RoomComparisonPlotlyChart })))
const DailyAverageAttendancePlotlyChart = lazy(() => import('../charts/DailyAverageAttendancePlotlyChart').then(m => ({ default: m.DailyAverageAttendancePlotlyChart })))
const MonthlyVolumePlotlyChart = lazy(() => import('../charts/MonthlyVolumePlotlyChart').then(m => ({ default: m.MonthlyVolumePlotlyChart })))
const WeeklyEvolutionPlotlyChart = lazy(() => import('../charts/WeeklyEvolutionPlotlyChart').then(m => ({ default: m.WeeklyEvolutionPlotlyChart })))
const AcademicMilestonesPlotlyChart = lazy(() => import('../charts/AcademicMilestonesPlotlyChart').then(m => ({ default: m.AcademicMilestonesPlotlyChart })))
const CurricularDistributionPlotlyChart = lazy(() => import('../charts/CurricularDistributionPlotlyChart').then(m => ({ default: m.CurricularDistributionPlotlyChart })))
const CheckinDistributionPlotlyChart = lazy(() => import('../charts/CheckinDistributionPlotlyChart').then(m => ({ default: m.CheckinDistributionPlotlyChart })))
const Forecast14DaysPlotlyChart = lazy(() => import('../charts/Forecast14DaysPlotlyChart').then(m => ({ default: m.Forecast14DaysPlotlyChart })))
const VisitProfilesPlotlyChart = lazy(() => import('../charts/VisitProfilesPlotlyChart').then(m => ({ default: m.VisitProfilesPlotlyChart })))
const CameraStatsPlotlyChart = lazy(() => import('../charts/CameraStatsPlotlyChart').then(m => ({ default: m.CameraStatsPlotlyChart })))
const IntercampusMobilityPlotlyChart = lazy(() => import('../charts/IntercampusMobilityPlotlyChart').then(m => ({ default: m.IntercampusMobilityPlotlyChart })))
const VehicleDailyPlotlyChart = lazy(() => import('../charts/VehicleDailyPlotlyChart').then(m => ({ default: m.VehicleDailyPlotlyChart })))
const VehicleMilestonesPlotlyChart = lazy(() => import('../charts/VehicleMilestonesPlotlyChart').then(m => ({ default: m.VehicleMilestonesPlotlyChart })))
const VehicleBehavioralClustersPlotlyChart = lazy(() => import('../charts/VehicleBehavioralClustersPlotlyChart').then(m => ({ default: m.VehicleBehavioralClustersPlotlyChart })))

export interface ChatMessageData {
  id: string
  role: 'user' | 'assistant'
  content: string
  tipo?: string
  component?: string
  payload?: any
  fig_data?: { data: any[]; layout: any }
  table_data?: Record<string, any>[]
  dataset_tipo?: string
  modelUsed?: string
  timestamp: string
}

interface ChatMessageProps {
  msg: ChatMessageData
  preguntaTexto?: string
  espacioId?: number
}

function ChatMessageComponent({ msg, preguntaTexto, espacioId }: ChatMessageProps) {
  const isUser = msg.role === 'user'
  const [exportandoPdf, setExportandoPdf] = useState(false)
  const [exportandoExcel, setExportandoExcel] = useState(false)

  const handleExportarPdf = async () => {
    if (exportandoPdf) return
    const tituloConsulta = preguntaTexto || 'Consulta Analítica DSS'
    setExportandoPdf(true)
    try {
      await exportarConsultaPdf({
        pregunta: tituloConsulta,
        respuesta: msg.content,
        payload: msg.payload,
        tableData: msg.table_data,
        elementoId: (msg.component || msg.fig_data) ? `chart-box-${msg.id}` : undefined,
        espacioId: espacioId || (msg.dataset_tipo === 'estacionamiento' ? 2 : 1),
        titulo: tituloConsulta,
      })
    } catch (err) {
      console.error('Error exportando consulta a PDF:', err)
    } finally {
      setExportandoPdf(false)
    }
  }

  const handleExportarExcel = async () => {
    if (exportandoExcel) return
    const tituloConsulta = preguntaTexto || 'Consulta Analítica DSS'
    setExportandoExcel(true)
    try {
      await exportarConsultaExcel({
        pregunta: tituloConsulta,
        respuesta: msg.content,
        payload: msg.payload,
        tableData: msg.table_data,
        elementoId: (msg.component || msg.fig_data) ? `chart-box-${msg.id}` : undefined,
        espacioId: espacioId || (msg.dataset_tipo === 'estacionamiento' ? 2 : 1),
        titulo: tituloConsulta,
        component: msg.component,
        figData: msg.fig_data,
      })
    } catch (err) {
      console.error('Error exportando consulta a Excel:', err)
    } finally {
      setExportandoExcel(false)
    }
  }

  const renderComponent = () => {
    if (!msg.component && !msg.fig_data) return null

    const fallbackLoader = <div className="h-48 animate-pulse bg-slate-100 rounded-xl" />

    switch (msg.component) {
      case 'OccupancyAreaChart':
        if (Array.isArray(msg.payload) && msg.payload.length > 0) {
          const isEstacionamiento = msg.dataset_tipo === 'estacionamiento' || msg.payload[0]?.entradas !== undefined
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2 min-h-[300px]">
              <Suspense fallback={fallbackLoader}>
                <OccupancyAreaChart
                  data={msg.payload}
                  capacidad={isEstacionamiento ? 180 : 350}
                  unit={isEstacionamiento ? 'vehículos' : 'ocupantes'}
                />
              </Suspense>
            </div>
          )
        }
        break

      case 'ForecastLineChart':
        if (msg.payload) {
          const forecastData = msg.payload.forecast || msg.payload.pronostico_7d || []
          const histData = msg.payload.historico_7d || []
          const cap = msg.payload.capacidad_asientos ?? (msg.dataset_tipo === 'estacionamiento' ? 180 : 350)
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <ForecastLineChart
                  forecast={forecastData}
                  historico7d={histData}
                  pronostico7d={msg.payload.pronostico_7d}
                  capacidad={cap}
                  recinto={msg.dataset_tipo === 'estacionamiento' ? 'vehicular' : 'biblioteca'}
                />
              </Suspense>
            </div>
          )
        }
        break

      case 'HourlyBarChart':
        if (Array.isArray(msg.payload) && msg.payload.length > 0) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2 h-64">
              <Suspense fallback={fallbackLoader}>
                <HourlyBarChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'HeatmapChart':
        if (Array.isArray(msg.payload) && msg.payload.length > 0) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2 h-64">
              <Suspense fallback={fallbackLoader}>
                <HeatmapChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'RoomComparisonPlotlyChart':
        if (msg.payload) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <RoomComparisonPlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'DoorUsagePlotlyChart':
        if (Array.isArray(msg.payload) && msg.payload.length > 0) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <DoorUsagePlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'CheckinDistributionPlotlyChart':
        if (Array.isArray(msg.payload) && msg.payload.length > 0) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <CheckinDistributionPlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'DailyAverageAttendancePlotlyChart':
        if (msg.payload) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <DailyAverageAttendancePlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'MonthlyVolumePlotlyChart':
        if (Array.isArray(msg.payload) && msg.payload.length > 0) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <MonthlyVolumePlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'WeeklyEvolutionPlotlyChart':
        if (Array.isArray(msg.payload) && msg.payload.length > 0) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <WeeklyEvolutionPlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'AcademicMilestonesPlotlyChart':
        if (Array.isArray(msg.payload) && msg.payload.length > 0) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <AcademicMilestonesPlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'CurricularDistributionPlotlyChart':
        if (msg.payload) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <CurricularDistributionPlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'Forecast14DaysPlotlyChart':
        if (msg.payload) {
          const preds = Array.isArray(msg.payload) ? msg.payload : (msg.payload.predicciones || [])
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <Forecast14DaysPlotlyChart data={preds} />
              </Suspense>
            </div>
          )
        }
        break

      case 'VisitProfilesPlotlyChart':
        if (msg.payload) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <VisitProfilesPlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'FleetDonutChart':
        if (Array.isArray(msg.payload) && msg.payload.length > 0) {
          const nameKey = msg.payload[0]?.marca !== undefined ? 'marca' : 'tipo'
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <FleetDonutChart data={msg.payload} nameKey={nameKey} />
              </Suspense>
            </div>
          )
        }
        break

      case 'CameraStatsPlotlyChart':
        if (Array.isArray(msg.payload) && msg.payload.length > 0) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <CameraStatsPlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'IntercampusMobilityPlotlyChart':
        if (msg.payload) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <IntercampusMobilityPlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'VehicleDailyPlotlyChart':
        if (Array.isArray(msg.payload) && msg.payload.length > 0) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <VehicleDailyPlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'VehicleMilestonesPlotlyChart':
        if (Array.isArray(msg.payload) && msg.payload.length > 0) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <VehicleMilestonesPlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'VehicleBehavioralClustersPlotlyChart':
        if (msg.payload) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <VehicleBehavioralClustersPlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      case 'PeakValleyPlotlyChart':
        if (Array.isArray(msg.payload)) {
          return (
            <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
              <Suspense fallback={fallbackLoader}>
                <PeakValleyPlotlyChart data={msg.payload} />
              </Suspense>
            </div>
          )
        }
        break

      default:
        break
    }

    if (msg.fig_data && Array.isArray(msg.fig_data.data) && msg.fig_data.layout) {
      return (
        <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-2 mt-2">
          <InteractiveChart
            data={msg.fig_data.data}
            layout={msg.fig_data.layout}
            height={260}
            filename="grafico_asistente_uct"
          />
        </div>
      )
    }

    return null
  }

  // Discriminación rigurosa de intención de visualización
  const tieneSolicitudGrafico = Boolean(
    (msg.component || msg.fig_data) && msg.tipo !== 'text'
  )
  const textoHaIniciado = Boolean(msg.content && msg.content.trim().length > 0)
  const componenteGrafico = (tieneSolicitudGrafico && (textoHaIniciado || Boolean(msg.payload || msg.fig_data)))
    ? renderComponent()
    : null

  return (
    <div className={`flex gap-2.5 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-lg bg-uct-blue-primary/10 text-uct-blue-primary flex items-center justify-center shrink-0 mt-0.5 border border-uct-blue-primary/20">
          <Bot size={15} />
        </div>
      )}

      <div
        className={`max-w-[90%] rounded-2xl p-3 text-xs leading-relaxed ${
          isUser
            ? 'bg-uct-blue-primary text-white rounded-br-xs shadow-xs'
            : 'bg-white text-slate-800 border border-slate-200/80 rounded-bl-xs shadow-xs space-y-2.5'
        }`}
      >
        {/* 1. Bloque de narrativa y análisis de texto: se muestra siempre en primer lugar */}
        {!msg.content ? (
          <div className="flex items-center gap-1.5 py-1 text-slate-500 font-medium">
            <div className="w-1.5 h-1.5 rounded-full bg-uct-gold animate-bounce" />
            <div className="w-1.5 h-1.5 rounded-full bg-uct-gold animate-bounce [animation-delay:0.2s]" />
            <div className="w-1.5 h-1.5 rounded-full bg-uct-gold animate-bounce [animation-delay:0.4s]" />
            <span className="text-[11px] text-slate-400 ml-1">Procesando respuesta analítica...</span>
          </div>
        ) : (
          <div className={`whitespace-pre-wrap leading-relaxed ${isUser ? 'text-white font-medium' : 'text-slate-800'}`}>{msg.content}</div>
        )}

        {/* 2. Componente gráfico interactivo: exclusivamente debajo del texto analítico */}
        {tieneSolicitudGrafico && componenteGrafico && (
          <div id={`chart-box-${msg.id}`} className="w-full pt-1">
            {componenteGrafico}
          </div>
        )}

        {Array.isArray(msg.table_data) && msg.table_data.length > 0 && typeof msg.table_data[0] === 'object' && msg.table_data[0] !== null && (
          <details className="mt-2 text-[11px] bg-slate-50 rounded-lg border border-slate-200 p-2 cursor-pointer group">
            <summary className="font-semibold text-uct-blue-primary select-none flex items-center gap-1.5 hover:text-uct-gold transition-colors">
              <TableIcon size={13} className="text-emerald-600 inline" />
              <span>Ver detalle tabular ({msg.table_data.length} filas)</span>
            </summary>
            <div className="overflow-x-auto rounded-lg border border-slate-200 mt-2 bg-white max-h-48">
              <table className="w-full text-[11px] text-left border-collapse">
                <thead className="bg-uct-blue-primary text-white uppercase text-[10px] sticky top-0">
                  <tr>
                    {Object.keys(msg.table_data[0] || {}).map((col, idx) => (
                      <th key={idx} className="px-2.5 py-1.5 font-semibold">
                        {col.replace(/_/g, ' ')}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {msg.table_data.slice(0, 15).map((row, rIdx) => (
                    <tr key={rIdx} className="hover:bg-slate-50">
                      {Object.values(row || {}).map((val: any, cIdx) => (
                        <td key={cIdx} className="px-2.5 py-1 text-slate-600">
                          {typeof val === 'number' ? val.toLocaleString() : String(val)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}

        {!isUser && msg.content && (
          <div className="flex items-center gap-2 pt-2 border-t border-slate-100 mt-2">
            <button
              type="button"
              onClick={handleExportarPdf}
              disabled={exportandoPdf}
              className="flex items-center gap-1.5 text-[11px] font-medium text-slate-700 hover:text-uct-blue-primary bg-slate-50 hover:bg-slate-100 border border-slate-200 px-2 py-1 rounded-md transition-colors cursor-pointer disabled:opacity-50"
              title="Descargar esta consulta en PDF"
            >
              <FileText size={12} className="text-red-600" />
              <span>{exportandoPdf ? 'Generando PDF...' : 'Descargar PDF'}</span>
            </button>
            {tieneSolicitudGrafico && componenteGrafico && (
              <button
                type="button"
                onClick={handleExportarExcel}
                disabled={exportandoExcel}
                className="flex items-center gap-1.5 text-[11px] font-medium text-slate-700 hover:text-emerald-700 bg-slate-50 hover:bg-slate-100 border border-slate-200 px-2 py-1 rounded-md transition-colors cursor-pointer disabled:opacity-50"
                title="Descargar datos en Excel modificable (.xlsx) con fórmulas y gráfico"
              >
                <FileSpreadsheet size={12} className="text-emerald-600" />
                <span>{exportandoExcel ? 'Generando Excel...' : 'Descargar Excel'}</span>
              </button>
            )}
          </div>
        )}

        <div
          className={`flex items-center justify-between text-[10px] pt-1 ${
            isUser ? 'text-white/60' : 'text-slate-400'
          }`}
        >
          <span>{msg.timestamp}</span>
          {!isUser && msg.modelUsed && (
            <span className="font-mono text-[9px] text-slate-400">
              {msg.modelUsed}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

export const ChatMessage = memo(ChatMessageComponent)
export default ChatMessage
