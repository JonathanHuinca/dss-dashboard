import axios from 'axios'

const API_BASE = (import.meta as unknown as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL ?? 'http://localhost:8000/api/v1'

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 15_000,
})

api.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('uct_auth_token') : null
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

axios.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('uct_auth_token') : null
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AttendanceKpis {
  total_registros: number
  usuarios_unicos: number
  dias_operativos: number
  promedio_marcajes_diarios: number
  tasa_recurrencia_mensual: number
  permanencia_promedio_min: number
  permanencia_mediana_min: number
  tasa_rebote_pct: number
  horas_estudiante_total: number
  hora_punta?: string
  max_aforo_historico?: number
}

export interface OccupancyRealtime {
  aforo_actual: number
  capacidad_maxima: number
  ocupacion_pct: number
  nivel_alerta: 'normal' | 'preventivo' | 'critico'
  timestamp: string
}

export interface HourlyFlowPoint {
  bucket: string
  ingresos: number
  salidas: number
  personas_unicas?: number
  entradas?: number
  lecturas_fallidas?: number
}

export interface HeatmapPoint {
  dia_semana: number
  dia_nombre: string
  hora: number
  ingresos_promedio: number
}

export interface VehicleKpis {
  vehiculos_unicos: number
  total_accesos: number
  dias_operativos: number
  turnover_rate_diario: number
  permanencia_mediana_min: number
  tasa_lectura_fallida_pct: number
  hora_punta?: string
  max_aforo_historico?: number
}

export interface ParkingOccupancy {
  vehiculos_presentes: number
  plazas_disponibles: number
  capacidad_maxima: number
  ocupacion_pct: number
  nivel_alerta: 'normal' | 'preventivo' | 'saturacion'
  timestamp: string
}

export interface FleetItem { tipo?: string; marca?: string; total: number; pct: number }
export interface FleetComposition {
  por_tipo: FleetItem[]
  por_marca: FleetItem[]
}

export interface ForecastPoint {
  ds: string
  yhat: number
  yhat_lower: number
  yhat_upper: number
}

export interface ForecastResponse {
  recinto: string
  model_status: { status: string; model_date?: string; message?: string }
  horizon_hours: number
  forecast: ForecastPoint[]
}

export interface AlertItem {
  recinto: string
  nivel: 'normal' | 'preventivo' | 'critico'
  mensaje: string
  horas_afectadas: { ds: string; yhat: number }[]
  capacidad_max: number
}

export interface AlertsResponse {
  total_alertas: number
  alertas: AlertItem[]
}

export const fetchAttendanceKpis       = () => api.get<AttendanceKpis>('/attendance/kpis').then(r => r.data)
export const fetchOccupancyRealtime    = () => api.get<OccupancyRealtime>('/attendance/occupancy-realtime').then(r => r.data)
export const fetchAttendanceHourlyFlow = (fechaInicio?: string, fechaFin?: string) =>
  api.get<HourlyFlowPoint[]>('/attendance/hourly-flow', { params: { fecha_inicio: fechaInicio, fecha_fin: fechaFin } }).then(r => r.data)
export const fetchHeatmap              = () => api.get<HeatmapPoint[]>('/attendance/heatmap').then(r => r.data)

export const fetchVehicleKpis          = () => api.get<VehicleKpis>('/vehicles/kpis').then(r => r.data)
export const fetchParkingOccupancy     = () => api.get<ParkingOccupancy>('/vehicles/parking-occupancy').then(r => r.data)
export const fetchVehicleHourlyFlow    = (fechaInicio?: string, fechaFin?: string) =>
  api.get<HourlyFlowPoint[]>('/vehicles/hourly-flow', { params: { fecha_inicio: fechaInicio, fecha_fin: fechaFin } }).then(r => r.data)
export const fetchFleetComposition     = () => api.get<FleetComposition>('/vehicles/fleet-composition').then(r => r.data)

export interface CameraStatPoint {
  camara: string
  entradas: number
  salidas: number
  lecturas_fallidas: number
}

export interface VehicleDailyPoint {
  fecha: string
  entradas: number
  salidas: number
  vehiculos_unicos: number
}

export const fetchCameraStats                 = () => api.get<CameraStatPoint[]>('/vehicles/camera-stats').then(r => r.data)
export const fetchVehicleDailyEvolution       = () => api.get<VehicleDailyPoint[]>('/vehicles/daily-evolution').then(r => r.data)
export const fetchVehicleAcademicMilestones   = () => api.get<AcademicMilestonePoint[]>('/vehicles/academic-milestones-comparison').then(r => r.data)

export interface IntercampusDailyFlow {
  fecha: string
  csf_a_chs: number
  chs_a_csf: number
  total: number
}

export interface IntercampusHourlyDist {
  hora: string
  viajes: number
}

export interface IntercampusMobilityResponse {
  total_viajes: number
  csf_a_chs: number
  chs_a_csf: number
  tiempo_promedio_min: number
  tiempo_mediano_min: number
  franja_punta: string
  flujo_por_fecha: IntercampusDailyFlow[]
  distribucion_horaria: IntercampusHourlyDist[]
}

export interface BehavioralClusterItem {
  perfil: string
  color: string
  total_vehiculos: number
  porcentaje: number
  hora_llegada_promedio: number
  permanencia_promedio_min: number
  dias_activos_promedio: number
  tasa_jornada_extrema_pct: number
}

export interface ScatterSamplePoint {
  patente_hash: string
  hora_llegada: number
  permanencia_min: number
  dias: number
  perfil: string
  color: string
}

export interface BehavioralClustersResponse {
  total_vehiculos_analizados: number
  distribucion: BehavioralClusterItem[]
  vehiculos_externos_count: number
  vehiculos_externos_pct: number
  scatter_sample: ScatterSamplePoint[]
}

export const fetchIntercampusMobility = () => api.get<IntercampusMobilityResponse>('/vehicles/intercampus-mobility').then(r => r.data)
export const fetchBehavioralClusters  = () => api.get<BehavioralClustersResponse>('/vehicles/behavioral-clusters').then(r => r.data)


export interface Forecast14DayItem {
  fecha: string
  dia_nombre: string
  hito: string
  color: string
  is_exam_period: boolean
  is_break: boolean
  is_holiday: boolean
  demanda_estimada: number
}

export interface Forecast14DaysResponse {
  recinto: string
  espacio_id: number
  horizon_days: number
  fecha_inicio: string
  fecha_fin: string
  predicciones: Forecast14DayItem[]
  model_status: {
    status: string
    model_type: string
    r2_score: number
    trained_date: string
  }
}

export interface VisitProfileItem {
  perfil: string
  total: number
  porcentaje: number
  permanencia_promedio_min: number
}

export interface VisitProfilesResponse {
  espacio_id: number
  modelo_entrenado: boolean
  accuracy: number
  perfiles: VisitProfileItem[]
}

export const fetchForecast14Days = (espacioId: number = 1) =>
  api.get<Forecast14DaysResponse>('/predictions/forecast-14days', { params: { espacio_id: espacioId } }).then(r => r.data)

export const fetchVisitProfiles = (espacioId: number = 1) =>
  api.get<VisitProfilesResponse>('/predictions/visit-profiles', { params: { espacio_id: espacioId } }).then(r => r.data)



export interface PeakValleyPoint {
  hora: string
  promedio_ingresos: number
  max_ingresos: number
  total_ingresos: number
  nivel: string
  color: string
}

export interface WeeklyEvolutionPoint {
  semana_iso: string
  inicio_semana: string
  total_asistencias: number
  usuarios_unicos: number
}

export interface MonthlyVolumePoint {
  mes: string
  total_asistencias: number
  dias_activos: number
  promedio_diario: number
}

export interface AcademicMilestonePoint {
  hito: string
  dias_totales: number
  promedio_diario: number
  max_dia: number
  total_asistencias: number
}

export interface DoorUsagePoint {
  puerta: string
  puerta_id: string
  entradas: number
  salidas: number
  total: number
}

export interface CheckinDistributionPoint {
  marcajes: string
  total_registros: number
  porcentaje: number
}

export const fetchForecastAttendance   = () => api.get<ForecastResponse>('/predictions/forecast-attendance').then(r => r.data)
export const fetchForecastParking      = () => api.get<ForecastResponse>('/predictions/forecast-parking').then(r => r.data)
export const fetchAlerts               = () => api.get<AlertsResponse>('/predictions/alerts').then(r => r.data)

export const fetchPeakValley           = () => api.get<PeakValleyPoint[]>('/attendance/peak-valley').then(r => r.data)
export const fetchWeeklyEvolution      = () => api.get<WeeklyEvolutionPoint[]>('/attendance/weekly-evolution').then(r => r.data)
export const fetchMonthlyVolume        = () => api.get<MonthlyVolumePoint[]>('/attendance/monthly-volume').then(r => r.data)
export const fetchAcademicMilestones   = () => api.get<AcademicMilestonePoint[]>('/attendance/academic-milestones-comparison').then(r => r.data)
export const fetchDoorsUsage           = () => api.get<DoorUsagePoint[]>('/attendance/doors-usage').then(r => r.data)
export const fetchCheckinsDistribution = () => api.get<CheckinDistributionPoint[]>('/attendance/checkins-distribution').then(r => r.data)

export interface AssistantRequest {
  message: string
  model?: string
  history?: { role: string; content: string }[]
}

export interface AssistantResponse {
  reply: string
  model_requested: string
  model_used: string
  success: boolean
  live_llm: boolean
  error?: string
}

export interface ModelItem {
  id: string
  name: string
  description: string
}

export interface ModelsResponse {
  models: ModelItem[]
  default: string
}

export const fetchAssistantModels = () =>
  api.get<ModelsResponse>('/assistant/models').then(r => r.data)

export const sendAssistantMessage = (payload: AssistantRequest) =>
  api.post<AssistantResponse>('/assistant/chat', payload, { timeout: 45_000 }).then(r => r.data)

export interface InteractiveChatRequest {
  prompt: string
  dataset_tipo: string
  session_id: string
  model?: string
  grafico_contexto?: string
}

export interface InteractiveChatResponse {
  tipo: 'plotly' | 'df' | 'text'
  explicacion: string
  fig_data?: { data: any[]; layout: any }
  table_data?: Record<string, any>[]
  session_id: string
  model_used: string
}

export interface ChatHistoryItem {
  id: string
  timestamp: string
  prompt: string
  dataset_tipo: string
  tipo: 'plotly' | 'df' | 'text'
  explicacion: string
  fig_data?: { data: any[]; layout: any }
  table_data?: Record<string, any>[]
  model_used: string
}

export interface ChatHistoryResponse {
  session_id: string
  messages: ChatHistoryItem[]
}

const getAuthHeaders = (): Record<string, string> => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('uct_auth_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export const sendInteractiveChatMessage = (payload: InteractiveChatRequest) =>
  axios.post<InteractiveChatResponse>('/api/chat', payload, {
    timeout: 45_000,
    headers: getAuthHeaders(),
  }).then(r => r.data)

export const fetchChatHistory = (sessionId: string) =>
  axios.get<ChatHistoryResponse>('/api/chat/history', {
    params: { session_id: sessionId },
    headers: getAuthHeaders(),
  }).then(r => r.data)

export const exportChatPdf = async (sessionId: string, titulo?: string) => {
  const res = await axios.post('/api/chat/export-pdf', { session_id: sessionId, titulo }, {
    responseType: 'blob',
    headers: getAuthHeaders(),
  })
  const blob = new Blob([res.data], { type: 'application/pdf' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `informe_ejecutivo_${sessionId.slice(0, 8)}.pdf`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

export interface KPISummary {
  dias_operativos: number
  horas_estudiante: number
  recurrencia_mensual: number
  hora_pico_ingreso: string
  pico_concurrente: number
  mes_referencia?: string
  periodo_label?: string
}

export const fetchKpiSummary = (espacioId: number = 1, fechaInicio?: string, fechaFin?: string) =>
  api.get<KPISummary>('/metrics/kpi-summary', {
    params: {
      espacio_id: espacioId,
      fecha_inicio: fechaInicio || undefined,
      fecha_fin: fechaFin || undefined,
    },
  }).then(r => r.data)



