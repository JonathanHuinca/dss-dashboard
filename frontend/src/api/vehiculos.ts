import { api, DataFilters, HourlyFlowPoint, parseFilters } from './clienteBase'

export interface VehicleKpis {
  vehiculos_unicos: number
  total_accesos: number
  total_salidas?: number
  dias_operativos: number
  turnover_rate_diario: number
  permanencia_mediana_min: number
  tasa_lectura_fallida_pct: number
  hora_punta?: string
  max_aforo_historico?: number
  capacidad_calibrada?: number
}

export interface ParkingOccupancy {
  vehiculos_presentes: number
  plazas_disponibles: number
  capacidad_maxima: number
  ocupacion_pct: number
  nivel_alerta: 'normal' | 'preventivo' | 'saturacion'
  timestamp: string
  sector?: string
}

export interface FleetItem {
  tipo?: string
  marca?: string
  total: number
  pct: number
}

export interface FleetComposition {
  por_tipo: FleetItem[]
  por_marca: FleetItem[]
}

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

export interface RawVehicleItem {
  time: string
  patente_hash: string
  patente_short: string
  camara: string
  direccion: string
  tipo_vehiculo: string
  marca: string
  color: string
  calidad_lectura: string
  categorias: string[]
  nivel_integridad: 'conforme' | 'observado' | 'critico'
}

export interface RawVehicleResponse {
  items: RawVehicleItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface SectorEstacionamiento {
  id: number
  codigo: string
  nombre: string
  capacidad_max: number
  camaras_entrada: string
  camaras_salida: string
  activo: boolean
}

// ─── Funciones API Vehículos ───────────────────────────────────────────────────

export const fetchVehicleKpis = (
  fechaInicio?: string,
  fechaFin?: string,
  filters?: DataFilters | string,
  sector?: string,
  signal?: AbortSignal,
) => {
  const f = parseFilters(filters)
  const sectorParam = sector && sector !== 'todos' ? sector : f.sector && f.sector !== 'todos' ? f.sector : undefined
  const tipoVehiculoParam = (f as any).tipo_vehiculo && (f as any).tipo_vehiculo !== 'todos' ? (f as any).tipo_vehiculo : undefined
  return api.get<VehicleKpis>('/vehicles/kpis', { signal,
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
      alcance: f.alcance,
      regimen_horario: f.regimen_horario,
      direccion: f.direccion,
      dias_semana: f.dias_semana,
      door: f.door,
      sector: sectorParam,
      tipo_vehiculo: tipoVehiculoParam,
    },
  }).then(r => r.data)
}

export const fetchParkingOccupancy = (sector?: string, signal?: AbortSignal) =>
  api.get<ParkingOccupancy>('/vehicles/parking-occupancy', { signal,
    params: {
      sector: sector && sector !== 'todos' ? sector : undefined,
    },
  }).then(r => r.data)

export const fetchVehicleHourlyFlow = (
  fechaInicio?: string,
  fechaFin?: string,
  filters?: DataFilters | string,
  sector?: string,
  signal?: AbortSignal,
) => {
  const f = parseFilters(filters)
  const sectorParam = sector && sector !== 'todos' ? sector : f.sector && f.sector !== 'todos' ? f.sector : undefined
  const tipoVehiculoParam = (f as any).tipo_vehiculo && (f as any).tipo_vehiculo !== 'todos' ? (f as any).tipo_vehiculo : undefined
  return api.get<HourlyFlowPoint[]>('/vehicles/hourly-flow', { signal,
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
      alcance: f.alcance,
      regimen_horario: f.regimen_horario,
      direccion: f.direccion,
      dias_semana: f.dias_semana,
      door: f.door,
      sector: sectorParam,
      tipo_vehiculo: tipoVehiculoParam,
    },
  }).then(r => r.data)
}

export const fetchFleetComposition = (fechaInicio?: string, fechaFin?: string, sector?: string, signal?: AbortSignal) =>
  api.get<FleetComposition>('/vehicles/fleet-composition', { signal,
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
      sector: sector && sector !== 'todos' ? sector : undefined,
    },
  }).then(r => r.data)

export const fetchCameraStats = (fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string, sector?: string, signal?: AbortSignal) => {
  const f = parseFilters(filters)
  const sectorParam = sector && sector !== 'todos' ? sector : f.sector && f.sector !== 'todos' ? f.sector : undefined
  const tipoVehiculoParam = (f as any).tipo_vehiculo && (f as any).tipo_vehiculo !== 'todos' ? (f as any).tipo_vehiculo : undefined
  return api.get<CameraStatPoint[]>('/vehicles/camera-stats', { signal,
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
      alcance: f.alcance,
      regimen_horario: f.regimen_horario,
      direccion: f.direccion,
      dias_semana: f.dias_semana,
      door: f.door,
      sector: sectorParam,
      tipo_vehiculo: tipoVehiculoParam,
    },
  }).then(r => r.data)
}

export const fetchVehicleDailyEvolution = (fechaInicio?: string, fechaFin?: string, sector?: string, signal?: AbortSignal) =>
  api.get<VehicleDailyPoint[]>('/vehicles/daily-evolution', { signal,
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
      sector: sector && sector !== 'todos' ? sector : undefined,
    },
  }).then(r => r.data)

export const fetchVehicleAcademicMilestones = (signal?: AbortSignal) =>
  api.get<any[]>('/vehicles/academic-milestones-comparison', { signal }).then(r => r.data)

export const fetchIntercampusMobility = (signal?: AbortSignal) =>
  api.get<IntercampusMobilityResponse>('/vehicles/intercampus-mobility', { signal }).then(r => r.data)

export const fetchBehavioralClusters = (signal?: AbortSignal) =>
  api.get<BehavioralClustersResponse>('/vehicles/behavioral-clusters', { signal }).then(r => r.data)

export const fetchRawVehicles = (params: {
  page?: number
  pageSize?: number
  fechaInicio?: string
  fechaFin?: string
  camara?: string
  direccion?: string
  tipoVehiculo?: string
  searchHash?: string
  categoria?: string
  alcance?: string
  regimenHorario?: string
  diasSemana?: string
  door?: string
}) =>
  api.get<RawVehicleResponse>('/vehicles/raw-events', {
    params: {
      page: params.page || 1,
      page_size: params.pageSize || 50,
      fecha_inicio: params.fechaInicio || undefined,
      fecha_fin: params.fechaFin || undefined,
      camara: params.camara || undefined,
      direccion: params.direccion || undefined,
      tipo_vehiculo: params.tipoVehiculo || undefined,
      search_hash: params.searchHash || undefined,
      categoria: params.categoria || undefined,
      alcance: params.alcance || undefined,
      regimen_horario: params.regimenHorario || undefined,
      dias_semana: params.diasSemana || undefined,
      door: params.door || undefined,
    },
  }).then(r => r.data)

export const fetchSectoresEstacionamiento = () =>
  api.get<SectorEstacionamiento[]>('/admin/estacionamientos/sectores').then(r => r.data)
