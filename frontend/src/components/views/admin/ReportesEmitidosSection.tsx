import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  Bot,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Copy,
  Download,
  ExternalLink,
  Eye,
  FileCheck2,
  FileSpreadsheet,
  FileText,
  Filter,
  Image as ImageIcon,
  Mail,
  Power,
  Printer,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  User,
  X,
} from 'lucide-react'
import { useAuth } from '../../../context/AuthContext'
import { useTemporizadorSeguro } from '../../../hooks/useTemporizadorSeguro'
import {
  actualizarReporteCompartido,
  type AuditoriaReporteResumen,
  type EventoAuditoriaReporte,
  fetchAuditoriaReportes,
  fetchEventosReporte,
  type RespuestaAuditoriaReportes,
  type RespuestaEventosReporte,
} from '../../../api/reportesCompartidos'
import { formatearFechaHoraChile } from '../../../utils/fechaChile'

const ROLE_LABELS: Record<string, { texto: string; clases: string }> = {
  Admin_Sistema: {
    texto: 'Administrador',
    clases: 'bg-purple-50 text-purple-700 border-purple-200',
  },
  Director_Recinto: {
    texto: 'Directivo',
    clases: 'bg-uct-blue-primary/10 text-uct-blue-primary border-uct-blue-primary/20',
  },
  Analista_Consulta: {
    texto: 'Analista',
    clases: 'bg-sky-50 text-sky-700 border-sky-200',
  },
}

const ACCION_META: Record<
  string,
  { etiqueta: string; clases: string; icon: React.ReactNode }
> = {
  apertura_reporte: {
    etiqueta: 'Apertura de reporte',
    clases: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    icon: <Eye size={13} />,
  },
  descarga_excel: {
    etiqueta: 'Descarga Excel (.xlsx)',
    clases: 'bg-green-50 text-green-700 border-green-200',
    icon: <FileSpreadsheet size={13} />,
  },
  descarga_csv: {
    etiqueta: 'Descarga CSV',
    clases: 'bg-amber-50 text-amber-700 border-amber-200',
    icon: <FileText size={13} />,
  },
  descarga_pdf: {
    etiqueta: 'Impresión / PDF',
    clases: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    icon: <Printer size={13} />,
  },
  descarga_imagen: {
    etiqueta: 'Descarga Imagen (.png)',
    clases: 'bg-cyan-50 text-cyan-700 border-cyan-200',
    icon: <ImageIcon size={13} />,
  },
  consulta_ia_confinada: {
    etiqueta: 'Consulta IA Confinada',
    clases: 'bg-violet-50 text-violet-700 border-violet-200',
    icon: <Sparkles size={13} />,
  },
}

const formatearFecha = (iso?: string | null): string =>
  formatearFechaHoraChile(iso, undefined, '—')

const resumirDispositivo = (ua?: string | null): string => {
  if (!ua) return 'No registrado'
  if (/Edg\//i.test(ua)) return 'Microsoft Edge'
  if (/Chrome\//i.test(ua) && !/Edg\//i.test(ua)) return 'Google Chrome'
  if (/Firefox\//i.test(ua)) return 'Mozilla Firefox'
  if (/Safari\//i.test(ua) && !/Chrome\//i.test(ua)) return 'Safari'
  return ua.slice(0, 40)
}

export const ReportesEmitidosSection: React.FC = () => {
  const { isSuperAdmin } = useAuth()
  const queryClient = useQueryClient()

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(15)
  const [espacioFilter, setEspacioFilter] = useState<string>('')
  const [emisorRolFilter, setEmisorRolFilter] = useState<string>('')
  const [revisionFilter, setRevisionFilter] = useState<string>('')
  const [estadoFilter, setEstadoFilter] = useState<string>('')
  const [search, setSearch] = useState<string>('')

  const [avisoMsg, setAvisoMsg] = useState<{ tipo: 'ok' | 'err'; texto: string } | null>(null)
  const [reporteSeleccionado, setReporteSeleccionado] = useState<AuditoriaReporteResumen | null>(null)
  const [filtroAccionTimeline, setFiltroAccionTimeline] = useState<string>('')
  const { programar } = useTemporizadorSeguro()

  const mostrarAviso = (tipo: 'ok' | 'err', texto: string) => {
    setAvisoMsg({ tipo, texto })
    programar(() => setAvisoMsg(null), 5000)
  }

  const { data, isLoading, isFetching, refetch } = useQuery<RespuestaAuditoriaReportes>({
    queryKey: [
      'admin-auditoria-reportes',
      page,
      pageSize,
      espacioFilter,
      emisorRolFilter,
      revisionFilter,
      estadoFilter,
      search,
    ],
    queryFn: () =>
      fetchAuditoriaReportes({
        page,
        page_size: pageSize,
        espacio_id: espacioFilter ? Number(espacioFilter) : undefined,
        emisor_rol: emisorRolFilter || undefined,
        estado_revision: revisionFilter || undefined,
        solo_activos: estadoFilter === '' ? undefined : estadoFilter === 'activos',
        search: search.trim() || undefined,
      }),
    staleTime: 20_000,
  })

  const {
    data: timelineData,
    isLoading: isLoadingTimeline,
    isFetching: isFetchingTimeline,
    refetch: refetchTimeline,
  } = useQuery<RespuestaEventosReporte>({
    queryKey: ['admin-reporte-eventos', reporteSeleccionado?.id, filtroAccionTimeline],
    queryFn: () =>
      fetchEventosReporte(reporteSeleccionado!.id, {
        accion: filtroAccionTimeline || undefined,
        limit: 200,
      }),
    enabled: Boolean(reporteSeleccionado?.id),
    staleTime: 10_000,
  })

  const mutarReporte = useMutation({
    mutationFn: ({
      reporteId,
      payload,
    }: {
      reporteId: string
      payload: Parameters<typeof actualizarReporteCompartido>[1]
      mensajeExito: string
    }) => actualizarReporteCompartido(reporteId, payload),
    onSuccess: (_res, variables) => {
      queryClient.invalidateQueries({ queryKey: ['admin-auditoria-reportes'] })
      queryClient.invalidateQueries({ queryKey: ['reportes-compartidos'] })
      mostrarAviso('ok', variables.mensajeExito)
    },
    onError: (err: any) => {
      mostrarAviso(
        'err',
        err?.response?.data?.detail || 'No fue posible actualizar la configuración del reporte.'
      )
    },
  })

  const kpis = data?.kpis
  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 1
  const espaciosAutorizados = data?.espacios_autorizados ?? null

  const opcionesEspacio = useMemo(() => {
    const todos = [
      { id: 1, nombre: 'Biblioteca CSF' },
      { id: 2, nombre: 'Estacionamiento CSF' },
    ]
    if (!espaciosAutorizados) return todos
    return todos.filter((e) => espaciosAutorizados.includes(e.id))
  }, [espaciosAutorizados])

  const copiarEnlace = async (item: AuditoriaReporteResumen) => {
    const url = `${window.location.origin}/reporte-compartido/${item.token_acceso}`
    try {
      await navigator.clipboard.writeText(url)
      mostrarAviso('ok', `Enlace público del reporte ${item.codigo_corto} copiado al portapapeles.`)
    } catch {
      mostrarAviso('err', 'No se pudo copiar automáticamente el enlace desde este navegador.')
    }
  }

  return (
    <div className="space-y-6">
      {/* Banner descriptivo de alcance RLS */}
      <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-uct-blue-primary/10 border border-uct-blue-primary/20 text-uct-blue-primary flex items-center justify-center shrink-0">
            <FileCheck2 size={22} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-bold text-slate-900">
                Auditoría y Seguimiento de Reportes Emitidos
              </h2>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
                <ShieldCheck size={12} className="text-uct-blue-primary" />
                {isSuperAdmin
                  ? 'Alcance Global (Todos los Módulos)'
                  : `Alcance Directivo (${
                      opcionesEspacio.map((e) => e.nombre).join(' y ') || 'Sin módulo asignado'
                    } — Directivos y Analistas)`}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Trazabilidad de recepción y lectura por parte del destinatario: aperturas, descargas (Excel, CSV, PDF e imágenes), consultas al asistente IA confinado y control rápido de acceso.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-xs font-bold text-slate-700 cursor-pointer shrink-0 transition"
        >
          <RefreshCw size={14} className={isFetching ? 'animate-spin text-uct-blue-primary' : ''} />
          <span>Actualizar Auditoría</span>
        </button>
      </div>

      {avisoMsg && (
        <div
          className={`p-3.5 rounded-xl border flex items-center justify-between gap-2 text-xs font-semibold ${
            avisoMsg.tipo === 'ok'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 size={16} className="shrink-0" />
            <span>{avisoMsg.texto}</span>
          </div>
          <button
            type="button"
            onClick={() => setAvisoMsg(null)}
            className="text-slate-500 hover:text-slate-800 cursor-pointer"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Tarjetas KPI Gerenciales */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Reportes Emitidos
            </span>
            <div className="w-8 h-8 rounded-lg bg-uct-blue-primary/10 text-uct-blue-primary flex items-center justify-center">
              <FileCheck2 size={16} />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">{kpis?.total_reportes ?? 0}</div>
          <p className="text-[11px] text-slate-500 mt-0.5">
            {kpis?.reportes_revisados ?? 0} revisados · {kpis?.reportes_sin_revisar ?? 0} sin revisar
          </p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Tasa de Revisión
            </span>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <Eye size={16} />
            </div>
          </div>
          <div className="text-2xl font-bold text-emerald-600 mt-2">
            {(kpis?.tasa_lectura_pct ?? 0).toFixed(1)}%
          </div>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Destinatarios que abrieron su informe
          </p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Total Aperturas
            </span>
            <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
              <Activity size={16} />
            </div>
          </div>
          <div className="text-2xl font-bold text-amber-600 mt-2">{kpis?.total_aperturas ?? 0}</div>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Accesos acumulados vía enlace único
          </p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Descargas y Uso IA
            </span>
            <div className="w-8 h-8 rounded-lg bg-violet-50 text-violet-600 flex items-center justify-center">
              <Download size={16} />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">
            {kpis?.total_descargas ?? 0}{' '}
            <span className="text-sm font-semibold text-violet-600">
              / {kpis?.total_consultas_ia ?? 0} IA
            </span>
          </div>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Exportaciones y preguntas analíticas
          </p>
        </div>
      </div>

      {/* Barra de Filtros */}
      <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-2xs space-y-3">
        <div className="flex items-center gap-2 text-xs font-bold text-slate-700">
          <Filter size={14} className="text-uct-blue-primary" />
          <span>Filtros de Auditoría</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <div className="relative lg:col-span-2">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
              placeholder="Buscar por código, título, nombre o email destinatario..."
              className="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-200 focus:outline-hidden focus:border-uct-blue-primary"
            />
          </div>

          <select
            value={espacioFilter}
            onChange={(e) => {
              setEspacioFilter(e.target.value)
              setPage(1)
            }}
            className="px-3 py-2 text-xs rounded-xl border border-slate-200 bg-white focus:outline-hidden focus:border-uct-blue-primary"
          >
            {opcionesEspacio.length > 1 && <option value="">Todos los módulos</option>}
            {opcionesEspacio.map((esp) => (
              <option key={esp.id} value={String(esp.id)}>
                {esp.nombre}
              </option>
            ))}
          </select>

          <select
            value={emisorRolFilter}
            onChange={(e) => {
              setEmisorRolFilter(e.target.value)
              setPage(1)
            }}
            className="px-3 py-2 text-xs rounded-xl border border-slate-200 bg-white focus:outline-hidden focus:border-uct-blue-primary"
          >
            <option value="">Todos los emisores</option>
            <option value="directivo">Emitido por Directivo</option>
            <option value="analista">Emitido por Analista</option>
            {isSuperAdmin && <option value="admin">Emitido por Administrador</option>}
          </select>

          <div className="grid grid-cols-2 gap-2">
            <select
              value={revisionFilter}
              onChange={(e) => {
                setRevisionFilter(e.target.value)
                setPage(1)
              }}
              className="px-2.5 py-2 text-xs rounded-xl border border-slate-200 bg-white focus:outline-hidden focus:border-uct-blue-primary"
            >
              <option value="">Lectura: Todas</option>
              <option value="revisado">Revisados</option>
              <option value="sin_revisar">Sin revisar</option>
            </select>

            <select
              value={estadoFilter}
              onChange={(e) => {
                setEstadoFilter(e.target.value)
                setPage(1)
              }}
              className="px-2.5 py-2 text-xs rounded-xl border border-slate-200 bg-white focus:outline-hidden focus:border-uct-blue-primary"
            >
              <option value="">Estado: Todos</option>
              <option value="activos">Activos</option>
              <option value="inactivos">Deshabilitados</option>
            </select>
          </div>
        </div>
      </div>

      {/* Tabla de Reportes Emitidos */}
      <div className="bg-white rounded-2xl border border-slate-200/90 shadow-2xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/90 border-b border-slate-200 text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                <th className="py-3 px-4">Reporte</th>
                <th className="py-3 px-4">Módulo / Emisor</th>
                <th className="py-3 px-4">Destinatario</th>
                <th className="py-3 px-4">Revisión y Aperturas</th>
                <th className="py-3 px-4">Descargas</th>
                <th className="py-3 px-4">Uso IA</th>
                <th className="py-3 px-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-10 text-center text-slate-500">
                    Cargando historial y trazabilidad de reportes...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-10 text-center text-slate-500">
                    No existen reportes compartidos que coincidan con los filtros seleccionados.
                  </td>
                </tr>
              ) : (
                items.map((item) => {
                  const emisorRol = item.emisor?.rol || item.creador?.rol || 'Usuario'
                  const roleMeta = ROLE_LABELS[emisorRol] || {
                    texto: emisorRol,
                    clases: 'bg-slate-100 text-slate-700 border-slate-200',
                  }
                  const emisorNombre =
                    item.emisor?.nombre_completo || item.creador?.nombre_completo || 'Sistema DSS'
                  const emisorEmail = item.emisor?.email || item.creador?.email || ''

                  return (
                    <tr key={item.id} className="hover:bg-slate-50/70 transition align-top">
                      {/* Columna Reporte */}
                      <td className="py-3.5 px-4 max-w-[260px]">
                        <div className="flex flex-wrap items-center gap-1.5 mb-1">
                          <span className="px-2 py-0.5 rounded-md bg-uct-blue-primary text-white text-[10px] font-bold tracking-wide">
                            {item.codigo_corto}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                              item.activo && !item.expirado
                                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                : 'bg-rose-50 text-rose-700 border-rose-200'
                            }`}
                          >
                            {!item.activo
                              ? 'Deshabilitado'
                              : item.expirado
                              ? 'Expirado'
                              : 'Vigente'}
                          </span>
                        </div>
                        <p className="font-bold text-slate-900 leading-snug line-clamp-2">
                          {item.titulo_reporte}
                        </p>
                        <p className="text-[11px] text-slate-500 mt-1">
                          Período: {item.fecha_inicio} al {item.fecha_fin}
                        </p>
                        <p className="text-[10px] text-slate-400 mt-0.5">
                          Emitido: {formatearFecha(item.creado_en)}
                        </p>
                      </td>

                      {/* Columna Módulo y Emisor */}
                      <td className="py-3.5 px-4 min-w-[180px]">
                        <span className="inline-block px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-semibold text-[11px] mb-1.5">
                          {item.espacio_nombre || (item.espacio_id === 1 ? 'Biblioteca CSF' : 'Estacionamiento CSF')}
                        </span>
                        <div className="flex items-center gap-1.5 font-semibold text-slate-800">
                          <User size={12} className="text-slate-400 shrink-0" />
                          <span className="truncate max-w-[150px]">{emisorNombre}</span>
                        </div>
                        {emisorEmail && (
                          <p className="text-[10px] text-slate-400 truncate max-w-[165px]">{emisorEmail}</p>
                        )}
                        <span
                          className={`inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${roleMeta.clases}`}
                        >
                          {roleMeta.texto}
                        </span>
                      </td>

                      {/* Columna Destinatario */}
                      <td className="py-3.5 px-4 min-w-[185px]">
                        <p className="font-bold text-slate-900">{item.destinatario?.nombre_completo || '—'}</p>
                        <p className="text-[11px] text-slate-600">{item.destinatario?.email || '—'}</p>
                        <p className="text-[10px] text-slate-500 mt-0.5">
                          {item.destinatario?.cargo} · {item.destinatario?.unidad_academica}
                        </p>
                      </td>

                      {/* Columna Revisión y Aperturas */}
                      <td className="py-3.5 px-4 min-w-[190px]">
                        <div className="flex items-center gap-2 mb-1">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                              item.revisado
                                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                : 'bg-amber-50 text-amber-700 border-amber-200'
                            }`}
                          >
                            {item.revisado ? 'Revisado' : 'Sin revisar'}
                          </span>
                          <span className="font-bold text-slate-800">
                            {item.total_aperturas} {item.total_aperturas === 1 ? 'apertura' : 'aperturas'}
                          </span>
                        </div>
                        {item.revisado ? (
                          <div className="text-[10px] text-slate-500 space-y-0.5">
                            <p>Último acceso: {formatearFecha(item.ultimo_acceso_en)}</p>
                            {item.ultima_ip && (
                              <p className="text-slate-400">
                                IP: {item.ultima_ip} ({resumirDispositivo(item.ultimo_user_agent)})
                              </p>
                            )}
                          </div>
                        ) : (
                          <p className="text-[10px] text-slate-400">El destinatario aún no abre este enlace.</p>
                        )}
                      </td>

                      {/* Columna Descargas */}
                      <td className="py-3.5 px-4 min-w-[145px]">
                        <div className="flex items-center gap-1.5 font-bold text-slate-800 mb-1">
                          <Download size={13} className="text-uct-blue-primary" />
                          <span>{item.total_descargas}</span>
                          {!item.permitir_exportacion && (
                            <span className="text-[10px] font-semibold text-rose-600">(Bloqueadas)</span>
                          )}
                        </div>
                        {item.total_descargas > 0 ? (
                          <div className="flex flex-wrap gap-1 text-[10px]">
                            {item.total_descargas_excel > 0 && (
                              <span className="px-1.5 py-0.5 rounded bg-green-50 text-green-700 border border-green-200">
                                XLS: {item.total_descargas_excel}
                              </span>
                            )}
                            {item.total_descargas_csv > 0 && (
                              <span className="px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">
                                CSV: {item.total_descargas_csv}
                              </span>
                            )}
                            {item.total_descargas_pdf > 0 && (
                              <span className="px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
                                PDF: {item.total_descargas_pdf}
                              </span>
                            )}
                            {item.total_descargas_imagen > 0 && (
                              <span className="px-1.5 py-0.5 rounded bg-cyan-50 text-cyan-700 border border-cyan-200">
                                IMG: {item.total_descargas_imagen}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-[10px] text-slate-400">Sin descargas</span>
                        )}
                      </td>

                      {/* Columna Uso IA */}
                      <td className="py-3.5 px-4 min-w-[125px]">
                        <div className="flex items-center gap-1.5 mb-1">
                          <Bot
                            size={13}
                            className={item.permitir_ia ? 'text-violet-600' : 'text-slate-400'}
                          />
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                              item.permitir_ia
                                ? 'bg-violet-50 text-violet-700 border-violet-200'
                                : 'bg-slate-100 text-slate-500 border-slate-200'
                            }`}
                          >
                            {item.permitir_ia ? 'IA Activa' : 'IA Apagada'}
                          </span>
                        </div>
                        <p className="text-[11px] font-semibold text-slate-700">
                          {item.total_consultas_ia}{' '}
                          {item.total_consultas_ia === 1 ? 'consulta' : 'consultas'}
                        </p>
                      </td>

                      {/* Columna Acciones */}
                      <td className="py-3.5 px-4 text-right min-w-[215px]">
                        <div className="flex flex-wrap items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => {
                              setFiltroAccionTimeline('')
                              setReporteSeleccionado(item)
                            }}
                            title="Ver timeline cronológico de eventos"
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-uct-blue-primary text-white hover:bg-blue-800 text-[11px] font-bold cursor-pointer transition"
                          >
                            <Clock size={12} />
                            <span>Timeline</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => copiarEnlace(item)}
                            title="Copiar enlace público"
                            className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 cursor-pointer"
                          >
                            <Copy size={13} />
                          </button>

                          <a
                            href={`/reporte-compartido/${item.token_acceso}`}
                            target="_blank"
                            rel="noreferrer"
                            title="Abrir reporte compartido en pestaña nueva"
                            className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100"
                          >
                            <ExternalLink size={13} />
                          </a>

                          <button
                            type="button"
                            disabled={mutarReporte.isPending}
                            onClick={() =>
                              mutarReporte.mutate({
                                reporteId: item.id,
                                payload: { activo: !item.activo },
                                mensajeExito: item.activo
                                  ? `Reporte ${item.codigo_corto} deshabilitado.`
                                  : `Reporte ${item.codigo_corto} habilitado.`,
                              })
                            }
                            title={item.activo ? 'Deshabilitar acceso' : 'Habilitar acceso'}
                            className={`p-1.5 rounded-lg border cursor-pointer ${
                              item.activo
                                ? 'border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100'
                                : 'border-rose-200 text-rose-700 bg-rose-50 hover:bg-rose-100'
                            }`}
                          >
                            <Power size={13} />
                          </button>

                          <button
                            type="button"
                            disabled={mutarReporte.isPending}
                            onClick={() =>
                              mutarReporte.mutate({
                                reporteId: item.id,
                                payload: { permitir_ia: !item.permitir_ia },
                                mensajeExito: item.permitir_ia
                                  ? `Asistente IA deshabilitado para ${item.codigo_corto}.`
                                  : `Asistente IA habilitado para ${item.codigo_corto}.`,
                              })
                            }
                            title={item.permitir_ia ? 'Deshabilitar IA' : 'Habilitar IA'}
                            className={`p-1.5 rounded-lg border cursor-pointer ${
                              item.permitir_ia
                                ? 'border-violet-200 text-violet-700 bg-violet-50 hover:bg-violet-100'
                                : 'border-slate-200 text-slate-400 hover:bg-slate-100'
                            }`}
                          >
                            <Sparkles size={13} />
                          </button>

                          <button
                            type="button"
                            disabled={mutarReporte.isPending}
                            onClick={() =>
                              mutarReporte.mutate({
                                reporteId: item.id,
                                payload: { permitir_exportacion: !item.permitir_exportacion },
                                mensajeExito: item.permitir_exportacion
                                  ? `Descargas bloqueadas para ${item.codigo_corto}.`
                                  : `Descargas habilitadas para ${item.codigo_corto}.`,
                              })
                            }
                            title={item.permitir_exportacion ? 'Bloquear descargas' : 'Permitir descargas'}
                            className={`p-1.5 rounded-lg border cursor-pointer ${
                              item.permitir_exportacion
                                ? 'border-sky-200 text-sky-700 bg-sky-50 hover:bg-sky-100'
                                : 'border-slate-200 text-slate-400 hover:bg-slate-100'
                            }`}
                          >
                            <Download size={13} />
                          </button>

                          <button
                            type="button"
                            disabled={mutarReporte.isPending || !item.activo}
                            onClick={() =>
                              mutarReporte.mutate({
                                reporteId: item.id,
                                payload: { reenviar_correo: true },
                                mensajeExito: `Notificación reenviada a ${item.destinatario?.email}.`,
                              })
                            }
                            title={
                              item.activo
                                ? 'Reenviar enlace por correo institucional'
                                : 'Habilite el reporte para reenviar correo'
                            }
                            className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 disabled:opacity-40 cursor-pointer"
                          >
                            <Mail size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Paginación */}
        <div className="px-4 py-3 bg-slate-50/70 border-t border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-600">
          <div className="flex items-center gap-2">
            <span>
              Mostrando <strong>{items.length}</strong> de <strong>{total}</strong> reportes
            </span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value))
                setPage(1)
              }}
              className="px-2 py-1 rounded-lg border border-slate-200 bg-white text-xs"
            >
              <option value={10}>10 por página</option>
              <option value={15}>15 por página</option>
              <option value={25}>25 por página</option>
              <option value={50}>50 por página</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 cursor-pointer"
            >
              <ChevronLeft size={14} />
              <span>Anterior</span>
            </button>
            <span className="font-semibold">
              Página {page} de {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 cursor-pointer"
            >
              <span>Siguiente</span>
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Modal Timeline Cronológico de Auditoría */}
      {reporteSeleccionado && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-2xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 flex items-start justify-between gap-3 bg-slate-50">
              <div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded-md bg-uct-blue-primary text-white text-[11px] font-bold">
                    {reporteSeleccionado.codigo_corto}
                  </span>
                  <h3 className="text-sm font-bold text-slate-900">
                    Timeline de Actividad — {reporteSeleccionado.titulo_reporte}
                  </h3>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Destinatario: <strong>{reporteSeleccionado.destinatario?.nombre_completo}</strong> (
                  {reporteSeleccionado.destinatario?.email})
                </p>
              </div>
              <button
                type="button"
                onClick={() => setReporteSeleccionado(null)}
                className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-200 cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            <div className="px-5 py-3 border-b border-slate-100 flex flex-wrap items-center justify-between gap-2 bg-white">
              <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                {[
                  { id: '', label: 'Todos los eventos' },
                  { id: 'apertura_reporte', label: 'Aperturas' },
                  { id: 'descarga_excel', label: 'Excel' },
                  { id: 'descarga_csv', label: 'CSV' },
                  { id: 'descarga_pdf', label: 'PDF / Impresión' },
                  { id: 'descarga_imagen', label: 'Imágenes' },
                  { id: 'consulta_ia_confinada', label: 'Consultas IA' },
                ].map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setFiltroAccionTimeline(f.id)}
                    className={`px-2.5 py-1 rounded-lg font-semibold border cursor-pointer transition ${
                      filtroAccionTimeline === f.id
                        ? 'bg-uct-blue-primary text-white border-uct-blue-primary'
                        : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => refetchTimeline()}
                disabled={isFetchingTimeline}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer"
              >
                <RefreshCw size={12} className={isFetchingTimeline ? 'animate-spin' : ''} />
                <span>Refrescar</span>
              </button>
            </div>

            <div className="p-5 overflow-y-auto flex-1 space-y-3">
              {isLoadingTimeline ? (
                <div className="py-10 text-center text-xs text-slate-500">
                  Cargando eventos cronológicos...
                </div>
              ) : (timelineData?.eventos?.length ?? 0) === 0 ? (
                <div className="py-10 text-center text-xs text-slate-500">
                  No se registran eventos bajo el filtro seleccionado.
                </div>
              ) : (
                timelineData?.eventos.map((ev: EventoAuditoriaReporte) => {
                  const meta = ACCION_META[ev.accion] || {
                    etiqueta: ev.accion,
                    clases: 'bg-slate-100 text-slate-700 border-slate-200',
                    icon: <Activity size={13} />,
                  }
                  return (
                    <div
                      key={ev.id}
                      className="p-3.5 rounded-xl border border-slate-200/80 bg-slate-50/50 flex flex-col sm:flex-row sm:items-start justify-between gap-2"
                    >
                      <div className="space-y-1 flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${meta.clases}`}
                          >
                            {meta.icon}
                            <span>{meta.etiqueta}</span>
                          </span>
                          <span className="text-[11px] font-semibold text-slate-700">
                            {formatearFecha(ev.fecha_hora)}
                          </span>
                        </div>

                        {ev.detalle && (
                          <p className="text-xs text-slate-800 bg-white px-2.5 py-1.5 rounded-lg border border-slate-200/80 break-words">
                            {ev.accion === 'consulta_ia_confinada' ? (
                              <>
                                <strong>Consulta del destinatario:</strong> {ev.detalle}
                              </>
                            ) : (
                              ev.detalle
                            )}
                          </p>
                        )}
                      </div>

                      <div className="text-[10px] text-slate-400 sm:text-right shrink-0">
                        <div>IP: {ev.ip_origen || '—'}</div>
                        <div title={ev.user_agent || ''}>{resumirDispositivo(ev.user_agent)}</div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
