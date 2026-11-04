import axios, { AxiosInstance } from 'axios'

const API_BASE = (import.meta as unknown as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL || '/api/v1'

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 15_000,
})

// Inyector automático de token JWT en cada solicitud saliente
api.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('uct_auth_token') : null
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Manejo centralizado de expiración de sesión (401)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('uct_auth_token')
      window.dispatchEvent(new Event('uct:auth-expired'))
    }
    return Promise.reject(error)
  }
)

export interface DataFilters {
  alcance?: 'conformes' | 'todos' | 'anomalias'
  regimen_horario?: string
  direccion?: string
  dias_semana?: string
  door?: string
  perfil_visita?: string
  marcajes?: string
  sala?: string
  carrera?: string
  facultad?: string
  cohorte?: string
  sector?: string
  tipo_vehiculo?: string
  incluir_pausas_bano?: boolean
  desduplicar_rafagas?: boolean
}

export function parseFilters(filters?: DataFilters | string): DataFilters {
  if (!filters) return {}
  if (typeof filters === 'string') return { alcance: filters as any }
  return filters
}

export interface MonthInfo {
  label: string
  inicio: string
  fin: string
  year: number
  month: number
}

export interface DateBoundsResponse {
  fecha_min: string
  fecha_max: string
  espacio_id?: number
  meses_disponibles: MonthInfo[]
}

export const fetchDateBounds = (espacioId?: number) =>
  api.get<DateBoundsResponse>('/metrics/date-bounds', {
    params: { espacio_id: espacioId || undefined },
  }).then(r => r.data)

export interface HourlyFlowPoint {
  bucket: string
  ingresos: number
  salidas: number
  personas_unicas?: number
  personas_sala1?: number
  personas_sala2?: number
  ingresos_sala1?: number
  ingresos_sala2?: number
  entradas?: number
  lecturas_fallidas?: number
  vehiculos_presentes?: number
}

export interface KPISummary {
  dias_operativos: number
  horas_estudiante: number
  recurrencia_mensual: number
  hora_pico_ingreso: string
  pico_concurrente: number
  mes_referencia?: string
  periodo_label?: string
  carrera_mas_concurrida?: string
  sector_mas_concurrido?: string
  asistencia_total?: number
  promedio_diario_asistencia?: number
  pico_maximo_asistencia?: number
  permanencia_promedio_min?: number
  vehiculos_total?: number
  promedio_diario_vehiculos?: number
  pico_maximo_vehiculos?: number
}

export const fetchKpiSummary = (
  espacioId: number = 1,
  fechaInicio?: string,
  fechaFin?: string,
  filters?: DataFilters | string
) => {
  const f: Record<string, any> = typeof filters === 'object' && filters !== null ? filters : {}
  return api.get<KPISummary>('/metrics/kpi-summary', {
    params: {
      espacio_id: espacioId,
      fecha_inicio: fechaInicio || undefined,
      fecha_fin: fechaFin || undefined,
      alcance: f.alcance,
      regimen_horario: f.regimen_horario,
      direccion: f.direccion,
      dias_semana: f.dias_semana,
      door: f.door,
      perfil_visita: f.perfil_visita,
      marcajes: f.marcajes,
      sala: f.sala,
      carrera: f.carrera,
      facultad: f.facultad,
      cohorte: f.cohorte,
      incluir_pausas_bano: f.incluir_pausas_bano !== undefined ? f.incluir_pausas_bano : undefined,
      desduplicar_rafagas: f.desduplicar_rafagas !== undefined ? f.desduplicar_rafagas : undefined,
    },
  }).then(r => r.data)
}
