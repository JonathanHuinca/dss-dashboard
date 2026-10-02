import React from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  CalendarDays,
  GraduationCap,
  Repeat,
  Flame,
  Users,
  RefreshCw,
  TrendingUp,
  Building2,
} from 'lucide-react'
import { fetchKpiSummary, KPISummary } from '../../api/client'
import { DateRange } from '../../types/dateRange'

interface Props {
  espacioId?: number
  selectedRange?: DateRange
}

export const KPIBanner: React.FC<Props> = ({ espacioId = 1, selectedRange }) => {
  const { data, isLoading, isFetching, isError, refetch } = useQuery<KPISummary>({
    queryKey: ['kpi-summary', espacioId, selectedRange?.inicio, selectedRange?.fin],
    queryFn: () => fetchKpiSummary(espacioId, selectedRange?.inicio, selectedRange?.fin),
    staleTime: 1000 * 60 * 5,
  })

  const activePeriodLabel = selectedRange?.label || data?.periodo_label || 'Historial Semestre Completo'

  return (
    <section className="px-6 pt-5 pb-3">
      <div className="bg-white/90 backdrop-blur-md rounded-2xl p-4.5 border border-slate-200/80 shadow-xs mb-1">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3.5 pb-2.5 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-uct-blue-primary/10 flex items-center justify-center text-uct-blue-primary">
              <Building2 size={16} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-slate-800 tracking-tight">
                  Panel Gerencial de Métricas Clave
                </h2>
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-blue-50 text-uct-blue-primary border border-blue-200/60 max-w-xs truncate">
                  <TrendingUp size={11} className="shrink-0" />
                  <span className="truncate">{activePeriodLabel}</span>
                </span>
              </div>
              <p className="text-[11px] text-slate-500">
                Consolidado operacional dinámico sincronizado con el período seleccionado
              </p>
            </div>
          </div>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:text-uct-blue-primary bg-slate-50 hover:bg-slate-100/80 border border-slate-200 transition-all cursor-pointer disabled:opacity-50"
            title="Actualizar métricas"
          >
            <RefreshCw size={12} className={isFetching ? 'animate-spin text-uct-blue-primary' : ''} />
            <span>Actualizar</span>
          </button>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="h-24 rounded-xl bg-slate-100/80 animate-pulse border border-slate-200/60 p-3 flex flex-col justify-between"
              >
                <div className="flex justify-between items-center">
                  <div className="h-3 w-20 bg-slate-200 rounded"></div>
                  <div className="h-7 w-7 bg-slate-200 rounded-lg"></div>
                </div>
                <div className="h-6 w-24 bg-slate-200 rounded"></div>
                <div className="h-2 w-16 bg-slate-200 rounded"></div>
              </div>
            ))}
          </div>
        ) : isError ? (
          <div className="py-4 text-center text-xs text-rose-600 bg-rose-50/50 rounded-xl border border-rose-200/60">
            No fue posible cargar las métricas gerenciales.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3.5">
            <div className="relative overflow-hidden bg-white rounded-xl p-3.5 border border-slate-200/80 shadow-2xs hover:shadow-xs transition-all hover:border-emerald-300 group">
              <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-emerald-400 to-teal-500"></div>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                    Días Operativos
                  </p>
                  <p className="text-2xl font-black text-slate-900 mt-1 tracking-tight">
                    {data?.dias_operativos ?? 0}
                    <span className="text-xs font-semibold text-slate-400 ml-1">días</span>
                  </p>
                </div>
                <div className="w-9 h-9 rounded-lg bg-emerald-50 text-emerald-600 border border-emerald-200/60 flex items-center justify-center group-hover:scale-105 transition-transform">
                  <CalendarDays size={18} />
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mt-1.5 flex items-center gap-1 font-medium">
                Con registro de actividad
              </p>
            </div>

            <div className="relative overflow-hidden bg-white rounded-xl p-3.5 border border-slate-200/80 shadow-2xs hover:shadow-xs transition-all hover:border-blue-300 group">
              <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500 to-indigo-600"></div>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                    Horas-Estudiante
                  </p>
                  <p className="text-2xl font-black text-slate-900 mt-1 tracking-tight">
                    {Number(data?.horas_estudiante ?? 0).toLocaleString('es-CL')}
                    <span className="text-xs font-semibold text-slate-400 ml-1">hrs</span>
                  </p>
                </div>
                <div className="w-9 h-9 rounded-lg bg-blue-50 text-uct-blue-primary border border-blue-200/60 flex items-center justify-center group-hover:scale-105 transition-transform">
                  <GraduationCap size={18} />
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mt-1.5 flex items-center gap-1 font-medium">
                Horas efectivas de uso
              </p>
            </div>

            <div className="relative overflow-hidden bg-white rounded-xl p-3.5 border border-slate-200/80 shadow-2xs hover:shadow-xs transition-all hover:border-purple-300 group">
              <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-purple-500 to-violet-600"></div>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                    Recurrencia Mensual
                  </p>
                  <p className="text-2xl font-black text-slate-900 mt-1 tracking-tight">
                    {Number(data?.recurrencia_mensual ?? 0).toFixed(1)}x
                  </p>
                </div>
                <div className="w-9 h-9 rounded-lg bg-purple-50 text-purple-600 border border-purple-200/60 flex items-center justify-center group-hover:scale-105 transition-transform">
                  <Repeat size={18} />
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mt-1.5 flex items-center gap-1 font-medium">
                Visitas promedio / usuario
              </p>
            </div>

            <div className="relative overflow-hidden bg-white rounded-xl p-3.5 border border-slate-200/80 shadow-2xs hover:shadow-xs transition-all hover:border-amber-300 group">
              <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-amber-400 to-orange-500"></div>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                    Hora Pico de Ingreso
                  </p>
                  <p className="text-2xl font-black text-slate-900 mt-1 tracking-tight">
                    {data?.hora_pico_ingreso || '14:00 hrs'}
                  </p>
                </div>
                <div className="w-9 h-9 rounded-lg bg-amber-50 text-amber-600 border border-amber-200/60 flex items-center justify-center group-hover:scale-105 transition-transform">
                  <Flame size={18} />
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mt-1.5 flex items-center gap-1 font-medium">
                Mayor afluencia histórica
              </p>
            </div>

            <div className="relative overflow-hidden bg-white rounded-xl p-3.5 border border-slate-200/80 shadow-2xs hover:shadow-xs transition-all hover:border-rose-300 group">
              <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-rose-500 to-red-600"></div>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                    Pico Concurrente
                  </p>
                  <p className="text-2xl font-black text-slate-900 mt-1 tracking-tight">
                    {Number(data?.pico_concurrente ?? 0).toLocaleString('es-CL')} pers
                  </p>
                </div>
                <div className="w-9 h-9 rounded-lg bg-rose-50 text-rose-600 border border-rose-200/60 flex items-center justify-center group-hover:scale-105 transition-transform">
                  <Users size={18} />
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mt-1.5 flex items-center gap-1 font-medium">
                Máximo horario registrado
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
