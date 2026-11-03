import { api } from './clienteBase'

export interface ForecastPoint {
  ds: string
  yhat: number
  yhat_lower: number
  yhat_upper: number
  actual?: number | null
  es_abierto?: number
}

export interface ForecastResponse {
  recinto: string
  sala?: string
  capacidad_asientos?: number
  model_status: { status: string; model_type?: string; model_date?: string; message?: string }
  horizon_hours: number
  total_timeline_hours?: number
  anchor_timestamp?: string
  historico_7d?: ForecastPoint[]
  pronostico_7d?: ForecastPoint[]
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

export interface ModeloEstadoItem {
  clave: string
  familia: string
  archivo: string
  disponible: boolean
  version?: string | null
  wape?: number | null
  mae?: number | null
  ultima_modificacion?: string | null
  estado: string
}

// ─── Funciones API Predicción y Modelos ML ─────────────────────────────────────

export const fetchForecast14Days = (espacioId: number = 1) =>
  api.get<Forecast14DaysResponse>('/predictions/forecast-14days', { params: { espacio_id: espacioId } }).then(r => r.data)

export const fetchVisitProfiles = (espacioId: number = 1) =>
  api.get<VisitProfilesResponse>('/predictions/visit-profiles', { params: { espacio_id: espacioId } }).then(r => r.data)

export const fetchForecastAttendance = (sala: string = 'todas') =>
  api.get<ForecastResponse>('/predictions/forecast-attendance', { params: { sala } }).then(r => r.data)

export const fetchForecastParking = () =>
  api.get<ForecastResponse>('/predictions/forecast-parking').then(r => r.data)

export const fetchAlerts = () =>
  api.get<AlertsResponse>('/predictions/alerts').then(r => r.data)

export const dispararActualizacionModelos = () =>
  api.post<{ mensaje: string; tarea_id: string; estado: string }>('/admin/modelos/actualizar').then(r => r.data)

export const consultarEstadoModelos = () =>
  api.get<ModeloEstadoItem[]>('/admin/modelos/estado').then(r => r.data)

export const dispararReentrenamiento = (_espacioId: number = 1) =>
  dispararActualizacionModelos().then(res => ({
    task_id: res.tarea_id,
    status: res.estado,
    message: res.mensaje,
  }))

