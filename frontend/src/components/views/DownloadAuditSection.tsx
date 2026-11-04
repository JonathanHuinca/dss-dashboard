import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  FileSpreadsheet,
  FileText,
  Calendar,
  Search,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Shield,
  Download,
  Database,
  User,
  Clock,
  Filter,
} from 'lucide-react'
import { fetchDownloadAudit, DownloadAuditResponse } from '../../api/client'

export const DownloadAuditSection: React.FC = () => {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(15)
  const [moduloFilter, setModuloFilter] = useState('')
  const [formatoFilter, setFormatoFilter] = useState('')
  const [search, setSearch] = useState('')

  const { data, isLoading, isFetching, refetch } = useQuery<DownloadAuditResponse>({
    queryKey: ['download-audit', page, pageSize, moduloFilter, formatoFilter, search],
    queryFn: () =>
      fetchDownloadAudit({
        page,
        pageSize,
        modulo: moduloFilter || undefined,
        formato: formatoFilter || undefined,
        search: search || undefined,
      }),
    staleTime: 30_000,
  })

  const stats = data?.stats
  const items = data?.items || []
  const total = data?.total || 0
  const totalPages = data?.total_pages || 1

  return (
    <div className="space-y-6">
      {/* Tarjetas de Estadísticas Gerenciales de Auditoría */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Total Descargas Históricas
            </span>
            <div className="w-8 h-8 rounded-lg bg-uct-blue-primary/10 text-uct-blue-primary flex items-center justify-center">
              <Download size={16} />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 mt-2">
            {stats?.total_descargas ?? 0}
          </div>
          <p className="text-[11px] text-slate-400 mt-0.5">Eventos registrados en el sistema</p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Descargas Hoy
            </span>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <Clock size={16} />
            </div>
          </div>
          <div className="text-2xl font-bold text-emerald-600 mt-2">
            {stats?.descargas_hoy ?? 0}
          </div>
          <p className="text-[11px] text-slate-400 mt-0.5">Operaciones de exportación de hoy</p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Archivos CSV
            </span>
            <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
              <FileSpreadsheet size={16} />
            </div>
          </div>
          <div className="text-2xl font-bold text-amber-600 mt-2">
            {stats?.descargas_csv ?? 0}
          </div>
          <p className="text-[11px] text-slate-400 mt-0.5">Exportaciones de microdatos en CSV</p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Reportes PDF
            </span>
            <div className="w-8 h-8 rounded-lg bg-blue-50 text-uct-blue-primary flex items-center justify-center">
              <FileText size={16} />
            </div>
          </div>
          <div className="text-2xl font-bold text-uct-blue-primary mt-2">
            {stats?.descargas_pdf ?? 0}
          </div>
          <p className="text-[11px] text-slate-400 mt-0.5">Informes ejecutivos resumidos</p>
        </div>
      </div>

      {/* Tabla de Eventos de Auditoría de Descargas */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
        {/* Barra de Filtros */}
        <div className="p-4 border-b border-slate-200 bg-slate-50/60 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex flex-wrap items-center gap-2.5 flex-1">
            <div className="relative min-w-[240px]">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Buscar por usuario o detalle..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(1)
                }}
                className="w-full bg-white border border-slate-200 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-uct-blue-primary"
              />
            </div>

            <select
              value={moduloFilter}
              onChange={(e) => {
                setModuloFilter(e.target.value)
                setPage(1)
              }}
              className="bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 focus:outline-none cursor-pointer"
            >
              <option value="">Todos los módulos</option>
              <option value="biblioteca">Biblioteca CSF</option>
              <option value="estacionamiento">Estacionamiento CSF</option>
            </select>

            <select
              value={formatoFilter}
              onChange={(e) => {
                setFormatoFilter(e.target.value)
                setPage(1)
              }}
              className="bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 focus:outline-none cursor-pointer"
            >
              <option value="">Todos los formatos</option>
              <option value="csv">CSV (Microdatos)</option>
              <option value="pdf">PDF (Resumen)</option>
            </select>
          </div>

          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 cursor-pointer transition-colors"
          >
            <RefreshCw size={12} className={isFetching ? 'animate-spin text-uct-blue-primary' : ''} />
            <span>Actualizar</span>
          </button>
        </div>

        {/* Tabla */}
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-100/70 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[10px]">
                <th className="py-2.5 px-4">Fecha y Hora</th>
                <th className="py-2.5 px-4">Usuario</th>
                <th className="py-2.5 px-4">Módulo</th>
                <th className="py-2.5 px-4">Formato</th>
                <th className="py-2.5 px-4">Período Consultado</th>
                <th className="py-2.5 px-4">Registros Exportados</th>
                <th className="py-2.5 px-4">Detalle / IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    <RefreshCw size={18} className="animate-spin inline-block mr-2 text-uct-blue-primary" />
                    Cargando auditoría de descargas...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    No se registran eventos de descarga con los filtros seleccionados.
                  </td>
                </tr>
              ) : (
                items.map((log) => (
                  <tr key={log.id} className="hover:bg-blue-50/30 transition-colors">
                    <td className="py-3 px-4 font-medium text-slate-800 whitespace-nowrap">
                      {log.timestamp || '—'}
                    </td>
                    <td className="py-3 px-4">
                      <div>
                        <p className="font-semibold text-slate-800">{log.usuario_nombre}</p>
                        <p className="text-[11px] text-slate-400">{log.usuario_email}</p>
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          log.modulo === 'biblioteca'
                            ? 'bg-blue-50 text-uct-blue-primary border border-blue-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}
                      >
                        {log.modulo === 'biblioteca' ? 'Biblioteca CSF' : 'Estacionamiento CSF'}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold uppercase ${
                          log.formato === 'csv'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-rose-50 text-rose-700 border border-rose-200'
                        }`}
                      >
                        {log.formato === 'csv' ? <FileSpreadsheet size={11} /> : <FileText size={11} />}
                        <span>{log.formato}</span>
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-600 whitespace-nowrap">
                      {log.filtro_fecha_inicio && log.filtro_fecha_fin
                        ? `${log.filtro_fecha_inicio} a ${log.filtro_fecha_fin}`
                        : 'Historial Completo'}
                    </td>
                    <td className="py-3 px-4 font-bold text-slate-800">
                      {log.total_registros.toLocaleString('es-CL')}
                    </td>
                    <td className="py-3 px-4 text-slate-500">
                      <p className="truncate max-w-xs" title={log.filtro_detalle || ''}>
                        {log.filtro_detalle || 'Sin filtros adicionales'}
                      </p>
                      <p className="text-[10px] text-slate-400 font-mono">IP: {log.ip_origen}</p>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Paginación */}
        <div className="p-3.5 bg-slate-50/70 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
          <div>
            <span>Total: </span>
            <span className="font-bold text-slate-800">{total}</span> eventos registrados
          </div>

          <div className="flex items-center gap-2">
            <span>
              Página <span className="font-semibold">{page}</span> de <span className="font-semibold">{totalPages}</span>
            </span>

            <div className="flex items-center gap-1">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="p-1.5 rounded-md border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
              >
                <ChevronLeft size={14} />
              </button>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="p-1.5 rounded-md border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
