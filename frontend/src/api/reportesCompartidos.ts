import { api, DataFilters } from './clienteBase'

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
}

export interface CatalogoItemReporte {
  id: string
  titulo: string
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

export interface RespuestaReportePublico {
  reporte: ReporteCompartidoResumen
  datos: {
    kpis_base: Record<string, any>
    indicadores_ejecutivos: Record<string, any>
    indicadores_visibles: string[]
    graficos_visibles: string[]
    graficos: Record<string, any>
    generado_en: string
  }
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
  requiere_crear_password?: boolean
  token_activacion?: string | null
  catalogos: {
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

export async function fetchMisReportesConsultor(): Promise<{
  destinatario: DestinatarioReporteInfo
  reportes: Array<any>
}> {
  const { data } = await api.get('/reportes-compartidos/mis-reportes')
  return data
}

export async function crearReporteCompartido(
  payload: CrearReporteCompartidoPayload
): Promise<ReporteCompartidoResumen> {
  const { data } = await api.post<ReporteCompartidoResumen>('/reportes-compartidos', payload)
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

export async function fetchReportePublicoPorToken(tokenAcceso: string): Promise<RespuestaReportePublico> {
  const { data } = await api.get<RespuestaReportePublico>(`/reportes-compartidos/publico/${tokenAcceso}`)
  return data
}

export async function fetchPortalDestinatarioPorToken(tokenPortal: string): Promise<{
  destinatario: DestinatarioReporteInfo
  reportes: Array<any>
}> {
  const { data } = await api.get(`/reportes-compartidos/portal/${tokenPortal}`)
  return data
}

export async function consultarIAReportePublico(
  tokenAcceso: string,
  pregunta: string
): Promise<{ respuesta: string; timestamp: string }> {
  const { data } = await api.post(`/reportes-compartidos/publico/${tokenAcceso}/consultar-ia`, {
    pregunta,
  })
  return data
}

