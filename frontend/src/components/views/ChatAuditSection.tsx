import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from 'recharts'
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Sparkles,
  Search,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Zap,
  BookOpen,
  Car,
  Bot,
  User,
} from 'lucide-react'
import { api } from '../../api/client'

interface AuditItem {
  id: number
  usuario_id: number | null
  usuario_email: string | null
  usuario_nombre: string | null
  prompt_text: string
  dataset_tipo: string | null
  modelo_utilizado: string | null
  status: string
  response_time_ms: number | null
  timestamp: string
}

interface HourlyStat {
  hora: string
  cantidad: number
}

interface AuditStats {
  consultas_hoy: number
  consultas_exitosas_hoy: number
  consultas_error_hoy: number
  promedio_tiempo_hoy_ms: number
  consultas_por_dataset_hoy: Record<string, number>
  consultas_por_hora_hoy: HourlyStat[]
}

interface AuditResponse {
  items: AuditItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
  stats: AuditStats
}

export const ChatAuditSection: React.FC = () => {
  const [page, setPage] = useState(1)
  const [datasetFilter, setDatasetFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  const { data, isLoading, isFetching, refetch } = useQuery<AuditResponse>({
    queryKey: ['admin-chat-audit', page, datasetFilter, statusFilter, searchQuery],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: '12',
      })
      if (datasetFilter) params.append('dataset_tipo', datasetFilter)
      if (statusFilter) params.append('status_filter', statusFilter)
      if (searchQuery) params.append('search', searchQuery)
      const res = await api.get(`/admin/chat-audit?${params.toString()}`)
      return res.data
    },
  })

  const stats = data?.stats
  const items = data?.items || []
  const total = data?.total || 0
  const totalPages = data?.total_pages || 1

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-uct-blue-primary/10 border border-uct-blue-primary/20 flex items-center justify-center text-uct-blue-primary">
            <Activity size={24} />
          </div>
          <div>
            <p className="text-xs text-slate-500 font-medium">Consultas IA Hoy</p>
            <p className="text-2xl font-bold text-slate-900 mt-0.5">
              {isLoading ? '...' : stats?.consultas_hoy ?? 0}
            </p>
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600">
            <CheckCircle2 size={24} />
          </div>
          <div>
            <p className="text-xs text-slate-500 font-medium">Consultas Exitosas</p>
            <p className="text-2xl font-bold text-emerald-700 mt-0.5">
              {isLoading ? '...' : stats?.consultas_exitosas_hoy ?? 0}
            </p>
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600">
            <XCircle size={24} />
          </div>
          <div>
            <p className="text-xs text-slate-500 font-medium">Consultas con Error</p>
            <p className="text-2xl font-bold text-rose-700 mt-0.5">
              {isLoading ? '...' : stats?.consultas_error_hoy ?? 0}
            </p>
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-600">
            <Zap size={24} />
          </div>
          <div>
            <p className="text-xs text-slate-500 font-medium">Latencia Promedio</p>
            <p className="text-2xl font-bold text-amber-700 mt-0.5">
              {isLoading ? '...' : `${stats?.promedio_tiempo_hoy_ms ?? 0} ms`}
            </p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-slate-900">Consultas IA Hoy</h2>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-uct-blue-primary/10 text-uct-blue-primary">
                Telemetría en tiempo real
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Frecuencia de peticiones analíticas al Asistente Gemini distribuidas por hora del día
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs text-slate-600 bg-slate-50 px-3 py-1.5 rounded-lg border border-slate-200">
              <Clock size={13} className="text-uct-gold" />
              <span>Horario Operativo: 08:00 - 21:00</span>
            </span>
          </div>
        </div>

        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={stats?.consultas_por_hora_hoy || []}
              margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="hora" tick={{ fontSize: 11, fill: '#64748b' }} />
              <YAxis tick={{ fontSize: 11, fill: '#64748b' }} allowDecimals={false} />
              <RechartsTooltip
                contentStyle={{
                  backgroundColor: '#ffffff',
                  borderRadius: '10px',
                  border: '1px solid #e2e8f0',
                  boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                  fontSize: '11px',
                }}
                formatter={(val: any) => [`${val} consultas`, 'Volumen']}
              />
              <Bar dataKey="cantidad" fill="#002B49" radius={[4, 4, 0, 0]} maxBarSize={32} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="p-6 border-b border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-slate-900">Registro de Telemetría (DataGrid)</h2>
              <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-md font-medium border border-slate-200">
                {total} registros totales
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Auditoría granular de consultas, usuario solicitante, latencia y modelo utilizado
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Buscar prompt..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                  setPage(1)
                }}
                className="pl-8 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/20 focus:border-uct-blue-primary w-48"
              />
            </div>

            <select
              value={datasetFilter}
              onChange={(e) => {
                setDatasetFilter(e.target.value)
                setPage(1)
              }}
              className="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/20 focus:border-uct-blue-primary text-slate-700"
            >
              <option value="">Todos los Datasets</option>
              <option value="biblioteca">Biblioteca</option>
              <option value="estacionamiento">Estacionamiento</option>
            </select>

            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value)
                setPage(1)
              }}
              className="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/20 focus:border-uct-blue-primary text-slate-700"
            >
              <option value="">Todos los Estados</option>
              <option value="éxito">Éxito</option>
              <option value="error">Error</option>
            </select>

            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors cursor-pointer"
            >
              <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />
              <span>Actualizar</span>
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 text-[11px] font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                <th className="py-3 px-5">ID</th>
                <th className="py-3 px-5">Fecha & Hora</th>
                <th className="py-3 px-5">Usuario</th>
                <th className="py-3 px-5">Consulta / Prompt</th>
                <th className="py-3 px-5">Dataset</th>
                <th className="py-3 px-5">Modelo IA</th>
                <th className="py-3 px-5">Estado</th>
                <th className="py-3 px-5">Latencia</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-xs">
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-400">
                    Cargando auditoría de IA...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-400">
                    No se registraron consultas bajo los criterios seleccionados.
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3.5 px-5 font-mono text-slate-400 text-[11px]">
                      #{item.id}
                    </td>
                    <td className="py-3.5 px-5 text-slate-600 text-[11px] whitespace-nowrap">
                      {new Date(item.timestamp).toLocaleString()}
                    </td>
                    <td className="py-3.5 px-5">
                      {item.usuario_email ? (
                        <div className="flex flex-col">
                          <span className="font-semibold text-slate-900 leading-tight">
                            {item.usuario_nombre || 'Usuario'}
                          </span>
                          <span className="text-[10px] text-slate-500 font-mono">
                            {item.usuario_email}
                          </span>
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] text-slate-400 italic">
                          <User size={12} />
                          Anónimo / API
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-5 max-w-xs">
                      <p className="text-slate-800 line-clamp-2 text-xs" title={item.prompt_text}>
                        {item.prompt_text}
                      </p>
                    </td>
                    <td className="py-3.5 px-5">
                      {item.dataset_tipo === 'biblioteca' ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                          <BookOpen size={10} />
                          Biblioteca
                        </span>
                      ) : item.dataset_tipo === 'estacionamiento' ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <Car size={10} />
                          Estacionamiento
                        </span>
                      ) : (
                        <span className="text-slate-400 italic text-[11px]">
                          {item.dataset_tipo || 'General'}
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-5">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
                        <Bot size={10} />
                        {item.modelo_utilizado || 'Gemini'}
                      </span>
                    </td>
                    <td className="py-3.5 px-5">
                      {item.status === 'éxito' ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full font-medium text-[11px] border border-emerald-200">
                          <CheckCircle2 size={12} />
                          Éxito
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full font-medium text-[11px] border border-rose-200">
                          <XCircle size={12} />
                          Error
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-5 font-mono text-[11px] text-slate-600 whitespace-nowrap">
                      {item.response_time_ms !== null ? `${item.response_time_ms} ms` : '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="p-4 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
          <span>
            Página {page} de {totalPages} ({total} registros)
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1 || isLoading}
              className="flex items-center gap-1 px-2.5 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft size={14} />
              <span>Anterior</span>
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || isLoading}
              className="flex items-center gap-1 px-2.5 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span>Siguiente</span>
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
