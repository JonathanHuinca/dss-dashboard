import { api, DataFilters, HourlyFlowPoint, parseFilters } from './clienteBase'

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

export interface HeatmapPoint {
  dia_semana: number
  dia_nombre: string
  hora: number
  ingresos_promedio: number
  es_nocturno?: boolean
}

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
  cod_in?: string
  id_in?: string
  cod_out?: string
  id_out?: string
  sala?: string
  tipo_acceso?: 'Principal' | 'Universal' | string
}

export interface SalaBibliotecaItem {
  id: number
  codigo: string
  nombre: string
  edificio: string
  piso: string
  descripcion?: string
  capacidad_asientos: number
  permite_horario_extendido: boolean
  horario_extendido_examenes?: boolean
  puerta_principal_in?: string
  puerta_principal_out?: string
  puerta_universal_in?: string
  puerta_universal_out?: string
  hardware_entrada_principal?: string
  hardware_salida_principal?: string
  hardware_entrada_universal?: string
  hardware_salida_universal?: string
  activo: boolean
}

export interface RoomComparisonItem {
  sala: string
  total_marcajes: number
  usuarios_unicos: number
  entradas: number
  salidas: number
  porcentaje_afluencia: number
  capacidad_asientos: number
  edificio: string
  permite_24h_examenes: boolean
}

export interface RoomComparisonResponse {
  resumen_salas: RoomComparisonItem[]
  flujo_horario_comparado: Array<{ hora: string; hora_num: number; entradas_sala1: number; entradas_sala2: number }>
  total_global: number
}

export interface DailyAverageItem {
  dia_num: number
  dia_nombre: string
  dia_corto: string
  dias_muestreados: number
  promedio_entradas_total: number
  promedio_entradas_sala1: number
  promedio_entradas_sala2: number
  total_entradas_acumuladas: number
  ocupacion_relativa_sala1_pct: number
  ocupacion_relativa_sala2_pct: number
}

export interface DailyAverageResponse {
  dias: DailyAverageItem[]
  resumen: {
    dia_mayor_afluencia: string
    pico_promedio_diario: number
    sala1_capacidad: number
    sala2_capacidad: number
    total_dias_evaluados: number
  }
}

export interface CurricularDistributionResponse {
  total_estudiantes_catalogados: number
  total_eventos_asistencia?: number
  total_estudiantes_asistentes?: number
  carreras: Array<{
    carrera: string
    facultad: string
    total_estudiantes: number
    estudiantes_asistentes?: number
    eventos_asistencia?: number
    porcentaje: number
    porcentaje_eventos?: number
    porcentaje_asistentes?: number
  }>
  facultades: Array<{
    facultad: string
    total_estudiantes: number
    estudiantes_asistentes?: number
    eventos_asistencia?: number
    porcentaje: number
    porcentaje_eventos?: number
    porcentaje_asistentes?: number
  }>
  cohortes?: Array<{
    cohorte: number
    etiqueta: string
    total_estudiantes: number
    estudiantes_asistentes?: number
    eventos_asistencia: number
    porcentaje_estudiantes: number
    porcentaje_eventos: number
    porcentaje_asistentes?: number
  }>
  estamentos?: Array<{ estamento: string; total: number }>
}

export interface AvailableFiltersResponse {
  salas: SalaBibliotecaItem[]
  facultades: string[]
  carreras: string[]
  cohortes?: number[]
}

export interface CheckinDistributionPoint {
  marcajes: string
  total_registros: number
  porcentaje: number
}

export interface VisitProfileDonutItem {
  perfil: string
  total: number
  porcentaje: number
  promedio_min: number
  color: string
  descripcion: string
}

export interface VisitProfilesDonutResponse {
  items: VisitProfileDonutItem[]
  total_visitas_analizadas: number
  tasa_rebote_pct: number
  entradas_sin_salida: number
  salidas_sin_entrada: number
  total_no_analizados: number
  total_eventos: number
}

export interface RawAttendanceItem {
  time: string
  person_id_hash: string
  person_id_short: string
  door_entrada: string
  door_salida: string
  primera_entrada: string
  ultima_salida: string
  permanencia_min: number
  marcajes_totales: number
  salida_imputada: boolean
  entrada_imputada?: boolean
  alerta_coherencia_fechas?: boolean
  categorias: string[]
  nivel_integridad: 'conforme' | 'observado' | 'critico'
}

export interface RawAttendanceResponse {
  items: RawAttendanceItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// ─── Funciones API Asistencia ──────────────────────────────────────────────────

export const fetchAttendanceKpis = (fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string) => {
  const f = parseFilters(filters)
  return api.get<AttendanceKpis>('/attendance/kpis', {
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
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

export const fetchOccupancyRealtime = () =>
  api.get<OccupancyRealtime>('/attendance/occupancy-realtime').then(r => r.data)

export const fetchAttendanceHourlyFlow = (fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string) => {
  const f = parseFilters(filters)
  return api.get<HourlyFlowPoint[]>('/attendance/hourly-flow', {
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
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

export const fetchHeatmap = (
  fechaInicio?: string,
  fechaFin?: string,
  espacioId: number = 1,
  filters?: DataFilters | string,
) => {
  const f = parseFilters(filters)
  return api.get<HeatmapPoint[]>('/attendance/heatmap', {
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

export const fetchPeakValley = (fechaInicio?: string, fechaFin?: string) =>
  api.get<PeakValleyPoint[]>('/attendance/peak-valley', { params: { fecha_inicio: fechaInicio, fecha_fin: fechaFin } }).then(r => r.data)

export const fetchWeeklyEvolution = (
  fechaInicio?: string,
  fechaFin?: string,
  espacioId: number = 1,
  filters?: DataFilters | string,
) => {
  const f = parseFilters(filters)
  return api.get<WeeklyEvolutionPoint[]>('/attendance/weekly-evolution', {
    params: {
      espacio_id: espacioId,
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
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

export const fetchMonthlyVolume = (
  fechaInicio?: string,
  fechaFin?: string,
  espacioId: number = 1,
  filters?: DataFilters | string,
) => {
  const f = parseFilters(filters)
  return api.get<MonthlyVolumePoint[]>('/attendance/monthly-volume', {
    params: {
      espacio_id: espacioId,
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
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

export const fetchAcademicMilestones = (
  fechaInicio?: string,
  fechaFin?: string,
  espacioId: number = 1,
  filters?: DataFilters | string,
) => {
  const f = parseFilters(filters)
  return api.get<AcademicMilestonePoint[]>('/attendance/academic-milestones-comparison', {
    params: {
      espacio_id: espacioId,
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
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

export const fetchDoorsUsage = (fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string) => {
  const f = parseFilters(filters)
  return api.get<DoorUsagePoint[]>('/attendance/doors-usage', {
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
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
      incluir_pausas_bano: f.incluir_pausas_bano !== undefined ? f.incluir_pausas_bano : undefined,
      desduplicar_rafagas: f.desduplicar_rafagas !== undefined ? f.desduplicar_rafagas : undefined,
    },
  }).then(r => r.data)
}

export const fetchSalasBiblioteca = (espacioId: number = 1) =>
  api.get<SalaBibliotecaItem[]>('/attendance/salas', { params: { espacio_id: espacioId } }).then(r => r.data)

export const createSalaBiblioteca = (payload: Partial<SalaBibliotecaItem>) =>
  api.post<SalaBibliotecaItem>('/attendance/salas', payload).then(r => r.data)

export const updateSalaCapacidad = (salaId: number, capacidad: number) =>
  api.put<{
    sala_id: number
    codigo: string
    nombre: string
    capacidad_asientos: number
    espacio_id: number
    capacidad_total_espacio: number
  }>(`/attendance/salas/${salaId}/capacidad`, { capacidad_asientos: capacidad }).then(r => r.data)

export const fetchRoomsComparison = (
  fechaInicio?: string,
  fechaFin?: string,
  filters?: DataFilters | string,
  espacioId: number = 1,
) => {
  const f = parseFilters(filters)
  return api.get<RoomComparisonResponse>('/attendance/rooms-comparison', {
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
      alcance: f.alcance || 'todos',
      regimen_horario: f.regimen_horario,
      direccion: f.direccion,
      dias_semana: f.dias_semana,
      door: f.door,
      marcajes: f.marcajes,
      carrera: f.carrera,
      facultad: f.facultad,
      cohorte: f.cohorte,
      espacio_id: espacioId,
    },
  }).then(r => r.data)
}

export const fetchDailyAverageAttendance = (
  fechaInicio?: string,
  fechaFin?: string,
  filters?: DataFilters | string,
  espacioId: number = 1,
) => {
  const f = parseFilters(filters)
  return api.get<DailyAverageResponse>('/attendance/daily-average', {
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
      alcance: f.alcance || 'todos',
      regimen_horario: f.regimen_horario,
      direccion: f.direccion,
      dias_semana: f.dias_semana,
      door: f.door,
      marcajes: f.marcajes,
      carrera: f.carrera,
      facultad: f.facultad,
      cohorte: f.cohorte,
      espacio_id: espacioId,
    },
  }).then(r => r.data)
}

export const fetchCurricularDistribution = (
  fechaInicio?: string,
  fechaFin?: string,
  filters?: DataFilters | string,
  espacioId: number = 1,
) => {
  const f = parseFilters(filters)
  return api.get<CurricularDistributionResponse>('/attendance/curricular-distribution', {
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
      alcance: f.alcance || 'todos',
      regimen_horario: f.regimen_horario,
      direccion: f.direccion,
      dias_semana: f.dias_semana,
      door: f.door,
      marcajes: f.marcajes,
      carrera: f.carrera,
      facultad: f.facultad,
      cohorte: f.cohorte,
      espacio_id: espacioId,
    },
  }).then(r => r.data)
}

export const fetchAvailableFilters = (espacioId: number = 1) =>
  api.get<AvailableFiltersResponse>('/attendance/available-filters', { params: { espacio_id: espacioId } }).then(r => r.data)

export const fetchCheckinsDistribution = (fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string) => {
  const f = parseFilters(filters)
  return api.get<CheckinDistributionPoint[]>('/attendance/checkins-distribution', {
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
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

export const fetchVisitProfilesDonut = (
  fechaInicio?: string,
  fechaFin?: string,
  filters?: DataFilters | string,
  espacioId: number = 1,
) => {
  const f = parseFilters(filters)
  return api.get<VisitProfilesDonutResponse>('/attendance/visit-profiles-donut', {
    params: {
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
      alcance: f.alcance || 'todos',
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
      espacio_id: espacioId,
    },
  }).then(r => r.data)
}

export const fetchRawAttendance = (params: {
  page?: number
  pageSize?: number
  fechaInicio?: string
  fechaFin?: string
  door?: string
  searchHash?: string
  categoria?: string
  alcance?: string
  regimenHorario?: string
  direccion?: string
  diasSemana?: string
  perfilVisita?: string
  marcajes?: string
  incluirPausasBano?: boolean
  desduplicarRafagas?: boolean
}) =>
  api.get<RawAttendanceResponse>('/attendance/raw-events', {
    params: {
      page: params.page || 1,
      page_size: params.pageSize || 50,
      fecha_inicio: params.fechaInicio || undefined,
      fecha_fin: params.fechaFin || undefined,
      door: params.door || undefined,
      search_hash: params.searchHash || undefined,
      categoria: params.categoria || undefined,
      alcance: params.alcance || undefined,
      regimen_horario: params.regimenHorario || undefined,
      direccion: params.direccion || undefined,
      dias_semana: params.diasSemana || undefined,
      perfil_visita: params.perfilVisita || undefined,
      marcajes: params.marcajes || undefined,
      incluir_pausas_bano: params.incluirPausasBano !== undefined ? params.incluirPausasBano : undefined,
      desduplicar_rafagas: params.desduplicarRafagas !== undefined ? params.desduplicarRafagas : undefined,
    },
  }).then(r => r.data)

export interface Campana24hInfo {
  id: number | null
  descripcion: string
  subespacio: string
  subespacio_label: string
  capacidad_asientos: number
  fecha_inicio: string | null
  fecha_fin: string | null
  tiene_campana_activa?: boolean
}

export interface CampanaItem {
  id: number
  descripcion: string
  fecha_inicio: string | null
  fecha_fin: string | null
  subespacio: string
}

export interface KpisComparativa24h {
  ingresos_diurnos: number
  ingresos_nocturnos: number
  total_ingresos: number
  porcentaje_delta_24h: number
  estudiantes_nocturnos_unicos: number
  estudiantes_remanentes_vespertinos?: number
  estudiantes_totales_unicos: number
  horas_estudio_nocturnas: number
  permanencia_promedio_nocturna_min: number
  permanencia_promedio_diurna_min: number
}

export interface PicoNocturno24h {
  aforo_maximo: number
  hora_pico: string
  tasa_ocupacion_asientos_pct: number
}

export interface FaseMadrugada24h {
  fase: string
  ingresos: number
  porcentaje: number
}

export interface TopCurricular24h {
  carrera?: string
  facultad?: string
  visitas: number
  estudiantes: number
  porcentaje: number
}

export interface CurvaNocturnaItem {
  hora: string
  hora_num: number
  ingresos: number
}

export interface DiaSemanaNocturnoItem {
  dia: string
  dia_num: number
  ingresos: number
  estudiantes: number
  porcentaje: number
}

export interface ComparativaCampanaItem {
  id: number
  descripcion: string
  fecha_inicio: string
  fecha_fin: string
  ingresos_nocturnos: number
  ingresos_diurnos: number
  total_ingresos: number
  porcentaje_delta_24h: number
  estudiantes_nocturnos_unicos: number
  horas_estudio_nocturnas: number
}

export interface MapaCalorSemanaItem {
  id: string
  label: string
  fecha_inicio: string | null
  fecha_fin: string | null
}

export interface MapaCalor24h {
  semanas_disponibles: MapaCalorSemanaItem[]
  matriz_por_semana: Record<string, HeatmapPoint[]>
}

export interface Analisis24hResponse {
  campana: Campana24hInfo
  campanas_disponibles: CampanaItem[]
  bloque_horario_activo?: string
  bloque_horario_label?: string
  kpis_comparativa: KpisComparativa24h
  pico_nocturno: PicoNocturno24h
  fases_madrugada: FaseMadrugada24h[]
  top_carreras: TopCurricular24h[]
  top_facultades: TopCurricular24h[]
  curva_nocturna: CurvaNocturnaItem[]
  dias_semana_nocturno: DiaSemanaNocturnoItem[]
  comparativa_campanas: ComparativaCampanaItem[]
  mapa_calor: MapaCalor24h
}

export const fetchAnalisis24h = (params?: {
  espacioId?: number
  campanaId?: number
  fechaInicio?: string
  fechaFin?: string
  bloqueHorario?: 'todos' | 'lunes_jueves' | 'viernes'
}) =>
  api.get<Analisis24hResponse>('/attendance/analisis-24h', {
    params: {
      espacio_id: params?.espacioId ?? 1,
      campana_id: params?.campanaId !== undefined ? params.campanaId : undefined,
      fecha_inicio: params?.fechaInicio || undefined,
      fecha_fin: params?.fechaFin || undefined,
      bloque_horario: params?.bloqueHorario || 'todos',
    },
  }).then(r => r.data)

