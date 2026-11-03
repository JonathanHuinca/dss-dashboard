import React, { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Database,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  Clock,
  RefreshCw,
  Search,
  ChevronDown,
  ChevronUp,
  Filter,
} from 'lucide-react'
import { fetchIngestionHistory, IngestionHistoryItem } from '../../api/client'

export const IngestionAuditSection: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('')
  const [tipoFilter, setTipoFilter] = useState('todos')
  const [estadoFilter, setEstadoFilter] = useState('todos')
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null)

  const { data: jobs = [], isLoading, isFetching, refetch } = useQuery<IngestionHistoryItem[]>({
    queryKey: ['ingestion-history'],
    queryFn: fetchIngestionHistory,
    refetchInterval: 30000,
  })

  // Metricas acumuladas
  const stats = useMemo(() => {
    const total = jobs.length
    const completados = jobs.filter((j) => j.estado === 'completed').length
    const fallidos = jobs.filter((j) => j.estado === 'failed').length
    const totalRegistrosOk = jobs.reduce((acc, curr) => acc + (curr.registros_ok || 0), 0)

    return { total, completados, fallidos, totalRegistrosOk }
  }, [jobs])

  // Filtrado de jobs
  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      const matchSearch =
        searchTerm === '' ||
        job.filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (job.file_hash && job.file_hash.toLowerCase().includes(searchTerm.toLowerCase())) ||
        job.job_id.toLowerCase().includes(searchTerm.toLowerCase())

      const matchTipo = tipoFilter === 'todos' || job.tipo === tipoFilter
      const matchEstado = estadoFilter === 'todos' || job.estado === estadoFilter

      return matchSearch && matchTipo && matchEstado
    })
  }, [jobs, searchTerm, tipoFilter, estadoFilter])

  const formatearFecha = (fechaStr?: string | null) => {
    if (!fechaStr) return 'N/A'
    try {
      const d = new Date(fechaStr)
      return d.toLocaleString('es-CL', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    } catch {
      return fechaStr
    }
  }

  const obtenerBadgeTipo = (tipo: string) => {
    switch (tipo) {
      case 'curricular':
        return 'bg-purple-50 text-purple-700 border-purple-200'
      case 'asistencia':
      case 'marcajes_torniquete':
        return 'bg-blue-50 text-blue-700 border-blue-200'
      case 'vehicular':
      case 'vehicular_anpr':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200'
      case 'academico':
        return 'bg-amber-50 text-amber-700 border-amber-200'
      default:
        return 'bg-slate-50 text-slate-700 border-slate-200'
    }
  }

  const obtenerBadgeEstado = (estado: string) => {
    switch (estado) {
      case 'completed':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 size={13} />
            Completado
          </span>
        )
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <AlertTriangle size={13} />
            Fallido
          </span>
        )
      case 'processing':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200 animate-pulse">
            <RefreshCw size={13} className="animate-spin" />
            En Proceso
          </span>
        )
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            <Clock size={13} />
            {estado}
          </span>
        )
    }
  }

  return (
    <div className="space-y-6">
      {/* Tarjetas Superiores de Metricas */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Total Ingestas
            </span>
            <div className="w-8 h-8 rounded-lg bg-uct-blue-primary/10 text-uct-blue-primary flex items-center justify-center">
              <Database size={16} />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">{stats.total}</div>
          <p className="text-[11px] text-slate-400 mt-0.5">Archivos procesados historicamente</p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Ingestas Exitosas
            </span>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <CheckCircle2 size={16} />
            </div>
          </div>
          <div className="text-2xl font-bold text-emerald-600 mt-2">{stats.completados}</div>
          <p className="text-[11px] text-slate-400 mt-0.5">Cargas sin inconsistencias atomicas</p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Registros Validos
            </span>
            <div className="w-8 h-8 rounded-lg bg-blue-50 text-uct-blue-primary flex items-center justify-center">
              <FileSpreadsheet size={16} />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">
            {stats.totalRegistrosOk.toLocaleString('es-CL')}
          </div>
          <p className="text-[11px] text-slate-400 mt-0.5">Filas agregadas a la base de datos</p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Ingestas Fallidas
            </span>
            <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center">
              <AlertTriangle size={16} />
            </div>
          </div>
          <div className="text-2xl font-bold text-rose-600 mt-2">{stats.fallidos}</div>
          <p className="text-[11px] text-slate-400 mt-0.5">Con rollback por validacion o error</p>
        </div>
      </div>

      {/* Barra de Filtros y Busqueda */}
      <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-2.5 text-slate-400" size={16} />
              <input
                type="text"
                placeholder="Buscar por archivo, ID o SHA-256..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/20 focus:border-uct-blue-primary"
              />
            </div>

            <div className="flex items-center gap-2">
              <Filter size={14} className="text-slate-400" />
              <select
                value={tipoFilter}
                onChange={(e) => setTipoFilter(e.target.value)}
                className="text-xs border border-slate-200 rounded-lg px-2.5 py-2 focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/20 bg-white font-medium text-slate-700"
              >
                <option value="todos">Todos los tipos</option>
                <option value="curricular">Curricular (Maestro)</option>
                <option value="marcajes_torniquete">Marcajes Torniquetes</option>
                <option value="asistencia">Asistencia General</option>
                <option value="vehicular">Vehicular / ANPR</option>
                <option value="academico">Calendario Academico</option>
              </select>

              <select
                value={estadoFilter}
                onChange={(e) => setEstadoFilter(e.target.value)}
                className="text-xs border border-slate-200 rounded-lg px-2.5 py-2 focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/20 bg-white font-medium text-slate-700"
              >
                <option value="todos">Todos los estados</option>
                <option value="completed">Completado</option>
                <option value="failed">Fallido</option>
                <option value="processing">En Proceso</option>
              </select>
            </div>
          </div>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg transition-colors cursor-pointer"
          >
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
            <span>Actualizar</span>
          </button>
        </div>
      </div>

      {/* Tabla de Logs e Historial de Ingesta */}
      <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-800">
              Registro y Auditoria de Ingesta de Datos
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Control de versiones de archivos, integridad SHA-256 y trazabilidad de ejecuciones
            </p>
          </div>
          <span className="text-xs font-medium text-slate-500">
            {filteredJobs.length} {filteredJobs.length === 1 ? 'registro' : 'registros'}
          </span>
        </div>

        {isLoading ? (
          <div className="p-8 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
            <RefreshCw size={16} className="animate-spin" />
            Cargando historial de ingestas...
          </div>
        ) : filteredJobs.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-xs">
            No se encontraron registros de ingesta con los filtros aplicados.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50/75 border-b border-slate-100 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                  <th className="py-3 px-4">Fecha / Hora</th>
                  <th className="py-3 px-4">Archivo</th>
                  <th className="py-3 px-4">Tipo</th>
                  <th className="py-3 px-4">Estado</th>
                  <th className="py-3 px-4 text-center">Reg. Validos</th>
                  <th className="py-3 px-4 text-center">Reg. Error</th>
                  <th className="py-3 px-4">Integridad (SHA-256)</th>
                  <th className="py-3 px-4 text-center">Detalle</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-xs">
                {filteredJobs.map((job) => {
                  const isExpanded = expandedJobId === job.job_id
                  return (
                    <React.Fragment key={job.job_id}>
                      <tr className="hover:bg-slate-50/50 transition-colors">
                        <td className="py-3 px-4 text-slate-600 whitespace-nowrap">
                          {formatearFecha(job.creado_en)}
                        </td>
                        <td className="py-3 px-4">
                          <div className="font-semibold text-slate-800 flex items-center gap-2">
                            <FileSpreadsheet size={15} className="text-slate-400 shrink-0" />
                            <span className="truncate max-w-xs" title={job.filename}>
                              {job.filename}
                            </span>
                          </div>
                          <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                            ID: {job.job_id}
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-[11px] font-medium border ${obtenerBadgeTipo(
                              job.tipo
                            )}`}
                          >
                            {job.tipo}
                          </span>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">{obtenerBadgeEstado(job.estado)}</td>
                        <td className="py-3 px-4 text-center font-semibold text-slate-700">
                          {job.registros_ok.toLocaleString('es-CL')}
                        </td>
                        <td className="py-3 px-4 text-center font-semibold">
                          {job.registros_error > 0 ? (
                            <span className="text-rose-600">{job.registros_error.toLocaleString('es-CL')}</span>
                          ) : (
                            <span className="text-slate-400">0</span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          {job.file_hash ? (
                            <span
                              className="font-mono text-[10px] bg-slate-100 text-slate-600 px-2 py-1 rounded inline-block truncate max-w-[140px]"
                              title={job.file_hash}
                            >
                              {job.file_hash.substring(0, 16)}...
                            </span>
                          ) : (
                            <span className="text-slate-400 text-[11px]">-</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-center">
                          <button
                            onClick={() => setExpandedJobId(isExpanded ? null : job.job_id)}
                            className="p-1 hover:bg-slate-100 text-slate-500 rounded transition-colors cursor-pointer"
                            title="Ver parametros y auditoria"
                          >
                            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                          </button>
                        </td>
                      </tr>

                      {/* Fila expandible con detalles tecnicos */}
                      {isExpanded && (
                        <tr className="bg-slate-50/80">
                          <td colSpan={8} className="p-4 border-b border-slate-100">
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                              <div className="bg-white p-3 rounded-lg border border-slate-200">
                                <span className="font-bold text-slate-700 block mb-1">
                                  Configuracion de Ingesta
                                </span>
                                <div className="space-y-1 text-slate-600">
                                  <div>
                                    <span className="text-slate-400">Modo Solapamiento:</span>{' '}
                                    <span className="font-semibold">
                                      {job.modo_solapamiento || 'N/A'}
                                    </span>
                                  </div>
                                  <div>
                                    <span className="text-slate-400">Clave Enlace:</span>{' '}
                                    <span className="font-semibold">{job.clave_enlace || 'N/A'}</span>
                                  </div>
                                  <div>
                                    <span className="text-slate-400">Modo Enlace:</span>{' '}
                                    <span className="font-semibold">{job.modo_enlace || 'N/A'}</span>
                                  </div>
                                  <div>
                                    <span className="text-slate-400">Espacio ID:</span>{' '}
                                    <span className="font-semibold">{job.espacio_id || 'N/A'}</span>
                                  </div>
                                </div>
                              </div>

                              <div className="bg-white p-3 rounded-lg border border-slate-200">
                                <span className="font-bold text-slate-700 block mb-1">
                                  Tiempos de Ejecucion
                                </span>
                                <div className="space-y-1 text-slate-600">
                                  <div>
                                    <span className="text-slate-400">Inicio:</span>{' '}
                                    {formatearFecha(job.creado_en)}
                                  </div>
                                  <div>
                                    <span className="text-slate-400">Fin:</span>{' '}
                                    {formatearFecha(job.completado_en)}
                                  </div>
                                  <div>
                                    <span className="text-slate-400">Hash Completo:</span>{' '}
                                    <span className="font-mono text-[10px] break-all select-all">
                                      {job.file_hash || 'Sin hash registrado'}
                                    </span>
                                  </div>
                                </div>
                              </div>

                              <div className="bg-white p-3 rounded-lg border border-slate-200">
                                <span className="font-bold text-slate-700 block mb-1">
                                  Detalles / Mensaje del Sistema
                                </span>
                                {job.error_detail ? (
                                  <div className="p-2 bg-rose-50 border border-rose-200 text-rose-700 rounded text-[11px] font-mono break-all max-h-24 overflow-y-auto">
                                    {job.error_detail}
                                  </div>
                                ) : (
                                  <div className="text-emerald-700 flex items-center gap-1.5 text-xs font-medium">
                                    <CheckCircle2 size={14} />
                                    Proceso finalizado exitosamente sin advertencias.
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
