import React, { useEffect, useMemo, useState } from 'react'
import {
  Share2,
  X,
  Copy,
  Check,
  ShieldCheck,
  Sparkles,
  FileText,
  UserCheck,
  UserPlus,
  Plus,
  Trash2,
  ExternalLink,
  Power,
  Edit3,
  MessageSquarePlus,
  Lock,
  Layers,
  BarChart3,
  Mail,
  Calendar,
  KeyRound,
  Link2,
  Search,
  Building2,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Info,
  SlidersHorizontal,
} from 'lucide-react'
import {
  DataFilters,
  ReporteCompartidoResumen,
  DestinatarioReporteInfo,
  NotaItemReporte,
  CatalogoItemReporte,
  UsuarioCandidatoConsultor,
  fetchReportesCompartidos,
  crearReporteCompartido,
  actualizarReporteCompartido,
  eliminarReporteCompartido,
  actualizarEstadoDestinatario,
  eliminarDestinatarioReporte,
  registrarConsultorReporte,
  fetchUsuariosCandidatosConsultor,
  vincularUsuarioExistenteConsultor,
} from '../../api/client'

interface CompartirReporteModalProps {
  abierto: boolean
  onCerrar: () => void
  espacioIdInicial: number
  fechaInicioInicial: string
  fechaFinInicial: string
  etiquetaPeriodoInicial?: string
  filtrosIniciales: DataFilters
  totalRegistrosInicial?: number
  tieneCampana24hActiva?: boolean
}

const CATALOGO_POR_DEFECTO: Record<
  number,
  { graficos: CatalogoItemReporte[]; indicadores: CatalogoItemReporte[] }
> = {
  1: {
    graficos: [
      { id: 'aforo_presencia_intervalos', titulo: 'Curva de Presencia Física en Sala por Intervalos de Sesión vs Capacidad Máxima', seccion: '1. Resumen y Demanda General' },
      { id: 'prophet_presencia_14dias', titulo: 'Pronóstico Continuo de Presencia Física en Sala (Prophet Logístico Acotado)', seccion: '1. Resumen y Demanda General' },
      { id: 'distribucion_curricular', titulo: 'Distribución por Carrera y Facultad (Ley 21.719)', seccion: '1. Resumen y Demanda General' },
      { id: 'perfiles_visita', titulo: 'Perfiles de Estadía y Permanencia (Donut)', seccion: '1. Resumen y Demanda General' },
      { id: 'flujo_horario', titulo: 'Flujo Horario de Ingresos y Salidas', seccion: '1. Resumen y Demanda General' },
      { id: 'mapa_calor', titulo: 'Mapa de Calor (Día de Semana x Hora)', seccion: '1. Resumen y Demanda General' },
      { id: 'comparativa_salas', titulo: 'Comparativa Sala 1 vs Sala 2 (Pecera)', seccion: '2. Salas y Torniquetes' },
      { id: 'uso_torniquetes', titulo: 'Flujo por Torniquetes y Accesos Universales', seccion: '2. Salas y Torniquetes' },
      { id: 'frecuencia_marcajes', titulo: 'Distribución de Frecuencia de Marcajes', seccion: '2. Salas y Torniquetes' },
      { id: 'volumen_mensual', titulo: 'Volumen y Promedio Diario Mensual', seccion: '3. Evolución e Hitos' },
      { id: 'evolucion_semanal', titulo: 'Evolución Semanal (Semanas ISO)', seccion: '3. Evolución e Hitos' },
      { id: 'promedio_dia_semana', titulo: 'Promedio de Ingresos por Día de la Semana', seccion: '3. Evolución e Hitos' },
      { id: 'hitos_academicos', titulo: 'Comparativa por Hito del Calendario Académico', seccion: '3. Evolución e Hitos' },
      { id: 'campana_24h_resumen', titulo: 'KPIs Nocturnos, Delta 24h y Dictamen Ejecutivo', seccion: '5. Campaña 24 Horas Exámenes' },
      { id: 'campana_24h_curva_calor', titulo: 'Curva Continua Nocturna (20:00-07:00) y Mapa de Calor', seccion: '5. Campaña 24 Horas Exámenes' },
      { id: 'campana_24h_fases_dias', titulo: 'Fases de la Noche y Distribución por Día de Semana', seccion: '5. Campaña 24 Horas Exámenes' },
      { id: 'campana_24h_academico', titulo: 'Top Carreras y Facultades en Horario Nocturno', seccion: '5. Campaña 24 Horas Exámenes' },
      { id: 'campana_24h_comparativa', titulo: 'Comparativa Multicampaña (Históricas vs Actuales)', seccion: '5. Campaña 24 Horas Exámenes' },
    ],
    indicadores: [
      { id: 'dias_operativos', titulo: 'Días Operativos' },
      { id: 'carrera_mas_concurrida', titulo: 'Carrera Más Concurrida' },
      { id: 'recurrencia_mensual', titulo: 'Recurrencia Mensual' },
      { id: 'hora_pico_ingreso', titulo: 'Hora de Máxima Afluencia' },
      { id: 'pico_concurrente', titulo: 'Aforo Máximo Concurrente' },
      { id: 'afluencia_total', titulo: 'Afluencia Total' },
      { id: 'aforo_maximo_registrado', titulo: 'Aforo Máximo Registrado' },
      { id: 'estadia_promedio', titulo: 'Estadía Promedio' },
      { id: 'tasa_rebote', titulo: 'Tasa de Rebote' },
    ],
  },
  2: {
    graficos: [
      { id: 'presencia_vehicular_intervalos', titulo: 'Curva de Presencia Física Vehicular por Intervalos de Sesión vs Capacidad', seccion: '1. Aforo y Pronóstico' },
      { id: 'prophet_vehicular', titulo: 'Pronóstico Continuo Prophet Vehicular', seccion: '1. Aforo y Pronóstico' },
      { id: 'flujo_horario_vehicular', titulo: 'Flujo Horario de Ingresos y Salidas Vehiculares', seccion: '2. Flujo Horario de Accesos' },
      { id: 'composicion_flota', titulo: 'Composición por Tipo de Vehículo', seccion: '3. Flota y Cámaras ANPR' },
      { id: 'distribucion_marcas', titulo: 'Distribución por Marca de Vehículo', seccion: '3. Flota y Cámaras ANPR' },
      { id: 'estadisticas_camaras', titulo: 'Distribución por Pórtico y Cámara ANPR', seccion: '3. Flota y Cámaras ANPR' },
      { id: 'movilidad_intercampus', titulo: 'Movilidad Intercampus CSF - CHS', seccion: '4. Movilidad y Calendario' },
      { id: 'hitos_academicos_vehicular', titulo: 'Comparativa por Hito Académico Vehicular', seccion: '4. Movilidad y Calendario' },
      { id: 'clusters_comportamiento', titulo: 'Perfiles de Uso Vehicular (Clustering K-Means)', seccion: '5. Machine Learning (K-Means) y Estadía' },
      { id: 'distribucion_estadia', titulo: 'Distribución de Tiempos de Permanencia', seccion: '5. Machine Learning (K-Means) y Estadía' },
    ],
    indicadores: [
      { id: 'dias_operativos', titulo: 'Días Operativos' },
      { id: 'sector_mas_concurrido', titulo: 'Sector Más Demandado' },
      { id: 'recurrencia_vehicular', titulo: 'Recurrencia Vehicular' },
      { id: 'hora_pico_acceso', titulo: 'Hora de Mayor Demanda' },
      { id: 'pico_concurrente', titulo: 'Máxima Ocupación Simultánea' },
      { id: 'vehiculos_dentro', titulo: 'Vehículos Dentro' },
      { id: 'plazas_libres', titulo: 'Plazas Libres' },
      { id: 'total_ingresos', titulo: 'Total Ingresos' },
      { id: 'total_salidas', titulo: 'Total Salidas' },
      { id: 'rotacion_diaria', titulo: 'Rotación Diaria' },
      { id: 'permanencia_mediana', titulo: 'Permanencia Mediana' },
    ],
  },
}

function formatearSalaLegible(sala?: string): string {
  if (!sala || sala === 'todos') return 'Ambas Salas (Sala 1 + Sala 2)'
  const s = sala.toLowerCase()
  if (s.includes('csf02') || s.includes('sala_1') || s === '1') return 'Sala 1 (CSF02 - 2° Piso)'
  if (s.includes('csf04') || s.includes('sala_2') || s === '2') return 'Sala 2 Pecera (CSF04 - 1° Piso)'
  return sala
}

function formatearRegimenLegible(regimen?: string): string {
  if (!regimen || regimen === 'todos') return 'Todo Horario'
  const partes = regimen.split(',').map((p) => p.trim()).filter(Boolean)
  const mapEtiqueta: Record<string, string> = {
    dentro_horario: 'Dentro de Horario Hábil',
    fuera_horario: 'Fuera de Horario',
    dias_cierre: 'Días de Cierre',
    paro_federado: 'Paro Federado',
    paro_carrera: 'Paro de Carrera',
    '24h': 'Horario 24 Horas',
    '24h_total': 'Horario 24 Horas (Total)',
    '24h_delta': 'Horario 24 Horas (Madrugada)',
  }
  return partes
    .map((p) => {
      if (mapEtiqueta[p]) return mapEtiqueta[p]
      if (p.startsWith('horario_')) return 'Horario Especial Seleccionado'
      return p
    })
    .join(', ')
}

function formatearDireccionLegible(direccion?: string, espacioId = 1): string {
  if (!direccion || direccion === 'todos') return espacioId === 1 ? 'Todos los Flujos' : 'Ingresos y Salidas'
  const partes = direccion.split(',').map((p) => p.trim().toLowerCase()).filter(Boolean)
  const mapDir: Record<string, string> = {
    completos: 'Visita Regular (Entrada y Salida)',
    solo_ingreso: 'Solo Entrada',
    entrada: 'Solo Ingresos',
    solo_salida: 'Solo Salida',
    salida: 'Solo Salidas',
  }
  return partes.map((p) => mapDir[p] || p).join(', ')
}

function formatearDiasLegible(dias?: string): string {
  if (!dias) return 'Lun–Dom (Todos)'
  const lista = dias.split(',').map((d) => d.trim().toLowerCase()).filter(Boolean)
  if (lista.length === 0 || lista.length === 7) return 'Lun–Dom (Todos)'
  if (lista.length === 5 && !lista.includes('sabado') && !lista.includes('domingo')) return 'Lunes a Viernes'
  if (lista.length === 2 && lista.includes('sabado') && lista.includes('domingo')) return 'Fin de Semana'
  return lista.map((d) => d.charAt(0).toUpperCase() + d.slice(1)).join(', ')
}

export const CompartirReporteModal: React.FC<CompartirReporteModalProps> = ({
  abierto,
  onCerrar,
  espacioIdInicial,
  fechaInicioInicial,
  fechaFinInicial,
  etiquetaPeriodoInicial,
  filtrosIniciales,
  totalRegistrosInicial,
  tieneCampana24hActiva = false,
}) => {
  const [pestanaActiva, setPestanaActiva] = useState<'emitir' | 'consultores' | 'historial'>('emitir')
  const [cargando, setCargando] = useState<boolean>(false)
  const [guardando, setGuardando] = useState<boolean>(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [exitoMsg, setExitoMsg] = useState<string | null>(null)

  const [reportesEmitidos, setReportesEmitidos] = useState<ReporteCompartidoResumen[]>([])
  const [destinatarios, setDestinatarios] = useState<DestinatarioReporteInfo[]>([])
  const [catalogos, setCatalogos] = useState(CATALOGO_POR_DEFECTO)

  // Selección, vinculación o alta de usuario Consultor_Reporte en Pestaña 1
  const [modoConsultor, setModoConsultor] = useState<'seleccionar' | 'vincular_existente' | 'nuevo'>('seleccionar')
  const [consultorSeleccionadoId, setConsultorSeleccionadoId] = useState<string>('')
  const [destinatarioNombre, setDestinatarioNombre] = useState('')
  const [destinatarioEmail, setDestinatarioEmail] = useState('')
  const [destinatarioCargo, setDestinatarioCargo] = useState('')
  const [destinatarioUnidad, setDestinatarioUnidad] = useState('')

  // Gestión de usuarios institucionales candidatos del campus
  const [usuariosCandidatos, setUsuariosCandidatos] = useState<UsuarioCandidatoConsultor[]>([])
  const [candidatoSeleccionadoId, setCandidatoSeleccionadoId] = useState<string>('')
  const [candidatoFiltroTexto, setCandidatoFiltroTexto] = useState<string>('')
  const [vinculandoCandidato, setVinculandoCandidato] = useState<boolean>(false)

  // Subpestaña en Pestaña 2 (Consultores): 'vincular' o 'nuevo'
  const [subpestanaConsultor, setSubpestanaConsultor] = useState<'vincular' | 'nuevo'>('vincular')
  const [vincularP2UsuarioId, setVincularP2UsuarioId] = useState<string>('')
  const [vincularP2Cargo, setVincularP2Cargo] = useState<string>('')
  const [vincularP2Unidad, setVincularP2Unidad] = useState<string>('')

  // Formulario independiente para alta de nuevo Consultor_Reporte externo en Pestaña 2
  const [nuevoConsultorNombre, setNuevoConsultorNombre] = useState('')
  const [nuevoConsultorEmail, setNuevoConsultorEmail] = useState('')
  const [nuevoConsultorCargo, setNuevoConsultorCargo] = useState('')
  const [nuevoConsultorUnidad, setNuevoConsultorUnidad] = useState('')

  // Datos del reporte basados en los filtros actuales de la vista
  const [tituloReporte, setTituloReporte] = useState('')
  const [finalidadReporte, setFinalidadReporte] = useState('')
  const [modoDatos] = useState<'instantanea_fija'>('instantanea_fija')
  const [tipoVigencia, setTipoVigencia] = useState<'indefinido' | '7d' | '30d' | 'semestre' | 'custom'>('30d')
  const [fechaExpiracionCustom, setFechaExpiracionCustom] = useState('')

  // Permisos del enlace (IA deshabilitada por defecto)
  const [permitirIA, setPermitirIA] = useState<boolean>(false)
  const [permitirExportacion, setPermitirExportacion] = useState<boolean>(true)

  // Selección de gráficos e indicadores
  const [graficosSeleccionados, setGraficosSeleccionados] = useState<string[]>([])
  const [indicadoresSeleccionados, setIndicadoresSeleccionados] = useState<string[]>([])
  const [seccionesColapsadas, setSeccionesColapsadas] = useState<Record<string, boolean>>({})

  // Notas del emisor
  const [notaGeneral, setNotaGeneral] = useState<string>('')
  const [notasItems, setNotasItems] = useState<NotaItemReporte[]>([])
  const [nuevaNotaSeccion, setNuevaNotaSeccion] = useState<string>('general')
  const [nuevaNotaTitulo, setNuevaNotaTitulo] = useState<string>('')
  const [nuevaNotaContenido, setNuevaNotaContenido] = useState<string>('')

  const [reporteRecienCreado, setReporteRecienCreado] = useState<ReporteCompartidoResumen | null>(null)
  const [reporteEditandoNotas, setReporteEditandoNotas] = useState<ReporteCompartidoResumen | null>(null)
  const [reporteEditandoContenido, setReporteEditandoContenido] = useState<{
    reporte: ReporteCompartidoResumen
    graficos: string[]
    indicadores: string[]
    colapsadas: Record<string, boolean>
  } | null>(null)
  const [copiadoClave, setCopiadoClave] = useState<string | null>(null)

  const obtenerCatalogoPorEspacio = (espacioId: number, permitir24h: boolean) => {
    const base = catalogos[espacioId] || CATALOGO_POR_DEFECTO[espacioId] || CATALOGO_POR_DEFECTO[1]
    const defectoMap = new Map(
      (CATALOGO_POR_DEFECTO[espacioId]?.graficos || []).map((g) => [g.id, g.seccion])
    )
    const graficosConSeccion = base.graficos
      .filter((g) => {
        if (espacioId === 1 && !permitir24h) {
          return g.id !== 'campana_24_horas' && !g.id.startsWith('campana_24h_')
        }
        return true
      })
      .map((g) => ({
        ...g,
        seccion: g.seccion || defectoMap.get(g.id) || 'Gráficos Adicionales',
      }))

    const mapa = new Map<string, CatalogoItemReporte[]>()
    for (const graf of graficosConSeccion) {
      const nombreSec = graf.seccion || 'Gráficos del Reporte'
      const actuales = mapa.get(nombreSec) || []
      actuales.push(graf)
      mapa.set(nombreSec, actuales)
    }

    return {
      ...base,
      graficos: graficosConSeccion,
      secciones: Array.from(mapa.entries()).map(([nombre, items]) => ({ nombre, items })),
    }
  }

  const catalogoActual = useMemo(
    () => obtenerCatalogoPorEspacio(espacioIdInicial, tieneCampana24hActiva),
    [catalogos, espacioIdInicial, tieneCampana24hActiva]
  )
  const seccionesGraficos = catalogoActual.secciones

  const catalogoEdicionContenido = useMemo(() => {
    if (!reporteEditandoContenido) return null
    const rep = reporteEditandoContenido.reporte
    return obtenerCatalogoPorEspacio(rep.espacio_id, Boolean(rep.tiene_campana_24h))
  }, [catalogos, reporteEditandoContenido])

  // Resumen legible y dinámico de TODOS los filtros activos en la pantalla del emisor
  const resumenFiltrosPantalla = useMemo(() => {
    const chips: Array<{ etiqueta: string; valor: string; destacado?: boolean }> = []
    const alcanceVal = filtrosIniciales.alcance || 'conformes'
    const alcanceTexto =
      alcanceVal === 'conformes'
        ? 'Datos Conformes'
        : alcanceVal === 'anomalias'
        ? 'Solo Anomalías'
        : 'Todos los Registros'

    if (espacioIdInicial === 1) {
      chips.push({
        etiqueta: 'Sala Física',
        valor: formatearSalaLegible(filtrosIniciales.sala),
        destacado: Boolean(filtrosIniciales.sala && filtrosIniciales.sala !== 'todos'),
      })
      chips.push({
        etiqueta: 'Facultad',
        valor: filtrosIniciales.facultad || 'Todas las facultades',
        destacado: Boolean(filtrosIniciales.facultad),
      })
      chips.push({
        etiqueta: 'Carrera',
        valor: filtrosIniciales.carrera || 'Todas las carreras',
        destacado: Boolean(filtrosIniciales.carrera),
      })
      if (filtrosIniciales.cohorte) {
        chips.push({
          etiqueta: 'Cohorte',
          valor: String(filtrosIniciales.cohorte),
          destacado: true,
        })
      }
      chips.push({
        etiqueta: 'Calidad de Datos',
        valor: alcanceTexto,
        destacado: alcanceVal !== 'conformes',
      })
      chips.push({
        etiqueta: 'Régimen Horario',
        valor: formatearRegimenLegible(filtrosIniciales.regimen_horario),
        destacado: Boolean(filtrosIniciales.regimen_horario && filtrosIniciales.regimen_horario !== 'todos'),
      })
      chips.push({
        etiqueta: 'Flujo de Visita',
        valor: formatearDireccionLegible(filtrosIniciales.direccion, 1),
        destacado: Boolean(filtrosIniciales.direccion && filtrosIniciales.direccion !== 'todos'),
      })
      chips.push({
        etiqueta: 'Días Operativos',
        valor: formatearDiasLegible(filtrosIniciales.dias_semana),
        destacado: Boolean(filtrosIniciales.dias_semana),
      })
      if (filtrosIniciales.door && filtrosIniciales.door !== 'todos') {
        chips.push({
          etiqueta: 'Torniquetes / Accesos',
          valor: filtrosIniciales.door,
          destacado: true,
        })
      }
      if (filtrosIniciales.perfil_visita && filtrosIniciales.perfil_visita !== 'todos') {
        chips.push({
          etiqueta: 'Perfil de Estadía',
          valor: filtrosIniciales.perfil_visita,
          destacado: true,
        })
      }
      if (filtrosIniciales.marcajes && filtrosIniciales.marcajes !== 'todos') {
        chips.push({
          etiqueta: 'Marcajes Diarios',
          valor: filtrosIniciales.marcajes,
          destacado: true,
        })
      }
    } else {
      chips.push({
        etiqueta: 'Sector Estacionamiento',
        valor: filtrosIniciales.sector || 'Todos los sectores CSF (125 plazas)',
        destacado: Boolean(filtrosIniciales.sector && filtrosIniciales.sector !== 'todos'),
      })
      chips.push({
        etiqueta: 'Tipo de Vehículo',
        valor: filtrosIniciales.tipo_vehiculo || 'Toda la flota',
        destacado: Boolean(filtrosIniciales.tipo_vehiculo),
      })
      chips.push({
        etiqueta: 'Flujo Vehicular',
        valor: formatearDireccionLegible(filtrosIniciales.direccion, 2),
        destacado: Boolean(filtrosIniciales.direccion && filtrosIniciales.direccion !== 'todos'),
      })
      chips.push({
        etiqueta: 'Calidad ANPR',
        valor:
          alcanceVal === 'conformes'
            ? 'Placas Reconocidas'
            : alcanceVal === 'anomalias'
            ? 'Solo Unknown'
            : 'Todas las Capturas',
        destacado: alcanceVal !== 'conformes',
      })
      chips.push({
        etiqueta: 'Régimen Horario',
        valor: formatearRegimenLegible(filtrosIniciales.regimen_horario),
        destacado: Boolean(filtrosIniciales.regimen_horario && filtrosIniciales.regimen_horario !== 'todos'),
      })
      chips.push({
        etiqueta: 'Días Operativos',
        valor: formatearDiasLegible(filtrosIniciales.dias_semana),
        destacado: Boolean(filtrosIniciales.dias_semana),
      })
    }
    return chips
  }, [espacioIdInicial, filtrosIniciales])

  useEffect(() => {
    if (!abierto) return
    const cat = CATALOGO_POR_DEFECTO[espacioIdInicial] || CATALOGO_POR_DEFECTO[1]
    const graficosIniciales = cat.graficos
      .filter((g) => !(espacioIdInicial === 1 && !tieneCampana24hActiva && (g.id === 'campana_24_horas' || g.id.startsWith('campana_24h_'))))
      .map((g) => g.id)
    setGraficosSeleccionados(graficosIniciales)
    setIndicadoresSeleccionados(cat.indicadores.map((i) => i.id))

    if (espacioIdInicial === 1 && !tieneCampana24hActiva) {
      setNotasItems((prev) =>
        prev.filter((n) => n.seccion !== 'campana_24_horas' && !n.seccion.startsWith('campana_24h_'))
      )
      setNuevaNotaSeccion((prev) =>
        prev === 'campana_24_horas' || prev.startsWith('campana_24h_') ? 'general' : prev
      )
    }

    const nombreRecinto = espacioIdInicial === 1 ? 'Biblioteca CSF' : 'Estacionamiento CSF'
    const partesFoco: string[] = []
    if (espacioIdInicial === 1) {
      if (filtrosIniciales.sala && filtrosIniciales.sala !== 'todos') {
        partesFoco.push(formatearSalaLegible(filtrosIniciales.sala))
      }
      if (filtrosIniciales.carrera) {
        partesFoco.push(filtrosIniciales.carrera)
      } else if (filtrosIniciales.facultad) {
        partesFoco.push(filtrosIniciales.facultad)
      }
    } else {
      if (filtrosIniciales.sector && filtrosIniciales.sector !== 'todos') {
        partesFoco.push(`Sector ${filtrosIniciales.sector}`)
      }
      if (filtrosIniciales.tipo_vehiculo) {
        partesFoco.push(filtrosIniciales.tipo_vehiculo)
      }
    }
    const foco = partesFoco.length > 0 ? partesFoco.join(' • ') : 'Alcance General'
    setTituloReporte(`Reporte Ejecutivo ${nombreRecinto} — ${foco} (${fechaInicioInicial} a ${fechaFinInicial})`)
    cargarListado()
  }, [abierto, espacioIdInicial, fechaInicioInicial, fechaFinInicial, filtrosIniciales, tieneCampana24hActiva])

  const cargarListado = async (idPreferido?: string) => {
    setCargando(true)
    setErrorMsg(null)
    try {
      const [resp, candidatos] = await Promise.all([
        fetchReportesCompartidos(),
        fetchUsuariosCandidatosConsultor().catch(() => []),
      ])
      setReportesEmitidos(resp.reportes || [])
      const listaDest: DestinatarioReporteInfo[] = resp.destinatarios || []
      setDestinatarios(listaDest)
      setUsuariosCandidatos(candidatos || [])

      const idBusqueda = idPreferido !== undefined ? idPreferido : consultorSeleccionadoId
      const encontrado = listaDest.find((d) => String(d.id) === String(idBusqueda))

      if (listaDest.length === 0) {
        if (candidatos && candidatos.length > 0) {
          seleccionarCandidatoParaReporte(candidatos[0])
        } else {
          limpiarCamposConsultor()
        }
      } else if (encontrado) {
        seleccionarConsultorExistente(encontrado)
      } else if (listaDest[0]) {
        seleccionarConsultorExistente(listaDest[0])
      }

      if (resp.catalogos) {
        setCatalogos({
          1: resp.catalogos['1'] || CATALOGO_POR_DEFECTO[1],
          2: resp.catalogos['2'] || CATALOGO_POR_DEFECTO[2],
        })
      }
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No fue posible cargar el listado de reportes compartidos.')
    } finally {
      setCargando(false)
    }
  }

  const seleccionarConsultorExistente = (dest: DestinatarioReporteInfo) => {
    setConsultorSeleccionadoId(String(dest.id))
    setDestinatarioNombre(dest.nombre_completo)
    setDestinatarioEmail(dest.email)
    setDestinatarioCargo(dest.cargo)
    setDestinatarioUnidad(dest.unidad_academica)
    setModoConsultor('seleccionar')
  }

  const seleccionarCandidatoParaReporte = (cand: UsuarioCandidatoConsultor) => {
    setCandidatoSeleccionadoId(String(cand.id))
    setDestinatarioNombre(cand.nombre_completo)
    setDestinatarioEmail(cand.email)
    setDestinatarioCargo(cand.cargo_sugerido)
    setDestinatarioUnidad(cand.unidad_sugerida)
    setModoConsultor('vincular_existente')
  }

  const limpiarCamposConsultor = () => {
    setConsultorSeleccionadoId('')
    setDestinatarioNombre('')
    setDestinatarioEmail('')
    setDestinatarioCargo('')
    setDestinatarioUnidad('')
    setModoConsultor('nuevo')
  }

  const handleVincularCandidatoDirecto = async () => {
    if (!candidatoSeleccionadoId) {
      setErrorMsg('Seleccione un usuario institucional del campus.')
      return
    }
    const cand = usuariosCandidatos.find((u) => String(u.id) === String(candidatoSeleccionadoId))
    if (!cand) return

    setVinculandoCandidato(true)
    setErrorMsg(null)
    setExitoMsg(null)
    try {
      const resp = await vincularUsuarioExistenteConsultor({
        usuario_id: cand.id,
        cargo: destinatarioCargo.trim() || cand.cargo_sugerido,
        unidad_academica: destinatarioUnidad.trim() || cand.unidad_sugerida,
      })
      setExitoMsg(
        `Usuario institucional ${resp.nombre_completo} (${resp.email}) vinculado al rol Consultor de Reportes con éxito. Mantendrá su contraseña actual.`
      )
      await cargarListado(String(resp.id))
      setModoConsultor('seleccionar')
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No se pudo vincular el usuario al rol consultor.')
    } finally {
      setVinculandoCandidato(false)
    }
  }

  const handleVincularEnPestana2 = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!vincularP2UsuarioId) {
      setErrorMsg('Seleccione un usuario institucional para vincular.')
      return
    }
    const cand = usuariosCandidatos.find((u) => String(u.id) === String(vincularP2UsuarioId))
    if (!cand) return

    setGuardando(true)
    setErrorMsg(null)
    setExitoMsg(null)
    try {
      const resp = await vincularUsuarioExistenteConsultor({
        usuario_id: cand.id,
        cargo: vincularP2Cargo.trim() || cand.cargo_sugerido,
        unidad_academica: vincularP2Unidad.trim() || cand.unidad_sugerida,
      })
      setExitoMsg(
        `Usuario ${resp.nombre_completo} (${resp.email}) vinculado al rol Consultor_Reporte con éxito. Sus credenciales actuales se preservan intactas.`
      )
      setVincularP2UsuarioId('')
      setVincularP2Cargo('')
      setVincularP2Unidad('')
      await cargarListado(String(resp.id))
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No se pudo vincular el usuario institucional.')
    } finally {
      setGuardando(false)
    }
  }

  const handleRegistrarConsultorDirecto = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMsg(null)
    setExitoMsg(null)
    setGuardando(true)
    try {
      const nuevo = await registrarConsultorReporte({
        nombre_completo: nuevoConsultorNombre,
        email: nuevoConsultorEmail,
        cargo: nuevoConsultorCargo,
        unidad_academica: nuevoConsultorUnidad,
      })
      setNuevoConsultorNombre('')
      setNuevoConsultorEmail('')
      setNuevoConsultorCargo('')
      setNuevoConsultorUnidad('')
      await cargarListado(String(nuevo.id))
      setExitoMsg(
        nuevo.correo_enviado
          ? `Usuario Consultor (${nuevo.email}) registrado. Se envió a su correo el enlace institucional para crear su contraseña.`
          : `Usuario Consultor (${nuevo.email}) registrado correctamente.`
      )
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No se pudo registrar el usuario Consultor de Reporte.')
    } finally {
      setGuardando(false)
    }
  }

  const handleReenviarLinkPasswordConsultor = async (dest: DestinatarioReporteInfo) => {
    setErrorMsg(null)
    setExitoMsg(null)
    try {
      const res = await registrarConsultorReporte({
        nombre_completo: dest.nombre_completo,
        email: dest.email,
        cargo: dest.cargo,
        unidad_academica: dest.unidad_academica,
      })
      await cargarListado(String(dest.id))
      setExitoMsg(
        res.correo_enviado
          ? `Se envió el enlace de creación de contraseña al correo ${dest.email}.`
          : `Se generó un nuevo enlace de contraseña para ${dest.email}.`
      )
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No se pudo reenviar el enlace de contraseña.')
    }
  }

  const toggleGrafico = (id: string) => {
    setGraficosSeleccionados((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    )
  }

  const toggleSeccionGraficos = (items: CatalogoItemReporte[]) => {
    const idsSec = items.map((g) => g.id)
    setGraficosSeleccionados((prev) => {
      const todosMarcados = idsSec.every((id) => prev.includes(id))
      if (todosMarcados) {
        return prev.filter((id) => !idsSec.includes(id))
      }
      const nuevos = idsSec.filter((id) => !prev.includes(id))
      return [...prev, ...nuevos]
    })
  }

  const toggleColapsarSeccion = (nombreSec: string) => {
    setSeccionesColapsadas((prev) => ({
      ...prev,
      [nombreSec]: !prev[nombreSec],
    }))
  }

  const toggleIndicador = (id: string) => {
    setIndicadoresSeleccionados((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    )
  }

  const agregarNotaEspecifica = () => {
    if (!nuevaNotaContenido.trim()) return
    const nueva: NotaItemReporte = {
      id: `nota_${Date.now()}`,
      seccion: nuevaNotaSeccion,
      titulo: nuevaNotaTitulo.trim() || 'Observación Analítica',
      contenido: nuevaNotaContenido.trim(),
      fecha: new Date().toISOString().slice(0, 10),
    }
    setNotasItems((prev) => [...prev, nueva])
    setNuevaNotaTitulo('')
    setNuevaNotaContenido('')
  }

  const eliminarNotaEspecifica = (id: string) => {
    setNotasItems((prev) => prev.filter((n) => n.id !== id))
  }

  const calcularFechaExpiracion = (): string | null => {
    const ahora = new Date()
    if (tipoVigencia === 'indefinido') return null
    if (tipoVigencia === '7d') {
      ahora.setDate(ahora.getDate() + 7)
      return ahora.toISOString()
    }
    if (tipoVigencia === '30d') {
      ahora.setDate(ahora.getDate() + 30)
      return ahora.toISOString()
    }
    if (tipoVigencia === 'semestre') {
      ahora.setDate(ahora.getDate() + 120)
      return ahora.toISOString()
    }
    if (tipoVigencia === 'custom' && fechaExpiracionCustom) {
      return new Date(`${fechaExpiracionCustom}T23:59:59`).toISOString()
    }
    return null
  }

  const construirUrlReporte = (tokenAcceso: string) => {
    return `${window.location.origin}/reporte-compartido/${tokenAcceso}`
  }

  const construirUrlPortal = (tokenPortal: string) => {
    return `${window.location.origin}/mis-reportes/${tokenPortal}`
  }

  const copiarAlPortapapeles = (texto: string, clave: string) => {
    navigator.clipboard.writeText(texto)
    setCopiadoClave(clave)
    setTimeout(() => setCopiadoClave(null), 2200)
  }

  const handleCrearReporte = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMsg(null)
    setExitoMsg(null)

    if (!destinatarioEmail.trim() || !destinatarioNombre.trim()) {
      setErrorMsg('Seleccione un usuario Consultor de Reporte o complete sus datos para crearlo.')
      return
    }
    if (graficosSeleccionados.length === 0) {
      setErrorMsg('Seleccione al menos un gráfico para incluir en el reporte ejecutivo.')
      return
    }

    setGuardando(true)
    try {
      if (modoConsultor === 'vincular_existente' && candidatoSeleccionadoId) {
        const cand = usuariosCandidatos.find((u) => String(u.id) === String(candidatoSeleccionadoId))
        if (cand && (!cand.es_consultor || !cand.destinatario_id)) {
          await vincularUsuarioExistenteConsultor({
            usuario_id: cand.id,
            cargo: destinatarioCargo.trim() || cand.cargo_sugerido,
            unidad_academica: destinatarioUnidad.trim() || cand.unidad_sugerida,
          })
        }
      }

      const creado = await crearReporteCompartido({
        espacio_id: espacioIdInicial,
        destinatario_nombre: destinatarioNombre,
        destinatario_email: destinatarioEmail,
        destinatario_cargo: destinatarioCargo || 'Consultor Institucional',
        destinatario_unidad: destinatarioUnidad || 'Universidad Católica de Temuco',
        titulo_reporte: tituloReporte.trim() || 'Reporte Ejecutivo Institucional UCT',
        finalidad_reporte: finalidadReporte.trim() || 'Análisis de gestión institucional',
        nota_general: notaGeneral.trim() || undefined,
        notas_items: notasItems,
        fecha_inicio: fechaInicioInicial,
        fecha_fin: fechaFinInicial,
        modo_datos: modoDatos,
        filtros_bloqueados: filtrosIniciales,
        graficos_visibles: graficosSeleccionados,
        indicadores_visibles: indicadoresSeleccionados,
        permitir_exportacion: permitirExportacion,
        permitir_ia: permitirIA,
        expira_en: calcularFechaExpiracion(),
      })

      setReporteRecienCreado(creado)
      setExitoMsg(
        creado.correo_enviado
          ? `Reporte ${creado.codigo_corto} emitido y enviado automáticamente al correo ${creado.destinatario.email}.`
          : `Reporte ${creado.codigo_corto} emitido y vinculado a la cuenta de ${creado.destinatario.nombre_completo}.`
      )
      await cargarListado()
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'Error al generar el reporte ejecutivo compartido.')
    } finally {
      setGuardando(false)
    }
  }

  const handleToggleActivoReporte = async (rep: ReporteCompartidoResumen) => {
    try {
      const actualizado = await actualizarReporteCompartido(rep.id, { activo: !rep.activo })
      if (actualizado.activo && actualizado.correo_enviado) {
        setExitoMsg(`Reporte ${rep.codigo_corto} habilitado y notificado al correo ${rep.destinatario.email}.`)
      }
      await cargarListado()
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No se pudo cambiar el estado del enlace.')
    }
  }

  const handleReenviarCorreoReporte = async (rep: ReporteCompartidoResumen) => {
    try {
      const actualizado = await actualizarReporteCompartido(rep.id, { reenviar_correo: true })
      setExitoMsg(
        actualizado.correo_enviado
          ? `Enlace del reporte ${rep.codigo_corto} enviado por correo a ${rep.destinatario.email}.`
          : `Solicitud procesada para ${rep.destinatario.email} (verifique configuración SMTP si no llegó).`
      )
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No se pudo reenviar el correo.')
    }
  }

  const handleToggleIAReporte = async (rep: ReporteCompartidoResumen) => {
    try {
      await actualizarReporteCompartido(rep.id, { permitir_ia: !rep.permitir_ia })
      await cargarListado()
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No se pudo actualizar el permiso de IA.')
    }
  }

  const handleGuardarEdicionNotas = async () => {
    if (!reporteEditandoNotas) return
    setGuardando(true)
    try {
      await actualizarReporteCompartido(reporteEditandoNotas.id, {
        nota_general: reporteEditandoNotas.nota_general,
        notas_items: reporteEditandoNotas.notas_items,
      })
      setReporteEditandoNotas(null)
      await cargarListado()
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No se pudieron actualizar las notas del reporte.')
    } finally {
      setGuardando(false)
    }
  }

  const abrirEditorContenido = (rep: ReporteCompartidoResumen) => {
    const cat = obtenerCatalogoPorEspacio(rep.espacio_id, Boolean(rep.tiene_campana_24h))
    const idsCatalogo = new Set(cat.graficos.map((g) => g.id))
    let graficosIni = [...(rep.graficos_visibles || [])]
    if (graficosIni.includes('campana_24_horas') && rep.espacio_id === 1 && rep.tiene_campana_24h) {
      const granulares = cat.graficos.filter((g) => g.id.startsWith('campana_24h_')).map((g) => g.id)
      graficosIni = Array.from(new Set([...graficosIni.filter((id) => id !== 'campana_24_horas'), ...granulares]))
    } else {
      graficosIni = graficosIni.filter((id) => idsCatalogo.has(id))
    }

    const idsInd = new Set(cat.indicadores.map((i) => i.id))
    const indicadoresIni = (rep.indicadores_visibles || []).filter((id) => idsInd.has(id))

    setReporteEditandoNotas(null)
    setReporteEditandoContenido({
      reporte: rep,
      graficos: graficosIni,
      indicadores: indicadoresIni,
      colapsadas: {},
    })
  }

  const handleGuardarEdicionContenido = async () => {
    if (!reporteEditandoContenido) return
    if (reporteEditandoContenido.graficos.length === 0) {
      setErrorMsg('Debe mantener al menos un gráfico visible en el reporte.')
      return
    }
    setGuardando(true)
    setErrorMsg(null)
    try {
      await actualizarReporteCompartido(reporteEditandoContenido.reporte.id, {
        graficos_visibles: reporteEditandoContenido.graficos,
        indicadores_visibles: reporteEditandoContenido.indicadores,
      })
      setExitoMsg(
        `Gráficos y métricas del reporte ${reporteEditandoContenido.reporte.codigo_corto} actualizados correctamente.`
      )
      setReporteEditandoContenido(null)
      await cargarListado()
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No se pudieron actualizar los gráficos y métricas del reporte.')
    } finally {
      setGuardando(false)
    }
  }

  const handleEliminarReporte = async (repId: string) => {
    try {
      await eliminarReporteCompartido(repId)
      await cargarListado()
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No se pudo eliminar el reporte.')
    }
  }

  const handleToggleDestinatario = async (dest: DestinatarioReporteInfo) => {
    try {
      await actualizarEstadoDestinatario(dest.id, !dest.activo)
      await cargarListado()
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No se pudo cambiar el estado del destinatario.')
    }
  }

  const handleEliminarDestinatario = async (dest: DestinatarioReporteInfo) => {
    setErrorMsg(null)
    setExitoMsg(null)
    try {
      await eliminarDestinatarioReporte(dest.id)
      setDestinatarios((prev) => prev.filter((d) => d.id !== dest.id))
      setReportesEmitidos((prev) =>
        prev.filter(
          (r) =>
            r.destinatario?.id !== dest.id &&
            r.destinatario?.email?.toLowerCase() !== dest.email.toLowerCase()
        )
      )
      if (
        reporteRecienCreado?.destinatario?.id === dest.id ||
        reporteRecienCreado?.destinatario?.email?.toLowerCase() === dest.email.toLowerCase()
      ) {
        setReporteRecienCreado(null)
      }
      if (
        String(consultorSeleccionadoId) === String(dest.id) ||
        destinatarioEmail.toLowerCase() === dest.email.toLowerCase()
      ) {
        limpiarCamposConsultor()
      }
      setExitoMsg(`Usuario consultor ${dest.nombre_completo} (${dest.email}) y sus reportes asociados fueron eliminados.`)
      await cargarListado('')
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'No se pudo eliminar el usuario consultor.')
    }
  }

  if (!abierto) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-3 sm:p-6 overflow-y-auto">
      <div className="relative w-full max-w-5xl bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden my-auto max-h-[92vh] flex flex-col">
        {/* Cabecera Institucional UCT (#003865 + Logo Oficial + Dorado #C59B27) */}
        <div className="flex items-center justify-between px-6 py-4 bg-uct-blue-primary text-white border-b-2 border-uct-gold">
          <div className="flex items-center gap-3.5">
            <div className="h-10 px-2.5 py-1 rounded-lg bg-white flex items-center justify-center border border-uct-gold/50 shadow-xs shrink-0">
              <img src="/uct_logo.png" alt="UCT" className="h-7 w-auto object-contain" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-uct-gold">
                  Universidad Católica de Temuco — Campus San Francisco
                </span>
              </div>
              <h2 className="text-base sm:text-lg font-bold text-white leading-tight">
                Emisión de Reportes Ejecutivos y Gestión de Usuarios Consultores
              </h2>
            </div>
          </div>
          <button
            onClick={onCerrar}
            className="p-2 rounded-lg text-white/80 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            title="Cerrar ventana"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Barra de pestañas institucional clara */}
        <div className="flex flex-wrap items-center gap-2 px-6 pt-3 bg-slate-100 border-b border-slate-200">
          <button
            type="button"
            onClick={() => setPestanaActiva('emitir')}
            className={`px-4 py-2.5 text-xs font-bold rounded-t-xl border-t border-x transition-colors flex items-center gap-2 cursor-pointer ${
              pestanaActiva === 'emitir'
                ? 'bg-white text-uct-blue-primary border-slate-200 -mb-px shadow-2xs'
                : 'bg-transparent border-transparent text-slate-600 hover:text-uct-blue-primary'
            }`}
          >
            <Share2 className="w-3.5 h-3.5" />
            1. Emitir Reporte con Filtros Actuales
          </button>
          <button
            type="button"
            onClick={() => setPestanaActiva('consultores')}
            className={`px-4 py-2.5 text-xs font-bold rounded-t-xl border-t border-x transition-colors flex items-center gap-2 cursor-pointer ${
              pestanaActiva === 'consultores'
                ? 'bg-white text-uct-blue-primary border-slate-200 -mb-px shadow-2xs'
                : 'bg-transparent border-transparent text-slate-600 hover:text-uct-blue-primary'
            }`}
          >
            <UserCheck className="w-3.5 h-3.5" />
            2. Usuarios Consultores de Reporte ({destinatarios.length})
          </button>
          <button
            type="button"
            onClick={() => setPestanaActiva('historial')}
            className={`px-4 py-2.5 text-xs font-bold rounded-t-xl border-t border-x transition-colors flex items-center gap-2 cursor-pointer ${
              pestanaActiva === 'historial'
                ? 'bg-white text-uct-blue-primary border-slate-200 -mb-px shadow-2xs'
                : 'bg-transparent border-transparent text-slate-600 hover:text-uct-blue-primary'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            3. Historial de Reportes Emitidos ({reportesEmitidos.length})
          </button>
        </div>

        {/* Cuerpo principal con fondo institucional claro */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1 bg-slate-50/70 text-slate-800">
          {errorMsg && (
            <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-800 text-xs font-medium flex items-center justify-between">
              <span>{errorMsg}</span>
              <button onClick={() => setErrorMsg(null)} className="text-red-600 hover:text-red-900">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {exitoMsg && (
            <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-emerald-900 font-bold text-xs sm:text-sm">
                  <ShieldCheck className="w-5 h-5 text-emerald-600 shrink-0" />
                  <span>{exitoMsg}</span>
                </div>
                <button onClick={() => setExitoMsg(null)} className="text-emerald-700 hover:text-emerald-950">
                  <X className="w-4 h-4" />
                </button>
              </div>

              {reporteRecienCreado && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                  <div className="p-3 rounded-xl bg-white border border-slate-200 space-y-1.5">
                    <span className="text-[11px] font-bold text-uct-blue-primary uppercase tracking-wider">
                      Enlace Directo al Reporte ({reporteRecienCreado.codigo_corto})
                    </span>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        readOnly
                        value={construirUrlReporte(reporteRecienCreado.token_acceso)}
                        className="w-full bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 font-mono"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          copiarAlPortapapeles(
                            construirUrlReporte(reporteRecienCreado.token_acceso),
                            'nuevo_rep'
                          )
                        }
                        className="px-3 py-1.5 rounded-lg bg-uct-blue-primary hover:bg-uct-blue-secondary text-white text-xs font-semibold flex items-center gap-1.5 shrink-0 cursor-pointer"
                      >
                        {copiadoClave === 'nuevo_rep' ? (
                          <Check className="w-3.5 h-3.5" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                        {copiadoClave === 'nuevo_rep' ? 'Copiado' : 'Copiar'}
                      </button>
                      <a
                        href={construirUrlReporte(reporteRecienCreado.token_acceso)}
                        target="_blank"
                        rel="noreferrer"
                        className="p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-uct-blue-primary border border-slate-200"
                        title="Abrir reporte en nueva pestaña"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    </div>
                  </div>

                  <div className="p-3 rounded-xl bg-white border border-slate-200 space-y-1.5">
                    <span className="text-[11px] font-bold text-uct-blue-primary uppercase tracking-wider">
                      Bandeja Histórica del Consultor ({reporteRecienCreado.destinatario.nombre_completo})
                    </span>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        readOnly
                        value={construirUrlPortal(reporteRecienCreado.destinatario.token_portal)}
                        className="w-full bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 font-mono"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          copiarAlPortapapeles(
                            construirUrlPortal(reporteRecienCreado.destinatario.token_portal),
                            'nuevo_portal'
                          )
                        }
                        className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold flex items-center gap-1.5 shrink-0 cursor-pointer"
                      >
                        {copiadoClave === 'nuevo_portal' ? (
                          <Check className="w-3.5 h-3.5" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                        {copiadoClave === 'nuevo_portal' ? 'Copiado' : 'Copiar Bandeja'}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {pestanaActiva === 'emitir' && (
            <form onSubmit={handleCrearReporte} className="space-y-5">
              {/* BLOQUE A: Resumen Automático de los Filtros y Período ya Seleccionados en Pantalla */}
              <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                  <div className="flex items-center gap-2">
                    <Lock className="w-4 h-4 text-uct-blue-primary" />
                    <h3 className="text-xs sm:text-sm font-bold text-uct-blue-primary">
                      Alcance Sincronizado con los Filtros Activos en su Pantalla (Sellado en Servidor)
                    </h3>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {totalRegistrosInicial !== undefined && (
                      <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-900 border border-amber-300">
                        {totalRegistrosInicial.toLocaleString('es-CL')} registros en este filtro
                      </span>
                    )}
                    <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-blue-50 text-uct-blue-primary border border-blue-200">
                      {espacioIdInicial === 1 ? 'Biblioteca Campus San Francisco' : 'Estacionamiento Campus San Francisco'}
                    </span>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-uct-blue-primary text-white font-semibold">
                    <Calendar className="w-3.5 h-3.5 text-uct-gold" />
                    Período: {fechaInicioInicial} al {fechaFinInicial}
                    {etiquetaPeriodoInicial ? ` (${etiquetaPeriodoInicial})` : ''}
                  </span>
                  {resumenFiltrosPantalla.map((chip) => (
                    <span
                      key={chip.etiqueta}
                      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border ${
                        chip.destacado
                          ? 'bg-blue-50/90 border-uct-blue-primary/40 text-uct-blue-primary'
                          : 'bg-slate-100 border-slate-200 text-slate-700'
                      }`}
                    >
                      <span className={chip.destacado ? 'text-uct-blue-primary/80 font-semibold' : 'text-slate-500 font-medium'}>
                        {chip.etiqueta}:
                      </span>
                      <strong className={chip.destacado ? 'text-uct-blue-primary font-bold' : 'text-slate-900'}>
                        {chip.valor}
                      </strong>
                    </span>
                  ))}
                </div>
                <p className="text-[11px] text-slate-500">
                  Estos valores se toman automáticamente de los filtros que usted tiene seleccionados ahora mismo en el
                  dashboard. El destinatario recibirá únicamente los datos de este alcance y <strong>no podrá cambiar ni quitar ningún filtro</strong>.
                </p>
              </div>

              {/* BLOQUE B: Selección o Creación del Usuario Consultor_Reporte */}
              <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                  <div className="flex items-center gap-2">
                    <UserCheck className="w-4 h-4 text-uct-blue-primary" />
                    <h3 className="text-xs sm:text-sm font-bold text-uct-blue-primary">
                      Destinatario: Usuario Consultor de Reporte
                    </h3>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {destinatarios.length > 0 && (
                      <button
                        type="button"
                        onClick={() => {
                          setModoConsultor('seleccionar')
                          if (destinatarios[0]) seleccionarConsultorExistente(destinatarios[0])
                        }}
                        className={`px-3 py-1 rounded-lg text-xs font-semibold border cursor-pointer ${
                          modoConsultor === 'seleccionar'
                            ? 'bg-uct-blue-primary text-white border-uct-blue-primary'
                            : 'bg-slate-100 text-slate-700 border-slate-200 hover:bg-slate-200'
                        }`}
                      >
                        Seleccionar Consultor Existente ({destinatarios.length})
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setModoConsultor('vincular_existente')
                        if (usuariosCandidatos.length > 0 && !candidatoSeleccionadoId) {
                          seleccionarCandidatoParaReporte(usuariosCandidatos[0])
                        }
                      }}
                      className={`px-3 py-1 rounded-lg text-xs font-semibold border flex items-center gap-1.5 cursor-pointer ${
                        modoConsultor === 'vincular_existente'
                          ? 'bg-uct-blue-primary text-white border-uct-blue-primary'
                          : 'bg-blue-50 text-uct-blue-primary border-blue-200 hover:bg-blue-100'
                      }`}
                    >
                      <Link2 className="w-3.5 h-3.5 text-uct-gold" />
                      Vincular Usuario del Campus ({usuariosCandidatos.length})
                    </button>
                    <button
                      type="button"
                      onClick={limpiarCamposConsultor}
                      className={`px-3 py-1 rounded-lg text-xs font-semibold border flex items-center gap-1 cursor-pointer ${
                        modoConsultor === 'nuevo'
                          ? 'bg-uct-blue-primary text-white border-uct-blue-primary'
                          : 'bg-amber-50 text-amber-900 border-amber-300 hover:bg-amber-100'
                      }`}
                    >
                      <UserPlus className="w-3.5 h-3.5" />
                      Nuevo Consultor Externo
                    </button>
                  </div>
                </div>

                {modoConsultor === 'seleccionar' && destinatarios.length > 0 ? (
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Seleccione la Cuenta del Consultor Destinatario
                      </label>
                      <select
                        value={consultorSeleccionadoId}
                        onChange={(e) => {
                          const enc = destinatarios.find((d) => String(d.id) === e.target.value)
                          if (enc) seleccionarConsultorExistente(enc)
                        }}
                        className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3 py-2 text-xs font-medium text-slate-800 focus:outline-none focus:border-uct-blue-primary"
                      >
                        {destinatarios.map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.nombre_completo} ({d.email}) — {d.cargo} | {d.unidad_academica}{' '}
                            {d.cuenta_activada ? '[Contraseña Activa]' : '[Pendiente Crear Contraseña]'}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs bg-slate-50 p-3 rounded-xl border border-slate-200">
                      <div>
                        <span className="text-slate-500">Correo Institucional:</span>{' '}
                        <strong className="text-slate-800">{destinatarioEmail}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500">Cargo:</span>{' '}
                        <strong className="text-slate-800">{destinatarioCargo}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500">Carrera / Unidad:</span>{' '}
                        <strong className="text-slate-800">{destinatarioUnidad}</strong>
                      </div>
                    </div>
                  </div>
                ) : modoConsultor === 'vincular_existente' ? (
                  <div className="space-y-3.5">
                    <div className="p-3 rounded-xl bg-blue-50/80 border border-blue-200 text-xs text-slate-700 space-y-1">
                      <div className="flex items-center gap-2 font-bold text-uct-blue-primary">
                        <ShieldCheck className="w-4 h-4 text-uct-gold" />
                        <span>Vinculación de Usuario del Campus (Sin cambio de contraseña)</span>
                      </div>
                      <p className="text-[11px] text-slate-600 leading-relaxed">
                        Seleccione una persona ya registrada en la plataforma institucional del Campus. Se le otorgará el rol{' '}
                        <strong>Consultor de Reportes</strong> manteniendo sus credenciales vigentes. Podrá ingresar directamente al
                        reporte si ya tiene una sesión activa (SSO) o autenticarse con su contraseña institucional habitual.
                      </p>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[11px] font-bold text-slate-700 mb-1">
                          Usuario Activo del Campus UCT *
                        </label>
                        <select
                          value={candidatoSeleccionadoId}
                          onChange={(e) => {
                            const cand = usuariosCandidatos.find((u) => String(u.id) === e.target.value)
                            if (cand) seleccionarCandidatoParaReporte(cand)
                          }}
                          className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3 py-2 text-xs font-medium text-slate-800 focus:outline-none focus:border-uct-blue-primary"
                        >
                          <option value="">-- Seleccione un usuario institucional --</option>
                          {usuariosCandidatos
                            .filter((u) => {
                              if (!candidatoFiltroTexto.trim()) return true
                              const q = candidatoFiltroTexto.toLowerCase()
                              return (
                                u.nombre_completo.toLowerCase().includes(q) ||
                                u.email.toLowerCase().includes(q) ||
                                u.cargo_sugerido.toLowerCase().includes(q)
                              )
                            })
                            .map((u) => (
                              <option key={u.id} value={u.id}>
                                {u.nombre_completo} ({u.email}) — [{u.roles.join(', ')}]{' '}
                                {u.es_consultor ? '• [Rol Consultor Activo]' : '• [Vincular Rol]'}
                              </option>
                            ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-[11px] font-bold text-slate-700 mb-1">
                          Filtrar por Nombre, Cargo o Correo
                        </label>
                        <div className="relative">
                          <input
                            type="text"
                            placeholder="Buscar en usuarios del campus..."
                            value={candidatoFiltroTexto}
                            onChange={(e) => setCandidatoFiltroTexto(e.target.value)}
                            className="w-full bg-white border border-slate-300 rounded-xl pl-8 pr-3 py-2 text-xs text-slate-800 focus:outline-none focus:border-uct-blue-primary"
                          />
                          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 bg-slate-50 p-3 rounded-xl border border-slate-200">
                      <div>
                        <label className="block text-[10px] font-bold text-slate-500 mb-1 uppercase tracking-wider">
                          Nombre Completo
                        </label>
                        <input
                          type="text"
                          readOnly
                          value={destinatarioNombre}
                          className="w-full bg-slate-100 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 font-medium cursor-not-allowed"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] font-bold text-slate-500 mb-1 uppercase tracking-wider">
                          Correo Institucional
                        </label>
                        <input
                          type="email"
                          readOnly
                          value={destinatarioEmail}
                          className="w-full bg-slate-100 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 font-medium cursor-not-allowed"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] font-bold text-slate-700 mb-1 uppercase tracking-wider">
                          Cargo Institucional *
                        </label>
                        <input
                          type="text"
                          required
                          value={destinatarioCargo}
                          onChange={(e) => setDestinatarioCargo(e.target.value)}
                          placeholder="Ej. Directora / Jefe de Carrera"
                          className="w-full bg-white border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-800"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] font-bold text-slate-700 mb-1 uppercase tracking-wider">
                          Carrera / Unidad Académica *
                        </label>
                        <input
                          type="text"
                          required
                          value={destinatarioUnidad}
                          onChange={(e) => setDestinatarioUnidad(e.target.value)}
                          placeholder="Ej. Vicerrectoría / Facultad"
                          className="w-full bg-white border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-800"
                        />
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                      <div className="text-[11px] text-slate-500 flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                        <span>Se asociará automáticamente a la cuenta del usuario sin pedir cambio de contraseña.</span>
                      </div>
                      {candidatoSeleccionadoId && (
                        <button
                          type="button"
                          onClick={handleVincularCandidatoDirecto}
                          disabled={vinculandoCandidato}
                          className="px-3 py-1.5 rounded-lg bg-white border border-uct-blue-primary text-uct-blue-primary hover:bg-blue-50 text-xs font-semibold flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                        >
                          <Link2 className="w-3.5 h-3.5 text-uct-gold" />
                          {vinculandoCandidato ? 'Vinculando...' : 'Confirmar Vinculación de Rol Ahora'}
                        </button>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="p-3 rounded-xl bg-blue-50/70 border border-blue-200 text-xs text-slate-700">
                      Al registrar un nuevo <strong>Usuario Consultor de Reporte</strong>, el sistema creará su cuenta
                      y le enviará un correo institucional UCT para que defina su contraseña personal y acceda a su
                      bandeja de reportes.
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                      <div>
                        <label className="block text-[11px] font-bold text-slate-700 mb-1">
                          Nombre Completo *
                        </label>
                        <input
                          type="text"
                          required
                          placeholder="Ej. Dra. María Paz Riquelme"
                          value={destinatarioNombre}
                          onChange={(e) => setDestinatarioNombre(e.target.value)}
                          className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-bold text-slate-700 mb-1">
                          Correo Institucional *
                        </label>
                        <input
                          type="email"
                          required
                          placeholder="Ej. mriquelme@uct.cl"
                          value={destinatarioEmail}
                          onChange={(e) => setDestinatarioEmail(e.target.value)}
                          className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-bold text-slate-700 mb-1">
                          Cargo Institucional *
                        </label>
                        <input
                          type="text"
                          required
                          placeholder="Ej. Jefa de Carrera / Decano"
                          value={destinatarioCargo}
                          onChange={(e) => setDestinatarioCargo(e.target.value)}
                          className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-bold text-slate-700 mb-1">
                          Carrera / Unidad Académica *
                        </label>
                        <input
                          type="text"
                          required
                          placeholder="Ej. Ingeniería Civil Informática"
                          value={destinatarioUnidad}
                          onChange={(e) => setDestinatarioUnidad(e.target.value)}
                          className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                        />
                      </div>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-slate-100">
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 mb-1">
                      Título del Reporte Ejecutivo *
                    </label>
                    <input
                      type="text"
                      required
                      value={tituloReporte}
                      onChange={(e) => setTituloReporte(e.target.value)}
                      className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 mb-1">
                      Finalidad / Motivo del Reporte *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="Ej. Solicitud Dirección de Carrera / Acreditación CNA"
                      value={finalidadReporte}
                      onChange={(e) => setFinalidadReporte(e.target.value)}
                      className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                    />
                  </div>
                </div>
              </div>

              {/* BLOQUE C: Selección de Métricas/Indicadores y Gráficos */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                    <h4 className="text-xs font-bold text-uct-blue-primary uppercase tracking-wider flex items-center gap-2">
                      <Layers className="w-4 h-4 text-uct-blue-primary" />
                      Métricas e Indicadores Ejecutivos ({indicadoresSeleccionados.length})
                    </h4>
                    <button
                      type="button"
                      onClick={() =>
                        setIndicadoresSeleccionados(
                          indicadoresSeleccionados.length === catalogoActual.indicadores.length
                            ? []
                            : catalogoActual.indicadores.map((i) => i.id)
                        )
                      }
                      className="text-[11px] font-semibold text-uct-blue-primary hover:underline cursor-pointer"
                    >
                      {indicadoresSeleccionados.length === catalogoActual.indicadores.length
                        ? 'Desmarcar todos'
                        : 'Seleccionar todos'}
                    </button>
                  </div>
                  <div className="grid grid-cols-1 gap-1.5 max-h-52 overflow-y-auto pr-1">
                    {catalogoActual.indicadores.map((ind) => {
                      const activo = indicadoresSeleccionados.includes(ind.id)
                      return (
                        <label
                          key={ind.id}
                          className={`flex items-center gap-2.5 p-2 rounded-lg border text-xs cursor-pointer transition-colors ${
                            activo
                              ? 'bg-blue-50/80 border-uct-blue-primary/40 text-uct-blue-primary font-semibold'
                              : 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={activo}
                            onChange={() => toggleIndicador(ind.id)}
                            className="rounded border-slate-300 text-uct-blue-primary"
                          />
                          <span>{ind.titulo}</span>
                        </label>
                      )
                    })}
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
                    <h4 className="text-xs font-bold text-uct-blue-primary uppercase tracking-wider flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 text-uct-blue-primary" />
                      <span>
                        Gráficos Incluidos en el Reporte ({graficosSeleccionados.length} / {catalogoActual.graficos.length})
                      </span>
                    </h4>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setGraficosSeleccionados(catalogoActual.graficos.map((g) => g.id))}
                        className="px-2 py-0.5 rounded border border-uct-blue-primary/30 bg-blue-50/70 text-[11px] font-semibold text-uct-blue-primary hover:bg-blue-100 cursor-pointer"
                      >
                        Seleccionar todo
                      </button>
                      <button
                        type="button"
                        onClick={() => setGraficosSeleccionados([])}
                        className="px-2 py-0.5 rounded border border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-600 hover:bg-slate-100 cursor-pointer"
                      >
                        Ninguno
                      </button>
                    </div>
                  </div>

                  <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                    {seccionesGraficos.map((sec) => {
                      const colapsada = Boolean(seccionesColapsadas[sec.nombre])
                      const cantSel = sec.items.filter((g) => graficosSeleccionados.includes(g.id)).length
                      const todosSec = cantSel === sec.items.length && sec.items.length > 0
                      const badgeClase =
                        cantSel === 0
                          ? 'bg-slate-100 text-slate-500 border-slate-200'
                          : todosSec
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-blue-50 text-uct-blue-primary border-uct-blue-primary/30'

                      return (
                        <div key={sec.nombre} className="rounded-lg border border-slate-200 overflow-hidden bg-slate-50/50">
                          <div className="flex items-center justify-between gap-2 px-2.5 py-2 bg-slate-100/80 border-b border-slate-200/70">
                            <button
                              type="button"
                              onClick={() => toggleColapsarSeccion(sec.nombre)}
                              className="flex items-center gap-1.5 text-left text-xs font-bold text-slate-800 hover:text-uct-blue-primary cursor-pointer min-w-0"
                            >
                              {colapsada ? (
                                <ChevronRight className="w-3.5 h-3.5 shrink-0 text-slate-500" />
                              ) : (
                                <ChevronDown className="w-3.5 h-3.5 shrink-0 text-slate-500" />
                              )}
                              <span className="truncate">{sec.nombre}</span>
                              <span className={`px-1.5 py-0.2 rounded-full border text-[10px] font-semibold shrink-0 ${badgeClase}`}>
                                {cantSel}/{sec.items.length}
                              </span>
                            </button>

                            <button
                              type="button"
                              onClick={() => toggleSeccionGraficos(sec.items)}
                              className={`px-2 py-0.5 rounded text-[11px] font-semibold shrink-0 transition-colors cursor-pointer ${
                                todosSec
                                  ? 'bg-white border border-slate-300 text-slate-700 hover:bg-slate-50'
                                  : 'bg-uct-blue-primary text-white hover:bg-uct-blue-secondary'
                              }`}
                            >
                              {todosSec ? 'Quitar sección' : 'Toda la sección'}
                            </button>
                          </div>

                          {!colapsada && (
                            <div className="p-2 grid grid-cols-1 gap-1.5 bg-white">
                              {sec.items.map((graf) => {
                                const activo = graficosSeleccionados.includes(graf.id)
                                return (
                                  <label
                                    key={graf.id}
                                    className={`flex items-center gap-2.5 p-2 rounded-lg border text-xs cursor-pointer transition-colors ${
                                      activo
                                        ? 'bg-blue-50/80 border-uct-blue-primary/40 text-uct-blue-primary font-semibold'
                                        : 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100'
                                    }`}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={activo}
                                      onChange={() => toggleGrafico(graf.id)}
                                      className="rounded border-slate-300 text-uct-blue-primary"
                                    />
                                    <span>{graf.titulo}</span>
                                  </label>
                                )
                              })}
                            </div>
                          )}
                        </div>
                      )
                    })}

                    {espacioIdInicial === 1 && !tieneCampana24hActiva && (
                      <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-[11px] text-slate-600">
                        <Info className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
                        <span>
                          La sección <strong>5. Campaña 24 Horas Exámenes</strong> no está disponible porque el período seleccionado no contiene campañas 24 horas activas.
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* BLOQUE D: Notas del Emisor y Configuración de Vigencia / IA */}
              <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-4">
                <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
                  <MessageSquarePlus className="w-4 h-4 text-uct-blue-primary" />
                  <h3 className="text-xs sm:text-sm font-bold text-uct-blue-primary">
                    Notas Ejecutivas del Emisor y Control de Acceso
                  </h3>
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-slate-700 mb-1">
                    Nota Ejecutiva General / Observaciones para el Solicitante (Opcional)
                  </label>
                  <textarea
                    rows={2}
                    placeholder="Agregue conclusiones ejecutivas, contexto sobre suspensiones o comentarios que verá el destinatario en el encabezado del reporte..."
                    value={notaGeneral}
                    onChange={(e) => setNotaGeneral(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                  />
                </div>

                {/* Notas por gráfico */}
                <div className="space-y-2">
                  <label className="block text-[11px] font-bold text-slate-700">
                    Añadir Nota Específica a un Gráfico o Sección (Opcional)
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-12 gap-2">
                    <select
                      value={nuevaNotaSeccion}
                      onChange={(e) => setNuevaNotaSeccion(e.target.value)}
                      className="sm:col-span-3 bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-800"
                    >
                      <option value="general">Nota General</option>
                      {seccionesGraficos.map((sec) => (
                        <optgroup key={sec.nombre} label={sec.nombre}>
                          {sec.items.map((g) => (
                            <option key={g.id} value={g.id}>
                              {g.titulo}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                    <input
                      type="text"
                      placeholder="Título breve"
                      value={nuevaNotaTitulo}
                      onChange={(e) => setNuevaNotaTitulo(e.target.value)}
                      className="sm:col-span-3 bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-800"
                    />
                    <input
                      type="text"
                      placeholder="Observación..."
                      value={nuevaNotaContenido}
                      onChange={(e) => setNuevaNotaContenido(e.target.value)}
                      className="sm:col-span-4 bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-800"
                    />
                    <button
                      type="button"
                      onClick={agregarNotaEspecifica}
                      className="sm:col-span-2 px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-300 text-uct-blue-primary text-xs font-bold flex items-center justify-center gap-1 cursor-pointer"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Agregar
                    </button>
                  </div>

                  {notasItems.length > 0 && (
                    <div className="space-y-1.5 pt-1">
                      {notasItems.map((n) => (
                        <div
                          key={n.id}
                          className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-amber-50/70 border border-amber-200 text-xs"
                        >
                          <div>
                            <strong className="text-uct-blue-primary">[{n.seccion}] {n.titulo}: </strong>
                            <span className="text-slate-700">{n.contenido}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => eliminarNotaEspecifica(n.id)}
                            className="text-slate-400 hover:text-red-600 p-1"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Vigencia y Permisos */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3 border-t border-slate-100">
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 mb-1">
                      Vigencia del Reporte
                    </label>
                    <div className="flex gap-2">
                      <select
                        value={tipoVigencia}
                        onChange={(e) => setTipoVigencia(e.target.value as any)}
                        className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                      >
                        <option value="7d">7 Días</option>
                        <option value="30d">30 Días (Recomendado)</option>
                        <option value="semestre">Semestral (120 Días)</option>
                        <option value="indefinido">Indefinido (Control manual)</option>
                        <option value="custom">Fecha específica...</option>
                      </select>
                      {tipoVigencia === 'custom' && (
                        <input
                          type="date"
                          value={fechaExpiracionCustom}
                          onChange={(e) => setFechaExpiracionCustom(e.target.value)}
                          className="bg-slate-50 border border-slate-300 rounded-lg px-2 py-1.5 text-xs text-slate-800"
                        />
                      )}
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1">
                      Período institucional sellado e inmutable para auditoría.
                    </p>
                  </div>

                  <div className="flex flex-col justify-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
                    <label className="flex items-center justify-between cursor-pointer">
                      <span className="text-xs text-slate-700 font-semibold">
                        Habilitar Asistente IA en el Reporte
                      </span>
                      <input
                        type="checkbox"
                        checked={permitirIA}
                        onChange={(e) => setPermitirIA(e.target.checked)}
                        className="rounded border-slate-300 text-uct-blue-primary"
                      />
                    </label>
                    <label className="flex items-center justify-between cursor-pointer">
                      <span className="text-xs text-slate-700 font-medium">Permitir Impresión / PDF</span>
                      <input
                        type="checkbox"
                        checked={permitirExportacion}
                        onChange={(e) => setPermitirExportacion(e.target.checked)}
                        className="rounded border-slate-300 text-uct-blue-primary"
                      />
                    </label>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-1">
                <button
                  type="button"
                  onClick={onCerrar}
                  className="px-4 py-2.5 rounded-xl bg-white hover:bg-slate-100 border border-slate-300 text-slate-700 text-xs font-bold cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-5 py-2.5 rounded-xl bg-uct-blue-primary hover:bg-uct-blue-secondary disabled:opacity-50 text-white text-xs font-bold flex items-center gap-2 shadow-md cursor-pointer"
                >
                  <Mail className="w-4 h-4 text-uct-gold" />
                  {guardando
                    ? 'Emitiendo y enviando al correo...'
                    : 'Emitir Reporte Ejecutivo y Enviar al Correo'}
                </button>
              </div>
            </form>
          )}

          {pestanaActiva === 'consultores' && (
            <div className="space-y-5">
              {/* Selector de modo para alta o vinculación de Consultores */}
              <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
                <button
                  type="button"
                  onClick={() => setSubpestanaConsultor('vincular')}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer ${
                    subpestanaConsultor === 'vincular'
                      ? 'bg-uct-blue-primary text-white shadow-xs'
                      : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                  }`}
                >
                  <Link2 className="w-3.5 h-3.5 text-uct-gold" />
                  Vincular Usuario del Campus ({usuariosCandidatos.length})
                </button>
                <button
                  type="button"
                  onClick={() => setSubpestanaConsultor('nuevo')}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer ${
                    subpestanaConsultor === 'nuevo'
                      ? 'bg-uct-blue-primary text-white shadow-xs'
                      : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                  }`}
                >
                  <UserPlus className="w-3.5 h-3.5" />
                  Crear Nuevo Consultor Externo (Con Invitación)
                </button>
              </div>

              {subpestanaConsultor === 'vincular' ? (
                /* Formulario para vincular usuario institucional existente */
                <form
                  onSubmit={handleVincularEnPestana2}
                  className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-3"
                >
                  <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
                    <Link2 className="w-4 h-4 text-uct-blue-primary" />
                    <h3 className="text-xs sm:text-sm font-bold text-uct-blue-primary">
                      Vincular Usuario Existente del Campus UCT (Conserva su contraseña habitual)
                    </h3>
                  </div>
                  <p className="text-[11px] text-slate-600">
                    Asigna el rol <strong>Consultor de Reportes</strong> a un integrante del campus ya registrado en el
                    sistema. No se generará enlace de cambio de contraseña; el usuario ingresará con su sesión activa (SSO)
                    o sus credenciales habituales.
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-[11px] font-bold text-slate-700 mb-1">
                        Usuario Institucional UCT *
                      </label>
                      <select
                        required
                        value={vincularP2UsuarioId}
                        onChange={(e) => {
                          const id = e.target.value
                          setVincularP2UsuarioId(id)
                          const c = usuariosCandidatos.find((u) => String(u.id) === id)
                          if (c) {
                            setVincularP2Cargo(c.cargo_sugerido)
                            setVincularP2Unidad(c.unidad_sugerida)
                          }
                        }}
                        className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                      >
                        <option value="">-- Seleccionar usuario activo --</option>
                        {usuariosCandidatos.map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.nombre_completo} ({u.email}) — [{u.roles.join(', ')}]{' '}
                            {u.es_consultor ? '• [Rol Consultor Activo]' : '• [Vincular]'}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-slate-700 mb-1">
                        Cargo Institucional *
                      </label>
                      <input
                        type="text"
                        required
                        placeholder="Ej. Directivo UCT / Jefe de Carrera"
                        value={vincularP2Cargo}
                        onChange={(e) => setVincularP2Cargo(e.target.value)}
                        className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-slate-700 mb-1">
                        Carrera / Unidad Académica *
                      </label>
                      <input
                        type="text"
                        required
                        placeholder="Ej. Vicerrectoría Académica / Ingeniería"
                        value={vincularP2Unidad}
                        onChange={(e) => setVincularP2Unidad(e.target.value)}
                        className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                      />
                    </div>
                  </div>
                  <div className="flex justify-end pt-1">
                    <button
                      type="submit"
                      disabled={guardando || !vincularP2UsuarioId}
                      className="px-4 py-2 rounded-xl bg-uct-blue-primary hover:bg-uct-blue-secondary text-white text-xs font-bold flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                    >
                      <Link2 className="w-3.5 h-3.5 text-uct-gold" />
                      {guardando ? 'Vinculando al rol...' : 'Vincular Usuario al Rol Consultor_Reporte'}
                    </button>
                  </div>
                </form>
              ) : (
                /* Formulario para dar de alta un usuario Consultor_Reporte externo y enviarle correo de contraseña */
                <form
                  onSubmit={handleRegistrarConsultorDirecto}
                  className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-3"
                >
                  <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
                    <UserPlus className="w-4 h-4 text-uct-blue-primary" />
                    <h3 className="text-xs sm:text-sm font-bold text-uct-blue-primary">
                      Crear Nuevo Usuario Consultor de Reportes (Envía invitación para definir contraseña)
                    </h3>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                    <input
                      type="text"
                      required
                      placeholder="Nombre completo *"
                      value={nuevoConsultorNombre}
                      onChange={(e) => setNuevoConsultorNombre(e.target.value)}
                      className="bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                    />
                    <input
                      type="email"
                      required
                      placeholder="Correo institucional (@uct.cl) *"
                      value={nuevoConsultorEmail}
                      onChange={(e) => setNuevoConsultorEmail(e.target.value)}
                      className="bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                    />
                    <input
                      type="text"
                      required
                      placeholder="Cargo (ej. Jefe de Carrera) *"
                      value={nuevoConsultorCargo}
                      onChange={(e) => setNuevoConsultorCargo(e.target.value)}
                      className="bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                    />
                    <input
                      type="text"
                      required
                      placeholder="Carrera o Unidad Académica *"
                      value={nuevoConsultorUnidad}
                      onChange={(e) => setNuevoConsultorUnidad(e.target.value)}
                      className="bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                    />
                  </div>
                  <div className="flex justify-end">
                    <button
                      type="submit"
                      disabled={guardando}
                      className="px-4 py-2 rounded-xl bg-uct-blue-primary hover:bg-uct-blue-secondary text-white text-xs font-bold flex items-center gap-1.5 cursor-pointer"
                    >
                      <KeyRound className="w-3.5 h-3.5 text-uct-gold" />
                      {guardando ? 'Registrando y enviando correo...' : 'Crear Cuenta Consultor y Enviar Enlace de Contraseña'}
                    </button>
                  </div>
                </form>
              )}

              <div className="space-y-2.5">
                {destinatarios.length === 0 ? (
                  <div className="text-center py-10 bg-white rounded-xl border border-slate-200 text-slate-500 text-xs">
                    No hay usuarios Consultores de Reporte registrados todavía.
                  </div>
                ) : (
                  destinatarios.map((dest) => (
                    <div
                      key={dest.id}
                      className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs flex flex-wrap items-center justify-between gap-3"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-bold text-uct-blue-primary">{dest.nombre_completo}</span>
                          <span className="text-xs font-medium text-slate-600">({dest.email})</span>
                          <span
                            className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${
                              dest.cuenta_activada
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                : 'bg-amber-50 text-amber-800 border border-amber-200'
                            }`}
                          >
                            {dest.cuenta_activada ? 'Contraseña Creada' : 'Pendiente Definir Contraseña'}
                          </span>
                          <span
                            className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${
                              dest.activo
                                ? 'bg-blue-50 text-uct-blue-primary border border-blue-200'
                                : 'bg-red-50 text-red-700 border border-red-200'
                            }`}
                          >
                            {dest.activo ? 'Habilitado' : 'Suspendido'}
                          </span>
                        </div>
                        <p className="text-xs text-slate-600">
                          <strong>Cargo:</strong> {dest.cargo} | <strong>Unidad / Carrera:</strong>{' '}
                          {dest.unidad_academica} | <strong>Reportes en su bandeja:</strong> {dest.total_reportes || 0}
                        </p>
                      </div>

                      <div className="flex items-center gap-2 flex-wrap">
                        <button
                          type="button"
                          onClick={() => {
                            seleccionarConsultorExistente(dest)
                            setPestanaActiva('emitir')
                          }}
                          className="px-3 py-1.5 rounded-lg bg-uct-blue-primary hover:bg-uct-blue-secondary text-white text-xs font-semibold cursor-pointer"
                        >
                          Enviar Nuevo Reporte
                        </button>
                        <button
                          type="button"
                          onClick={() => handleReenviarLinkPasswordConsultor(dest)}
                          className="px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-200 text-uct-blue-primary text-xs font-semibold flex items-center gap-1 cursor-pointer"
                          title="Enviar o reenviar correo para crear contraseña"
                        >
                          <KeyRound className="w-3.5 h-3.5 text-uct-gold" />
                          Enviar Link Contraseña
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            copiarAlPortapapeles(construirUrlPortal(dest.token_portal), `portal_${dest.id}`)
                          }
                          className="px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1 cursor-pointer"
                        >
                          {copiadoClave === `portal_${dest.id}` ? (
                            <Check className="w-3.5 h-3.5 text-emerald-600" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                          Copiar Bandeja
                        </button>
                        <button
                          type="button"
                          onClick={() => handleToggleDestinatario(dest)}
                          className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold border cursor-pointer ${
                            dest.activo
                              ? 'bg-amber-50 border-amber-300 text-amber-800 hover:bg-amber-100'
                              : 'bg-emerald-50 border-emerald-300 text-emerald-800 hover:bg-emerald-100'
                          }`}
                        >
                          {dest.activo ? 'Deshabilitar' : 'Habilitar'}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleEliminarDestinatario(dest)}
                          className="px-2.5 py-1.5 rounded-lg bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 text-xs font-semibold flex items-center gap-1 cursor-pointer"
                          title="Eliminar usuario consultor y sus reportes asociados"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          Eliminar Usuario
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {pestanaActiva === 'historial' && (
            <div className="space-y-4">
              {reporteEditandoContenido && catalogoEdicionContenido && (
                <div className="p-4 rounded-xl bg-white border-2 border-uct-blue-primary space-y-4 shadow-md">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                    <div>
                      <h4 className="text-xs font-bold text-uct-blue-primary uppercase">
                        Editando Gráficos y Métricas: {reporteEditandoContenido.reporte.codigo_corto} —{' '}
                        {reporteEditandoContenido.reporte.titulo_reporte}
                      </h4>
                      <p className="text-[11px] text-slate-600 mt-0.5">
                        {reporteEditandoContenido.reporte.espacio_nombre} | Período:{' '}
                        {reporteEditandoContenido.reporte.fecha_inicio} al {reporteEditandoContenido.reporte.fecha_fin}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setReporteEditandoContenido(null)}
                      className="text-slate-500 hover:text-slate-800 text-xs font-semibold cursor-pointer"
                    >
                      Cerrar edición
                    </button>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className="p-3.5 rounded-xl bg-slate-50/60 border border-slate-200 space-y-2.5">
                      <div className="flex items-center justify-between border-b border-slate-200/70 pb-1.5">
                        <span className="text-xs font-bold text-uct-blue-primary">
                          Métricas / Indicadores ({reporteEditandoContenido.indicadores.length} /{' '}
                          {catalogoEdicionContenido.indicadores.length})
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              setReporteEditandoContenido((prev) =>
                                prev
                                  ? { ...prev, indicadores: catalogoEdicionContenido.indicadores.map((i) => i.id) }
                                  : null
                              )
                            }
                            className="text-[11px] font-semibold text-uct-blue-primary hover:underline cursor-pointer"
                          >
                            Todos
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setReporteEditandoContenido((prev) => (prev ? { ...prev, indicadores: [] } : null))
                            }
                            className="text-[11px] font-semibold text-slate-500 hover:underline cursor-pointer"
                          >
                            Ninguno
                          </button>
                        </div>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-64 overflow-y-auto pr-1">
                        {catalogoEdicionContenido.indicadores.map((ind) => {
                          const activo = reporteEditandoContenido.indicadores.includes(ind.id)
                          return (
                            <label
                              key={ind.id}
                              className={`flex items-center gap-2 p-2 rounded-lg border text-xs cursor-pointer ${
                                activo
                                  ? 'bg-blue-50 border-uct-blue-primary/40 text-uct-blue-primary font-semibold'
                                  : 'bg-white border-slate-200 text-slate-600'
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={activo}
                                onChange={() =>
                                  setReporteEditandoContenido((prev) => {
                                    if (!prev) return null
                                    const existe = prev.indicadores.includes(ind.id)
                                    return {
                                      ...prev,
                                      indicadores: existe
                                        ? prev.indicadores.filter((x) => x !== ind.id)
                                        : [...prev.indicadores, ind.id],
                                    }
                                  })
                                }
                                className="rounded border-slate-300 text-uct-blue-primary"
                              />
                              <span>{ind.titulo}</span>
                            </label>
                          )
                        })}
                      </div>
                    </div>

                    <div className="p-3.5 rounded-xl bg-slate-50/60 border border-slate-200 space-y-2.5">
                      <div className="flex items-center justify-between border-b border-slate-200/70 pb-1.5">
                        <span className="text-xs font-bold text-uct-blue-primary">
                          Gráficos ({reporteEditandoContenido.graficos.length} /{' '}
                          {catalogoEdicionContenido.graficos.length})
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              setReporteEditandoContenido((prev) =>
                                prev
                                  ? { ...prev, graficos: catalogoEdicionContenido.graficos.map((g) => g.id) }
                                  : null
                              )
                            }
                            className="text-[11px] font-semibold text-uct-blue-primary hover:underline cursor-pointer"
                          >
                            Seleccionar todo
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setReporteEditandoContenido((prev) => (prev ? { ...prev, graficos: [] } : null))
                            }
                            className="text-[11px] font-semibold text-slate-500 hover:underline cursor-pointer"
                          >
                            Ninguno
                          </button>
                        </div>
                      </div>
                      <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                        {catalogoEdicionContenido.secciones.map((sec) => {
                          const colapsada = Boolean(reporteEditandoContenido.colapsadas[sec.nombre])
                          const cantSel = sec.items.filter((g) =>
                            reporteEditandoContenido.graficos.includes(g.id)
                          ).length
                          const todosSec = cantSel === sec.items.length && sec.items.length > 0
                          return (
                            <div key={sec.nombre} className="rounded-lg border border-slate-200 overflow-hidden bg-white">
                              <div className="flex items-center justify-between gap-2 px-2.5 py-1.5 bg-slate-100/80 border-b border-slate-200/70">
                                <button
                                  type="button"
                                  onClick={() =>
                                    setReporteEditandoContenido((prev) =>
                                      prev
                                        ? {
                                            ...prev,
                                            colapsadas: {
                                              ...prev.colapsadas,
                                              [sec.nombre]: !prev.colapsadas[sec.nombre],
                                            },
                                          }
                                        : null
                                    )
                                  }
                                  className="flex items-center gap-1.5 text-left text-xs font-bold text-slate-800 hover:text-uct-blue-primary cursor-pointer min-w-0"
                                >
                                  {colapsada ? (
                                    <ChevronRight className="w-3.5 h-3.5 shrink-0 text-slate-500" />
                                  ) : (
                                    <ChevronDown className="w-3.5 h-3.5 shrink-0 text-slate-500" />
                                  )}
                                  <span className="truncate">{sec.nombre}</span>
                                  <span className="text-[10px] font-semibold text-slate-600">
                                    ({cantSel}/{sec.items.length})
                                  </span>
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    const idsSec = sec.items.map((g) => g.id)
                                    setReporteEditandoContenido((prev) => {
                                      if (!prev) return null
                                      const todos = idsSec.every((id) => prev.graficos.includes(id))
                                      return {
                                        ...prev,
                                        graficos: todos
                                          ? prev.graficos.filter((id) => !idsSec.includes(id))
                                          : Array.from(new Set([...prev.graficos, ...idsSec])),
                                      }
                                    })
                                  }}
                                  className={`px-2 py-0.5 rounded text-[10px] font-semibold shrink-0 cursor-pointer ${
                                    todosSec
                                      ? 'bg-white border border-slate-300 text-slate-700'
                                      : 'bg-uct-blue-primary text-white'
                                  }`}
                                >
                                  {todosSec ? 'Quitar sección' : 'Toda la sección'}
                                </button>
                              </div>
                              {!colapsada && (
                                <div className="p-1.5 grid grid-cols-1 gap-1">
                                  {sec.items.map((graf) => {
                                    const activo = reporteEditandoContenido.graficos.includes(graf.id)
                                    return (
                                      <label
                                        key={graf.id}
                                        className={`flex items-center gap-2 p-1.5 rounded border text-xs cursor-pointer ${
                                          activo
                                            ? 'bg-blue-50/80 border-uct-blue-primary/40 text-uct-blue-primary font-semibold'
                                            : 'bg-slate-50 border-slate-200 text-slate-600'
                                        }`}
                                      >
                                        <input
                                          type="checkbox"
                                          checked={activo}
                                          onChange={() =>
                                            setReporteEditandoContenido((prev) => {
                                              if (!prev) return null
                                              const existe = prev.graficos.includes(graf.id)
                                              return {
                                                ...prev,
                                                graficos: existe
                                                  ? prev.graficos.filter((x) => x !== graf.id)
                                                  : [...prev.graficos, graf.id],
                                              }
                                            })
                                          }
                                          className="rounded border-slate-300 text-uct-blue-primary"
                                        />
                                        <span>{graf.titulo}</span>
                                      </label>
                                    )
                                  })}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end gap-2 pt-1">
                    <button
                      type="button"
                      onClick={() => setReporteEditandoContenido(null)}
                      className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold cursor-pointer"
                    >
                      Cancelar
                    </button>
                    <button
                      type="button"
                      onClick={handleGuardarEdicionContenido}
                      disabled={guardando}
                      className="px-4 py-1.5 rounded-lg bg-uct-blue-primary hover:bg-uct-blue-secondary text-white text-xs font-bold cursor-pointer disabled:opacity-50"
                    >
                      {guardando ? 'Guardando cambios...' : 'Guardar Gráficos y Métricas'}
                    </button>
                  </div>
                </div>
              )}

              {reporteEditandoNotas && (
                <div className="p-4 rounded-xl bg-white border-2 border-uct-blue-primary space-y-3 shadow-md">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold text-uct-blue-primary uppercase">
                      Editando Notas de: {reporteEditandoNotas.titulo_reporte} ({reporteEditandoNotas.codigo_corto})
                    </h4>
                    <button
                      onClick={() => setReporteEditandoNotas(null)}
                      className="text-slate-500 hover:text-slate-800 text-xs font-semibold"
                    >
                      Cerrar edición
                    </button>
                  </div>
                  <textarea
                    rows={3}
                    value={reporteEditandoNotas.nota_general}
                    onChange={(e) =>
                      setReporteEditandoNotas({ ...reporteEditandoNotas, nota_general: e.target.value })
                    }
                    placeholder="Nota ejecutiva general del reporte..."
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg p-2.5 text-xs text-slate-800"
                  />
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={handleGuardarEdicionNotas}
                      disabled={guardando}
                      className="px-4 py-1.5 rounded-lg bg-uct-blue-primary hover:bg-uct-blue-secondary text-white text-xs font-bold cursor-pointer"
                    >
                      Guardar Notas
                    </button>
                  </div>
                </div>
              )}

              {cargando ? (
                <div className="text-center py-12 text-slate-500 text-sm">Cargando reportes emitidos...</div>
              ) : reportesEmitidos.length === 0 ? (
                <div className="text-center py-12 bg-white rounded-xl border border-slate-200 text-slate-500 text-sm">
                  Aún no se han emitido reportes ejecutivos compartidos.
                </div>
              ) : (
                <div className="space-y-3">
                  {reportesEmitidos.map((rep) => (
                    <div
                      key={rep.id}
                      className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-3"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-100 text-uct-blue-primary border border-slate-300">
                              {rep.codigo_corto}
                            </span>
                            <span className="text-sm font-bold text-slate-900">{rep.titulo_reporte}</span>
                            <span
                              className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${
                                rep.vigente
                                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                  : 'bg-red-50 text-red-700 border border-red-200'
                              }`}
                            >
                              {rep.vigente ? 'Habilitado / Vigente' : rep.expirado ? 'Expirado' : 'Deshabilitado'}
                            </span>
                            <span
                              className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${
                                rep.permitir_ia
                                  ? 'bg-amber-50 text-amber-800 border border-amber-200'
                                  : 'bg-slate-100 text-slate-600 border border-slate-200'
                              }`}
                            >
                              {rep.permitir_ia ? 'IA Habilitada' : 'IA Deshabilitada'}
                            </span>
                          </div>
                          <p className="text-xs text-slate-900">
                            <strong className="font-bold text-slate-900">Finalidad / Motivo del Reporte:</strong>{' '}
                            {rep.finalidad_reporte || 'Sin finalidad registrada'}
                          </p>
                          <div className="flex items-center gap-2 pt-0.5 text-xs text-slate-700">
                            <span className="font-semibold text-uct-blue-primary">Emitido por:</span>
                            <span className="font-bold text-slate-900">{rep.creador?.nombre_completo || 'Sistema DSS'}</span>
                            {rep.creador?.rol && (
                              <span className="text-[10px] px-1.5 py-0.2 rounded font-mono font-bold bg-slate-100 border border-slate-300 text-slate-700">
                                {rep.creador.rol}
                              </span>
                            )}
                            {rep.creador?.email && (
                              <span className="text-[11px] text-slate-400">({rep.creador.email})</span>
                            )}
                          </div>
                          <p className="text-xs text-slate-600">
                            <strong>Consultor Destinatario:</strong> {rep.destinatario.nombre_completo} (
                            {rep.destinatario.email} — {rep.destinatario.cargo}, {rep.destinatario.unidad_academica})
                          </p>
                          <p className="text-[11px] text-slate-500">
                            Módulo: {rep.espacio_nombre} | Período: {rep.fecha_inicio} al {rep.fecha_fin} | Aperturas:{' '}
                            {rep.total_accesos}
                            {rep.expira_en ? ` | Expira: ${rep.expira_en.slice(0, 10)}` : ' | Sin expiración'}
                          </p>
                        </div>

                        <div className="flex items-center gap-1.5 flex-wrap">
                          <button
                            type="button"
                            onClick={() => handleReenviarCorreoReporte(rep)}
                            className="px-2.5 py-1.5 rounded-lg bg-uct-blue-primary hover:bg-uct-blue-secondary text-white text-xs font-semibold flex items-center gap-1 cursor-pointer"
                            title="Enviar el enlace de este reporte al correo del consultor"
                          >
                            <Mail className="w-3.5 h-3.5 text-uct-gold" />
                            Enviar al Correo
                          </button>

                          <button
                            type="button"
                            onClick={() => copiarAlPortapapeles(construirUrlReporte(rep.token_acceso), rep.id)}
                            className="px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1 cursor-pointer"
                          >
                            {copiadoClave === rep.id ? (
                              <Check className="w-3.5 h-3.5 text-emerald-600" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                            {copiadoClave === rep.id ? 'Copiado' : 'Copiar Link'}
                          </button>

                          <a
                            href={construirUrlReporte(rep.token_acceso)}
                            target="_blank"
                            rel="noreferrer"
                            className="px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-200 text-uct-blue-primary text-xs font-semibold flex items-center gap-1"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                            Ver
                          </a>

                          <button
                            type="button"
                            onClick={() => abrirEditorContenido(rep)}
                            className="px-2.5 py-1.5 rounded-lg bg-blue-50 hover:bg-blue-100 border border-uct-blue-primary/30 text-uct-blue-primary text-xs font-semibold flex items-center gap-1 cursor-pointer"
                            title="Editar gráficos e indicadores incluidos en este reporte"
                          >
                            <SlidersHorizontal className="w-3.5 h-3.5" />
                            Gráficos / Métricas
                          </button>

                          <button
                            type="button"
                            onClick={() => {
                              setReporteEditandoContenido(null)
                              setReporteEditandoNotas(rep)
                            }}
                            className="px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1 cursor-pointer"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                            Notas
                          </button>

                          <button
                            type="button"
                            onClick={() => handleToggleIAReporte(rep)}
                            className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1 border cursor-pointer ${
                              rep.permitir_ia
                                ? 'bg-amber-50 border-amber-300 text-amber-900 hover:bg-amber-100'
                                : 'bg-slate-100 border-slate-200 text-slate-600 hover:bg-slate-200'
                            }`}
                          >
                            <Sparkles className="w-3.5 h-3.5" />
                            {rep.permitir_ia ? 'Deshabilitar IA' : 'Habilitar IA'}
                          </button>

                          <button
                            type="button"
                            onClick={() => handleToggleActivoReporte(rep)}
                            className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1 border cursor-pointer ${
                              rep.activo
                                ? 'bg-amber-50 border-amber-300 text-amber-800 hover:bg-amber-100'
                                : 'bg-emerald-50 border-emerald-300 text-emerald-800 hover:bg-emerald-100'
                            }`}
                          >
                            <Power className="w-3.5 h-3.5" />
                            {rep.activo ? 'Deshabilitar' : 'Habilitar y Enviar'}
                          </button>

                          <button
                            type="button"
                            onClick={() => handleEliminarReporte(rep.id)}
                            className="p-1.5 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 cursor-pointer"
                            title="Eliminar reporte"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
