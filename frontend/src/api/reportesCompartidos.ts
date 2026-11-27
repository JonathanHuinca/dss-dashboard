import { api, type DataFilters } from './clienteBase'

export interface NotaItemReporte {
  id: string
  seccion: string
  titulo: string
  contenido: string
  autor?: string
  fecha?: string
}

export interface DestinatarioReporteInfo {
  id: number
  usuario_id?: number
  nombre_completo: string
  email: string
  cargo: string
  unidad_academica: string
  token_portal: string
  activo: boolean
  cuenta_activada?: boolean
  enlace_activacion?: string | null
  correo_enviado?: boolean
  total_reportes?: number
  actualizado_en?: string | null
}

export interface ReporteCompartidoResumen {
  id: string
  codigo_corto: string
  token_acceso: string
  espacio_id: number
  espacio_nombre: string
  titulo_reporte: string
  finalidad_reporte: string
  nota_general: string
  notas_items: NotaItemReporte[]
  fecha_inicio: string
  fecha_fin: string
  modo_datos: 'dinamico_acotado' | 'instantanea_fija'
  filtros_bloqueados: DataFilters
  graficos_visibles: string[]
  indicadores_visibles: string[]
  permitir_exportacion: boolean
  permitir_ia: boolean
  activo: boolean
  expirado: boolean
  vigente: boolean
  expira_en: string | null
  total_accesos: number
  ultimo_acceso_en: string | null
  creado_en: string | null
  correo_enviado?: boolean
  enlace_activacion?: string | null
  destinatario: DestinatarioReporteInfo
  creador?: {
    id?: number | null
    nombre_completo: string
    email: string
    rol: string
  }
  tiene_campana_24h?: boolean
}

export interface CuotaIAReporte {
  usadas: number
  limite: number | null
  restantes: number | null
  ilimitado?: boolean
}

export interface MensajeIAReporteItem {
  id: number
  sesion_id: string
  pregunta: string
  respuesta: string
  modelo_utilizado?: string | null
  tiempo_respuesta_ms?: number | null
  creado_en: string | null
}

export interface CatalogoItemReporte {
  id: string
  titulo: string
  seccion?: string
}

export interface RespuestaListadoReportes {
  reportes: ReporteCompartidoResumen[]
  destinatarios: DestinatarioReporteInfo[]
  catalogos: {
    [espacioId: string]: {
      graficos: CatalogoItemReporte[]
      indicadores: CatalogoItemReporte[]
    }
  }
}

export interface CrearReporteCompartidoPayload {
  espacio_id: number
  destinatario_nombre: string
  destinatario_email: string
  destinatario_cargo: string
  destinatario_unidad: string
  titulo_reporte: string
  finalidad_reporte: string
  nota_general?: string
  notas_items?: NotaItemReporte[]
  fecha_inicio: string
  fecha_fin: string
  modo_datos: 'dinamico_acotado' | 'instantanea_fija'
  filtros_bloqueados: DataFilters
  graficos_visibles: string[]
  indicadores_visibles: string[]
  permitir_exportacion: boolean
  permitir_ia: boolean
  expira_en?: string | null
}

export interface ActualizarReporteCompartidoPayload {
  activo?: boolean
  permitir_ia?: boolean
  permitir_exportacion?: boolean
  titulo_reporte?: string
  finalidad_reporte?: string
  nota_general?: string
  notas_items?: NotaItemReporte[]
  graficos_visibles?: string[]
  indicadores_visibles?: string[]
  expira_en?: string | null
  reenviar_correo?: boolean
}

export interface RegistrarConsultorPayload {
  nombre_completo: string
  email: string
  cargo: string
  unidad_academica: string
}

export interface UsuarioCandidatoConsultor {
  id: number
  email: string
  nombre_completo: string
  roles: string[]
  es_consultor: boolean
  destinatario_id: number | null
  cargo_sugerido: string
  unidad_sugerida: string
}

export interface VincularUsuarioExistentePayload {
  usuario_id: number
  cargo: string
  unidad_academica: string
}

export interface RespuestaReportePublico {
  requiere_login?: boolean
  reporte: ReporteCompartidoResumen
  datos: {
    kpis_base: Record<string, any>
    indicadores_ejecutivos: Record<string, any>
    indicadores_visibles: string[]
    graficos_visibles: string[]
    graficos: Record<string, any>
    generado_en: string
  } | null
  historial_destinatario: Array<{
    id: string
    codigo_corto: string
    token_acceso: string
    titulo_reporte: string
    finalidad_reporte: string
    espacio_id: number
    espacio_nombre: string
    fecha_inicio: string
    fecha_fin: string
    creado_en: string | null
    vigente: boolean
    activo: boolean
    expirado: boolean
    es_actual: boolean
  }>
  destinatario_puede_ia?: boolean
  cuota_ia?: CuotaIAReporte | null
  mensajes_ia?: MensajeIAReporteItem[]
  catalogos?: {
    graficos: CatalogoItemReporte[]
    indicadores: CatalogoItemReporte[]
  }
}

export async function fetchReportesCompartidos(espacioId?: number): Promise<RespuestaListadoReportes> {
  const { data } = await api.get<RespuestaListadoReportes>('/reportes-compartidos', {
    params: espacioId ? { espacio_id: espacioId } : {},
  })
  return data
}

export async function registrarConsultorReporte(
  payload: RegistrarConsultorPayload
): Promise<DestinatarioReporteInfo> {
  const { data } = await api.post<DestinatarioReporteInfo>('/reportes-compartidos/consultores', payload)
  return data
}

export async function fetchUsuariosCandidatosConsultor(): Promise<UsuarioCandidatoConsultor[]> {
  const { data } = await api.get<UsuarioCandidatoConsultor[]>('/reportes-compartidos/usuarios-candidatos')
  return data
}

export async function vincularUsuarioExistenteConsultor(
  payload: VincularUsuarioExistentePayload
): Promise<DestinatarioReporteInfo> {
  const { data } = await api.post<DestinatarioReporteInfo>(
    '/reportes-compartidos/vincular-usuario-existente',
    payload
  )
  return data
}

export async function fetchMisReportesConsultor(signal?: AbortSignal): Promise<{
  destinatario: DestinatarioReporteInfo
  reportes: Array<any>
}> {
  const { data } = await api.get('/reportes-compartidos/mis-reportes', {
    signal,
    timeout: 45_000,
  })
  return data
}

export async function crearReporteCompartido(
  payload: CrearReporteCompartidoPayload
): Promise<ReporteCompartidoResumen> {
  const { data } = await api.post<ReporteCompartidoResumen>('/reportes-compartidos', payload, {
    timeout: 90_000,
  })
  return data
}

export async function actualizarReporteCompartido(
  reporteId: string,
  payload: ActualizarReporteCompartidoPayload
): Promise<ReporteCompartidoResumen> {
  const { data } = await api.patch<ReporteCompartidoResumen>(`/reportes-compartidos/${reporteId}`, payload)
  return data
}

export async function eliminarReporteCompartido(reporteId: string): Promise<{ eliminado: boolean; id: string }> {
  const { data } = await api.delete(`/reportes-compartidos/${reporteId}`)
  return data
}

export async function actualizarEstadoDestinatario(
  destinatarioId: number,
  activo: boolean
): Promise<{ id: number; nombre_completo: string; email: string; activo: boolean }> {
  const { data } = await api.patch(`/reportes-compartidos/destinatarios/${destinatarioId}`, { activo })
  return data
}

export async function eliminarDestinatarioReporte(
  destinatarioId: number
): Promise<{ eliminado: boolean; id: number; email: string }> {
  const { data } = await api.delete(`/reportes-compartidos/destinatarios/${destinatarioId}`)
  return data
}

export async function activarCuentaConsultorDesdeReporte(
  token: string,
  nuevaPassword: string,
  confirmarPassword: string
): Promise<any> {
  const { data } = await api.post('/auth/activate', {
    token,
    nueva_password: nuevaPassword,
    confirmar_password: confirmarPassword,
  })
  return data
}

export async function fetchReportePublicoPorToken(tokenAcceso: string, signal?: AbortSignal): Promise<RespuestaReportePublico> {
  const { data } = await api.get<RespuestaReportePublico>(`/reportes-compartidos/publico/${encodeURIComponent(tokenAcceso)}`, {
    signal,
    timeout: 60_000,
  })
  return data
}

export async function fetchPortalDestinatarioPorToken(tokenPortal: string, signal?: AbortSignal): Promise<{
  destinatario: DestinatarioReporteInfo
  reportes: Array<any>
}> {
  const { data } = await api.get(`/reportes-compartidos/portal/${encodeURIComponent(tokenPortal)}`, {
    signal,
    timeout: 45_000,
  })
  return data
}

export async function fetchHistorialIAReportePublico(
  tokenAcceso: string
): Promise<{ mensajes: MensajeIAReporteItem[]; cuota?: CuotaIAReporte | null }> {
  const { data } = await api.get<{ mensajes: MensajeIAReporteItem[]; cuota?: CuotaIAReporte | null }>(
    `/reportes-compartidos/publico/${encodeURIComponent(tokenAcceso)}/ia/historial`
  )
  return data
}

export async function consultarIAReportePublico(
  tokenAcceso: string,
  pregunta: string,
  sesionId: string = 'principal'
): Promise<{
  id: number
  sesion_id: string
  pregunta: string
  respuesta: string
  modelo_utilizado?: string | null
  tiempo_respuesta_ms?: number | null
  timestamp: string
  cuota?: CuotaIAReporte | null
}> {
  const { data } = await api.post(`/reportes-compartidos/publico/${encodeURIComponent(tokenAcceso)}/consultar-ia`, {
    pregunta,
    sesion_id: sesionId,
  })
  return data
}

export interface EmisorReporteInfo {
  id: number
  nombre_completo: string
  email: string
  rol: string
}

export interface AuditoriaReporteResumen extends ReporteCompartidoResumen {
  emisor?: EmisorReporteInfo | null
  revisado: boolean
  total_aperturas: number
  total_descargas: number
  total_descargas_excel: number
  total_descargas_csv: number
  total_descargas_pdf: number
  total_descargas_imagen: number
  total_consultas_ia: number
  primer_acceso_en?: string | null
  ultima_ip?: string | null
  ultimo_user_agent?: string | null
}

export interface AuditoriaReportesKpis {
  total_reportes: number
  reportes_revisados: number
  reportes_sin_revisar: number
  tasa_lectura_pct: number
  total_aperturas: number
  total_descargas: number
  total_consultas_ia: number
}

export interface RespuestaAuditoriaReportes {
  rol_auditor: string
  espacios_autorizados: number[] | null
  kpis: AuditoriaReportesKpis
  total: number
  page: number
  page_size: number
  total_pages: number
  items: AuditoriaReporteResumen[]
}

export interface EventoAuditoriaReporte {
  id: number
  fecha_hora: string | null
  accion: string
  ip_origen?: string | null
  detalle?: string | null
  user_agent?: string | null
}

export interface RespuestaEventosReporte {
  reporte_id: string
  codigo_corto: string
  titulo_reporte: string
  destinatario: {
    nombre_completo: string | null
    email: string | null
  }
  eventos: EventoAuditoriaReporte[]
}

export async function fetchAuditoriaReportes(params?: {
  espacio_id?: number
  emisor_rol?: string
  estado_revision?: string
  solo_activos?: boolean
  search?: string
  page?: number
  page_size?: number
}): Promise<RespuestaAuditoriaReportes> {
  const { data } = await api.get<RespuestaAuditoriaReportes>('/reportes-compartidos/auditoria', {
    params,
  })
  return data
}

export async function fetchEventosReporte(
  reporteId: string,
  params?: { accion?: string; limit?: number }
): Promise<RespuestaEventosReporte> {
  const { data } = await api.get<RespuestaEventosReporte>(`/reportes-compartidos/${reporteId}/eventos`, {
    params,
  })
  return data
}

export async function registrarEventoReportePublico(
  tokenAcceso: string,
  accion: 'descarga_excel' | 'descarga_csv' | 'descarga_pdf' | 'descarga_imagen',
  detalle?: string
): Promise<void> {
  await api.post(`/reportes-compartidos/publico/${encodeURIComponent(tokenAcceso)}/evento`, {
    accion,
    detalle,
  })
}

