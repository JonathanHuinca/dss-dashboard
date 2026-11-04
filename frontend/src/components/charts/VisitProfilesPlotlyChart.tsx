import { memo, useState } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { VisitProfilesDonutResponse } from '../../api/client'
import { Data } from 'plotly.js-dist-min'
import { Info, AlertCircle, CheckCircle2, Clock } from 'lucide-react'

interface Props {
  data?: VisitProfilesDonutResponse | null
  height?: number
}

export const VisitProfilesPlotlyChart = memo(function VisitProfilesPlotlyChart({ data, height = 340 }: Props) {
  const [rebanadaSeleccionada, setRebanadaSeleccionada] = useState<string | null>(null)

  if (!data || !data.items || data.items.length === 0 || (data.total_visitas_analizadas === 0 && (data.total_eventos ?? 0) === 0)) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-slate-400 space-y-2">
        <Clock className="w-8 h-8 text-slate-300 animate-pulse" />
        <p className="text-xs font-medium">Sin registros físicos de torniquetes para el período seleccionado</p>
      </div>
    )
  }

  if (data.total_visitas_analizadas === 0 && (data.total_eventos ?? 0) > 0) {
    return (
      <div className="space-y-3 p-4 bg-amber-50/70 border border-amber-200/80 rounded-xl text-xs text-amber-900">
        <div className="flex items-center gap-2 font-bold text-amber-800">
          <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
          <span>Datos Asimétricos Omitidos — Sin Ciclos Completos de Entrada y Salida</span>
        </div>
        <p className="text-[11px] text-amber-800/90 leading-relaxed">
          Se identificaron <b>{data.total_eventos.toLocaleString('es-CL')} eventos físicos</b> en el período ({data.entradas_sin_salida.toLocaleString('es-CL')} entradas sin salida y {data.salidas_sin_entrada.toLocaleString('es-CL')} salidas sin entrada), pero ninguno completó un ciclo cerrado consecutivo para calcular la permanencia en minutos.
        </p>
        <div className="flex items-center gap-3 pt-1 text-[10.5px] font-semibold">
          <span className="px-2 py-0.5 bg-amber-200/60 rounded">Total Bruto: {data.total_eventos.toLocaleString('es-CL')}</span>
          <span className="px-2 py-0.5 bg-amber-200/60 rounded">Asimétricos: {data.total_no_analizados.toLocaleString('es-CL')}</span>
        </div>
      </div>
    )
  }

  const items = data.items
  const totalAnalizadas = data.total_visitas_analizadas || 1
  const tasaRebote = data.tasa_rebote_pct ?? 0

  const labels = items.map(d => d.perfil)
  const pullArray = labels.map(l => (l === rebanadaSeleccionada ? 0.14 : 0))
  const baseColors = items.map(d => d.color || '#003865')

  // Configuración del Donut Plotly con colores normativos UCT
  const chartData: Data[] = [
    {
      labels,
      values: items.map(d => d.total),
      type: 'pie',
      hole: 0.58,
      sort: false,
      pull: pullArray,
      marker: {
        colors: rebanadaSeleccionada
          ? labels.map((l, idx) => (l === rebanadaSeleccionada ? baseColors[idx] : '#E2E8F0'))
          : baseColors,
        line: {
          color: rebanadaSeleccionada
            ? labels.map(l => (l === rebanadaSeleccionada ? '#002B49' : '#FFFFFF'))
            : '#FFFFFF',
          width: rebanadaSeleccionada ? labels.map(l => (l === rebanadaSeleccionada ? 2.5 : 1)) : 2.5,
        },
      },
      textinfo: 'percent',
      textposition: 'inside',
      insidetextfont: { color: '#FFFFFF', size: 12, family: 'Inter, sans-serif' },
      hovertemplate:
        '<b>%{label}</b><br>' +
        'Visitas: <b>%{value:,}</b><br>' +
        'Proporción: <b>%{percent}</b><br>' +
        '<extra></extra>',
    },
  ]

  const layout = {
    showlegend: true,
    legend: {
      orientation: 'h' as const,
      x: 0.5,
      xanchor: 'center' as const,
      y: -0.12,
      font: { size: 11, family: 'Inter, sans-serif' },
      itemclick: false as const,
      itemdoubleclick: false as const,
    },
    margin: { t: 20, b: 30, l: 15, r: 15 },
    annotations: [
      {
        font: { size: 18, color: '#003865', family: 'Inter, sans-serif', weight: 800 },
        showarrow: false,
        text: `${tasaRebote.toFixed(1)}%`,
        x: 0.5,
        y: 0.54,
      },
      {
        font: { size: 10, color: '#64748B', family: 'Inter, sans-serif' },
        showarrow: false,
        text: 'Tasa de Rebote',
        x: 0.5,
        y: 0.44,
      },
    ],
  }

  const handleDonutClick = (event: Readonly<Plotly.PlotMouseEvent>) => {
    if (event.points && event.points.length > 0) {
      const label = (event.points[0] as any).label
      if (label) {
        setRebanadaSeleccionada(prev => (prev === label ? null : label))
      }
    }
  }

  return (
    <div className="space-y-4">
      {/* 1. Gráfico Donut Interactivo */}
      <div className="bg-slate-50/50 p-2 rounded-xl border border-slate-100">
        <InteractiveChart
          data={chartData}
          layout={layout}
          filename="perfiles_visita_donut"
          height={height}
          onClick={handleDonutClick}
        />
      </div>

      {/* 2. Tarjetas de Resumen Numérico (Analizadas vs No Analizadas) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
        <div className="bg-blue-50/70 border border-blue-200/80 rounded-xl p-3 flex items-start gap-2.5">
          <CheckCircle2 className="w-5 h-5 text-uct-blue-primary shrink-0 mt-0.5" />
          <div className="min-w-0">
            <span className="block text-[10.5px] font-semibold text-uct-blue-primary uppercase tracking-wider">
              Visitas Analizadas
            </span>
            <span className="text-lg font-extrabold text-slate-800">
              {data.total_visitas_analizadas.toLocaleString('es-CL')}
            </span>
            <span className="block text-[10px] text-slate-500 mt-0.5 leading-tight">
              Ciclos completos (Entrada y Salida emparejadas)
            </span>
          </div>
        </div>

        <div className="bg-amber-50/70 border border-amber-200/80 rounded-xl p-3 flex items-start gap-2.5">
          <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <span className="block text-[10.5px] font-semibold text-amber-800 uppercase tracking-wider">
              No Analizados (Asimétricos)
            </span>
            <span className="text-lg font-extrabold text-amber-900">
              {data.total_no_analizados.toLocaleString('es-CL')}
            </span>
            <span className="block text-[10px] text-amber-700/80 mt-0.5 leading-tight">
              {data.entradas_sin_salida.toLocaleString('es-CL')} solo entrada + {data.salidas_sin_entrada.toLocaleString('es-CL')} solo salida
            </span>
          </div>
        </div>

        <div className="bg-emerald-50/70 border border-emerald-200/80 rounded-xl p-3 flex items-start gap-2.5">
          <Clock className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <span className="block text-[10.5px] font-semibold text-emerald-800 uppercase tracking-wider">
              Total Eventos Físicos
            </span>
            <span className="text-lg font-extrabold text-emerald-900">
              {data.total_eventos.toLocaleString('es-CL')}
            </span>
            <span className="block text-[10px] text-emerald-700/80 mt-0.5 leading-tight">
              Registros brutos en el período
            </span>
          </div>
        </div>
      </div>

      {/* 3. Panel Explicativo de Decisión Metodológica DSS */}
      <div className="bg-white rounded-xl border border-slate-200 p-3.5 shadow-2xs space-y-2.5">
        <div className="flex items-center gap-2 text-xs font-bold text-slate-800">
          <Info className="w-4 h-4 text-uct-blue-primary shrink-0" />
          <span>Criterio de Exclusión Metodológica DSS — Casos Asimétricos</span>
        </div>

        <p className="text-[11px] text-slate-600 leading-relaxed">
          Para calcular la permanencia física con rigor analítico, es indispensable disponer de la <b>marca de inicio (entrada)</b> y de <b>término (salida)</b>. Los registros asimétricos no pueden medirse en minutos y se excluyen del gráfico donut para evitar sesgos:
        </p>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-[10.5px] border-collapse">
            <thead>
              <tr className="bg-slate-100 text-slate-700 font-bold border-b border-slate-200">
                <th className="py-1.5 px-2.5">Caso Asimétrico</th>
                <th className="py-1.5 px-2.5">Diagnóstico Técnico</th>
                <th className="py-1.5 px-2.5">Impacto en Perfiles de Visita</th>
                <th className="py-1.5 px-2.5">Decisión Metodológica DSS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-600">
              <tr className="hover:bg-slate-50/60">
                <td className="py-2 px-2.5 font-semibold text-amber-700 whitespace-nowrap">
                  Solo Entrada ({data.entradas_sin_salida.toLocaleString('es-CL')})
                </td>
                <td className="py-2 px-2.5">
                  Marcó al ingresar por torniquete, pero egresó por salida libre, emergencia o puerta abierta.
                </td>
                <td className="py-2 px-2.5">
                  Se desconoce la hora de salida. Asignar el cierre inflaría falsamente como <i>Profundo (&gt;120 min)</i>.
                </td>
                <td className="py-2 px-2.5 font-medium text-slate-800">
                  Excluido del cálculo de duración. Se cataloga como evento de auditoría de integridad.
                </td>
              </tr>
              <tr className="hover:bg-slate-50/60">
                <td className="py-2 px-2.5 font-semibold text-rose-700 whitespace-nowrap">
                  Solo Salida ({data.salidas_sin_entrada.toLocaleString('es-CL')})
                </td>
                <td className="py-2 px-2.5">
                  Marcó al salir por torniquete, pero ingresó sin credencial (pasó junto a otro o puerta abierta).
                </td>
                <td className="py-2 px-2.5">
                  Se desconoce por completo la hora de inicio de la estancia.
                </td>
                <td className="py-2 px-2.5 font-medium text-slate-800">
                  Excluido del cálculo de duración. No se imputan tiempos arbitrarios.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
})
