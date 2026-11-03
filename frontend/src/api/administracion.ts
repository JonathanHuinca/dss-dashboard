import { api } from './clienteBase'

// ─── Tareas Programadas y Planificador ─────────────────────────────────────────

export interface EjecucionTareaDetalle {
  id: number | string
  tarea?: string
  tarea_nombre?: string
  disparador?: string
  origen?: string
  estado: string
  inicio?: string
  inicio_en?: string
  iniciado_en?: string
  fin?: string
  fin_en?: string
  finalizado_en?: string
  duracion_segundos?: number
  memoria_pico_mb?: number
  filas_afectadas?: number
  error?: string
  error_detalle?: string
  resumen_json?: string
}

export interface TareaItem {
  nombre: string
  descripcion?: string
  cron_expresion?: string
  en_curso: boolean
  proxima_ejecucion?: string | null
  ultima_ejecucion?: EjecucionTareaDetalle | null
}

export interface ResumenTareasAdmin {
  catalogo: TareaItem[]
  ultimas_ejecuciones: EjecucionTareaDetalle[]
  planificador_activo: boolean
}

export const consultarResumenTareasAdmin = () =>
  api.get<ResumenTareasAdmin>('/admin/tareas').then(r => r.data)

export const ejecutarTareaAdmin = (nombre: string) =>
  api.post(`/admin/tareas/${encodeURIComponent(nombre)}/ejecutar`).then(r => r.data)

// ─── Smart Campus UCT e Ingesta Directa ────────────────────────────────────────

export interface SincronizacionFuenteItem {
  id: number
  fuente: 'torniquetes' | 'estacionamientos' | string
  espacio_id: number
  ultima_fecha_sincronizada?: string | null
  ultima_ejecucion_en?: string | null
  filas_leidas: number
  filas_insertadas: number
  filas_duplicadas: number
  estado: 'completado' | 'error' | 'en_proceso' | string
  ultimo_error?: string | null
}

export interface EstadoSmartCampusResumen {
  fuentes: SincronizacionFuenteItem[]
  sectores_estacionamiento: SectorEstacionamientoAdmin[]
  servidor_activo: boolean
}

export interface SectorEstacionamientoAdmin {
  id: number
  espacio_id: number
  codigo: string
  nombre: string
  capacidad_max: number
  camaras_entrada: string
  camaras_salida: string
  activo: boolean
}

export const obtenerEstadoSmartCampus = () =>
  api.get<EstadoSmartCampusResumen>('/admin/smart-campus/estado').then(r => r.data)

export const sincronizarSmartCampusManual = (payload: { fuente?: string; desde?: string; hasta?: string }) =>
  api.post<{ status: string; mensaje: string; resultado?: any }>('/admin/smart-campus/sincronizar', payload).then(r => r.data)

export const obtenerSectoresEstacionamientoAdmin = () =>
  api.get<SectorEstacionamientoAdmin[]>('/admin/estacionamientos/sectores').then(r => r.data)

export const actualizarCapacidadSectorAdmin = (codigo: string, capacidad_max: number) =>
  api.put<{ mensaje: string; codigo: string; capacidad_max: number }>(`/admin/estacionamientos/sectores/${codigo}`, { capacidad_max }).then(r => r.data)

// ─── Gestión de Caché de Rendimiento ──────────────────────────────────────────

export interface StatsCache {
  aforo_vivo_items: number
  kpis_dia_items: number
  historicos_items: number
  general_items: number
  total_items: number
}

export const limpiarCacheAdmin = (espacio_id?: number) =>
  api.post<{ mensaje: string; entradas_eliminadas: number; espacio_id?: number }>('/admin/cache/limpiar', {}, {
    params: { espacio_id: espacio_id || undefined },
  }).then(r => r.data)

export const obtenerStatsCacheAdmin = () =>
  api.get<StatsCache>('/admin/cache/stats').then(r => r.data)

// ─── Espacios Físicos ──────────────────────────────────────────────────────────

export interface EspacioInfo {
  id: number
  campus: string
  tipo: 'biblioteca' | 'estacionamiento' | string
  nombre: string
  capacidad_max: number
  activo: boolean
}

export const fetchEspacios = () =>
  api.get<EspacioInfo[]>('/config/espacios').then(r => r.data)

export const fetchEspacioInfo = (espacioId: number) =>
  api.get<EspacioInfo>(`/config/espacios/${espacioId}`).then(r => r.data)

export const updateEspacioCapacidad = (espacioId: number, capacidad_max: number) =>
  api.put<EspacioInfo>(`/config/espacios/${espacioId}/capacidad`, { capacidad_max }).then(r => r.data)

// ─── Horarios de Operación ─────────────────────────────────────────────────────

export interface DiaHorario {
  abierto: boolean
  apertura: string
  cierre: string
  cierre_dia_siguiente?: boolean
}

export type ConfiguracionSemanal = {
  lunes: DiaHorario
  martes: DiaHorario
  miercoles: DiaHorario
  jueves: DiaHorario
  viernes: DiaHorario
  sabado: DiaHorario
  domingo: DiaHorario
}

export interface HorarioOperacion {
  id: number
  espacio_id: number
  anio: number
  descripcion: string
  tipo_horario?: string
  fecha_inicio: string | null
  fecha_fin: string | null
  hora_apertura: string
  hora_cierre: string
  cierre_dia_siguiente: boolean
  es_continuo_24h: boolean
  configuracion_dias?: Record<string, DiaHorario> | null
  subespacio?: string | null
  activo: boolean
  updated_at?: string
}

export interface HorarioOperacionCreate {
  espacio_id: number
  anio: number
  descripcion: string
  tipo_horario?: string
  fecha_inicio?: string | null
  fecha_fin?: string | null
  hora_apertura: string
  hora_cierre: string
  cierre_dia_siguiente?: boolean
  es_continuo_24h?: boolean
  configuracion_dias?: Record<string, DiaHorario> | null
  subespacio?: string | null
  activo?: boolean
}

export const fetchHorarios = (params?: { espacio_id?: number; anio?: number; subespacio?: string }) =>
  api.get<HorarioOperacion[]>('/config/horarios', { params }).then(r => r.data)

export const createHorario = (data: HorarioOperacionCreate) =>
  api.post<HorarioOperacion>('/config/horarios', data).then(r => r.data)

export const updateHorario = (id: number, data: Partial<HorarioOperacionCreate>) =>
  api.put<HorarioOperacion>(`/config/horarios/${id}`, data).then(r => r.data)

export const deleteHorario = (id: number) =>
  api.delete(`/config/horarios/${id}`).then(r => r.data)

// ─── Calendario Académico y Contingencias ──────────────────────────────────────

export interface CalendarStatusResponse {
  total_dias: number
  total_feriados: number
  total_recesos: number
  total_suspensiones: number
  total_examenes: number
  total_paros_federados?: number
  total_paros_carrera?: number
  fecha_min: string | null
  fecha_max: string | null
  fuente_oficial: string
}

export const fetchCalendarStatus = () =>
  api.get<CalendarStatusResponse>('/config/calendar/status').then(r => r.data)

export const syncCalendarScrape = () =>
  api.post<{ status: string; total_days: number }>('/config/calendar/sync-scrape').then(r => r.data)

export interface ContingenciaAcademica {
  id: number
  fecha_inicio: string
  fecha_fin: string
  tipo: 'paro_federado' | 'paro_carrera' | 'toma_campus' | 'climatica' | 'duelo' | 'suspension_sala' | 'otro'
  titulo: string
  descripcion?: string | null
  espacio_id?: number | null
  subespacio?: string | null
  hora_inicio?: string | null
  hora_fin?: string | null
  carreras_afectadas?: string | null
  implica_cierre_total: boolean
  creado_en?: string
}

export interface ContingenciaCrear {
  fecha_inicio: string
  fecha_fin: string
  tipo: string
  titulo: string
  descripcion?: string | null
  espacio_id?: number | null
  subespacio?: string | null
  hora_inicio?: string | null
  hora_fin?: string | null
  carreras_afectadas?: string | null
  implica_cierre_total: boolean
}

export interface DiaCalendarioResumen {
  fecha: string
  tipo_dia: 'operativo' | 'feriado' | 'receso' | 'paro_federado' | 'paro_carrera' | 'suspension' | 'examen' | 'clases'
  es_cierre: boolean
  es_paro: boolean
  is_holiday: boolean
  is_break: boolean
  is_exam_period: boolean
  is_class_milestone?: boolean
  is_strike_federado: boolean
  is_strike_carrera: boolean
  suspension_actividades: boolean
  subespacios_suspendidos?: string[]
  espacios_suspendidos?: number[]
  descripcion?: string | null
}

export interface EventoCalendarioDetalle extends DiaCalendarioResumen {
  fecha_inicio?: string
  fecha_fin?: string
  dias_totales?: number
  is_class_milestone?: boolean
  fuente?: string
}

export const obtenerContingencias = (anio?: number) =>
  api.get<ContingenciaAcademica[]>('/config/contingencias', { params: { anio } }).then(r => r.data)

export const crearContingencia = (data: ContingenciaCrear) =>
  api.post<ContingenciaAcademica>('/config/contingencias', data).then(r => r.data)

export const eliminarContingencia = (id: number) =>
  api.delete<{ detail: string }>(`/config/contingencias/${id}`).then(r => r.data)

export const obtenerResumenAnualCalendario = (anio: number = 2026) =>
  api.get<DiaCalendarioResumen[]>('/config/calendar/resumen-anual', { params: { anio } }).then(r => r.data)

export const fetchCalendarEvents = (params?: {
  anio?: number
  categoria?: string
  busqueda?: string
  agrupar_periodos?: boolean
}) => api.get<EventoCalendarioDetalle[]>('/config/calendar/events', { params }).then(r => r.data)

export const depurarCalendarBasura = () =>
  api.post<{ registros_eliminados: number; mensaje: string }>('/config/calendar/depurar').then(r => r.data)

export interface EventoCalendarioFormulario {
  descripcion: string
  is_holiday: boolean
  is_break: boolean
  is_exam_period: boolean
  is_class_milestone: boolean
  suspension_actividades: boolean
  is_strike_federado?: boolean
  is_strike_carrera?: boolean
  tipo_contingencia?: string | null
}

export interface EventoCalendarioCrearFormulario extends EventoCalendarioFormulario {
  fecha_inicio: string
  fecha_fin?: string | null
}

export const actualizarEventoCalendario = (fecha: string, datos: EventoCalendarioFormulario) =>
  api.put<{ mensaje: string; fecha: string; descripcion: string; fuente: string }>(`/config/calendar/events/${fecha}`, datos).then(r => r.data)

export const crearEventoCalendario = (datos: EventoCalendarioCrearFormulario) =>
  api.post<{ mensaje: string; dias_creados: number }>('/config/calendar/events', datos).then(r => r.data)

export const eliminarEventoCalendario = (fecha: string) =>
  api.delete<{ mensaje: string }>(`/config/calendar/events/${fecha}`).then(r => r.data)

// ─── Ingesta de Respaldo por Archivos ──────────────────────────────────────────

export interface SchemaFieldMapping {
  target_field: string
  matched_column: string | null
  status: 'verde' | 'amarillo' | 'rojo'
  required: boolean
  description: string
  classification: 'analitico' | 'seudonimizar' | 'purgar'
}

export interface InspectResponse {
  filename: string
  tipo: string
  espacio_id: number
  header_row_index: number
  total_rows_estimated: number
  columns_detected: string[]
  schema_mapping: SchemaFieldMapping[]
  preview_rows: Record<string, any>[]
  all_required_matched: boolean
  missing_required_fields: string[]
}

export interface PreviousJobInfo {
  job_id: string
  filename: string
  estado: string
  fecha: string | null
  registros_ok: number
}

export interface ValidationResponse {
  file_hash: string
  fecha_min: string | null
  fecha_max: string | null
  total_filas: number
  existe_colision: boolean
  registros_existentes: number
  clave_enlace_detectada: 'rut' | 'matricula' | 'crosswalk' | 'ninguna'
  porcentaje_coincidencia_carreras: number
  detalles_colision: string
  hash_ya_procesado: boolean
  trabajo_previo: PreviousJobInfo | null
}

export interface ProcessPayload {
  file: File
  tipo: string
  espacio_id: number
  modo_solapamiento: 'merge' | 'overwrite'
  clave_enlace: 'rut' | 'matricula' | 'crosswalk'
  modo_enlace: 'tolerante' | 'mandatorio'
}

export interface ProcessResponse {
  job_id: string
  status: string
  modo_solapamiento: string
  clave_enlace: string
  modo_enlace: string
  registros_procesados: number
  registros_insertados: number
  registros_eliminados: number
  carreras_catalogadas: number
  carreras_no_catalogadas: number
  file_hash: string
  detalle: string
}

export interface IngestionUploadResponse {
  job_id: string
  status: string
  filename: string
  file_hash?: string
  message?: string
}

export interface JobStatusResponse {
  job_id: string
  estado: 'queued' | 'processing' | 'completed' | 'failed'
  registros_ok: number
  registros_error: number
  error_detail?: string | null
}

export interface IngestionHistoryItem {
  job_id: string
  filename: string
  tipo: string
  estado: string
  registros_ok: number
  registros_error: number
  creado_en?: string | null
  completado_en?: string | null
  file_hash?: string | null
  modo_solapamiento?: string | null
  clave_enlace?: string | null
  modo_enlace?: string | null
  espacio_id?: number | null
  error_detail?: string | null
}

export const inspectFile = async (
  file: File,
  tipo: string,
  espacioId: number = 1
): Promise<InspectResponse> => {
  const formData = new FormData()
  formData.append('file', file)
  const res = await api.post<InspectResponse>('/ingestion/inspect', formData, {
    params: { tipo, espacio_id: espacioId },
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180_000,
  })
  return res.data
}

export const validateIngestion = async (
  file: File,
  tipo: string,
  espacioId: number = 1
): Promise<ValidationResponse> => {
  const formData = new FormData()
  formData.append('file', file)
  const res = await api.post<ValidationResponse>('/ingestion/validate', formData, {
    params: { tipo, espacio_id: espacioId },
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300_000,
  })
  return res.data
}

export const processIngestion = async (
  payload: ProcessPayload
): Promise<ProcessResponse> => {
  const formData = new FormData()
  formData.append('file', payload.file)
  const res = await api.post<ProcessResponse>('/ingestion/process', formData, {
    params: {
      tipo: payload.tipo,
      espacio_id: payload.espacio_id,
      modo_solapamiento: payload.modo_solapamiento,
      clave_enlace: payload.clave_enlace,
      modo_enlace: payload.modo_enlace,
    },
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600_000,
  })
  return res.data
}

export const uploadIngestion = async (
  payload: ProcessPayload
): Promise<IngestionUploadResponse> => {
  const formData = new FormData()
  formData.append('file', payload.file)
  const res = await api.post<IngestionUploadResponse>('/ingestion/upload', formData, {
    params: {
      tipo: payload.tipo,
      espacio_id: payload.espacio_id,
      modo_solapamiento: payload.modo_solapamiento,
      clave_enlace: payload.clave_enlace,
      modo_enlace: payload.modo_enlace,
    },
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300_000,
  })
  return res.data
}

export const fetchJobStatus = async (jobId: string): Promise<JobStatusResponse> => {
  const res = await api.get<JobStatusResponse>(`/ingestion/${jobId}/status`)
  return res.data
}

export const fetchIngestionHistory = async (): Promise<IngestionHistoryItem[]> => {
  const res = await api.get<IngestionHistoryItem[]>('/ingestion/history')
  return res.data
}

// ─── Usuarios, Autenticación y Activación ─────────────────────────────────────

export interface TokenVerifyData {
  es_valido: boolean
  email: string
  nombre_completo: string
  expira_en: string
  tipo_token: string
}

export interface ActivateAccountPayload {
  token: string
  nueva_password: string
  confirmar_password: string
}

export interface ActivateAccountResponse {
  mensaje: string
  email: string
  exito: boolean
}

export interface InviteUserPayload {
  email: string
  nombre_completo: string
  roles?: string[]
  allowed_datasets?: string[]
  can_use_ai?: boolean
  can_export?: boolean
  can_ingest?: boolean
  espacio_id?: number | null
}

export interface InviteUserResponse {
  usuario: {
    id: number
    email: string
    nombre_completo: string
    is_active: boolean
    roles: Array<{ id: number; nombre: string; descripcion?: string }>
  }
  enlace_activacion: string
  token_temporal?: string
  expira_en: string
  mensaje: string
}

export const verifyActivationToken = async (token: string): Promise<TokenVerifyData> => {
  const res = await api.get<TokenVerifyData>('/auth/verify-token', {
    params: { token },
  })
  return res.data
}

export const activateAccount = async (
  payload: ActivateAccountPayload
): Promise<ActivateAccountResponse> => {
  const res = await api.post<ActivateAccountResponse>('/auth/activate', payload)
  return res.data
}

export const inviteUser = async (
  payload: InviteUserPayload
): Promise<InviteUserResponse> => {
  const res = await api.post<InviteUserResponse>('/auth/invite', payload)
  return res.data
}

export interface ForgotPasswordResponse {
  mensaje: string
  enlace_recuperacion?: string
  token_temporal?: string
  expira_en?: string
}

export const forgotPassword = async (email: string): Promise<ForgotPasswordResponse> => {
  const res = await api.post<ForgotPasswordResponse>('/auth/forgot-password', { email })
  return res.data
}

export interface ResetPasswordPayload {
  token: string
  nueva_password: string
  confirmar_password: string
}

export interface ResetPasswordResponse {
  mensaje: string
  email: string
  exito: boolean
}

export const resetPassword = async (payload: ResetPasswordPayload): Promise<ResetPasswordResponse> => {
  const res = await api.post<ResetPasswordResponse>('/auth/reset-password', payload)
  return res.data
}

export const unlockUser = async (userId: number): Promise<{ mensaje: string; user_id: number; desbloqueado: boolean }> => {
  const res = await api.post<{ mensaje: string; user_id: number; desbloqueado: boolean }>(`/auth/users/${userId}/unlock`)
  return res.data
}

export interface DeleteUserResponse {
  mensaje: string
  usuario_id: number
  exito: boolean
}

export const deleteUser = async (userId: number): Promise<DeleteUserResponse> => {
  const res = await api.delete<DeleteUserResponse>(`/auth/users/${userId}`)
  return res.data
}

// ─── Auditoría y Purga de Datos ────────────────────────────────────────────────

export interface DownloadAuditItem {
  id: number
  usuario_id: number | null
  usuario_email: string
  usuario_nombre: string
  modulo: string
  formato: string
  filtro_fecha_inicio: string | null
  filtro_fecha_fin: string | null
  filtro_detalle: string | null
  total_registros: number
  ip_origen: string
  timestamp: string | null
}

export interface DownloadAuditStats {
  total_descargas: number
  descargas_hoy: number
  descargas_csv: number
  descargas_pdf: number
  descargas_por_modulo: Record<string, number>
}

export interface DownloadAuditResponse {
  items: DownloadAuditItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
  stats: DownloadAuditStats
}

export const fetchDownloadAudit = (params?: {
  page?: number
  pageSize?: number
  modulo?: string
  formato?: string
  search?: string
}) =>
  api.get<DownloadAuditResponse>('/admin/download-audit', {
    params: {
      page: params?.page || 1,
      page_size: params?.pageSize || 15,
      modulo: params?.modulo || undefined,
      formato: params?.formato || undefined,
      search: params?.search || undefined,
    },
  }).then(r => r.data)

export const recordDownloadAudit = (data: {
  modulo: string
  formato: string
  filtro_fecha_inicio?: string
  filtro_fecha_fin?: string
  filtro_detalle?: string
  total_registros?: number
}) => api.post('/admin/record-download', data).then(r => r.data)

export interface SolicitudPurgaDatos {
  alcance: 'asistencia' | 'vehicular' | 'institucional_estudiantes' | 'ingestas' | 'todo'
  espacio_id?: number
  confirmacion: string
}

export interface RespuestaPurgaDatos {
  status: string
  mensaje: string
  alcance: string
  espacio_id?: number
  registros_eliminados: Record<string, number>
}

export const purgarDatosAdmin = (solicitud: SolicitudPurgaDatos): Promise<RespuestaPurgaDatos> =>
  api.post<RespuestaPurgaDatos>('/admin/purgar-datos', solicitud).then(r => r.data)

// ─── Exportación Nativa OpenXML a Excel ────────────────────────────────────────

export interface SerieGraficoNativo {
  nombre: string
  valores: (number | null)[]
  color?: string
  tipo_serie?: string
  dash_type?: string
}

export interface GraficoNativoPayload {
  id: string
  titulo: string
  categoria?: string
  tipo_grafico: string
  eje_x_nombre?: string
  eje_y_nombre?: string
  categorias_x: (string | number)[]
  series: SerieGraficoNativo[]
  subtitulo?: string
}

export interface SolicitudExportacionExcel {
  modulo_nombre: string
  periodo_label: string
  filtros?: Record<string, string>
  graficos: GraficoNativoPayload[]
}

export const exportarGraficoExcelNativo = (payload: GraficoNativoPayload): Promise<Blob> =>
  api.post('/export/excel/grafico', payload, { responseType: 'blob', timeout: 180_000 }).then(r => r.data)

export const exportarConsolidadoExcelNativo = (solicitud: SolicitudExportacionExcel): Promise<Blob> =>
  api.post('/export/excel/consolidado', solicitud, { responseType: 'blob', timeout: 180_000 }).then(r => r.data)

export const descargarPlantillaSalasEstudioExcel = async (params: {
  espacio_id?: number
  fecha_inicio?: string
  fecha_fin?: string
  alcance?: string
  regimen_horario?: string
  direccion?: string
  dias_semana?: string
  door?: string
  carrera?: string
  facultad?: string
  periodo_label?: string
}): Promise<Blob> => {
  const res = await api.get('/export/excel/plantilla-salas-estudio', {
    params,
    responseType: 'blob',
    timeout: 180_000,
  })
  return res.data
}

