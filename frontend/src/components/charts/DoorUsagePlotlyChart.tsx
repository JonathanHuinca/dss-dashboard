import { InteractiveChart } from '../ui/InteractiveChart'
import { DoorUsagePoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'
import { DoorClosed, ArrowDownRight, ArrowUpRight } from 'lucide-react'

interface Props {
  data: DoorUsagePoint[]
}

export function DoorUsagePlotlyChart({ data }: Props) {
  const chartData: Data[] = [
    {
      x: data.map(d => d.puerta),
      y: data.map(d => d.entradas),
      name: 'Entradas',
      type: 'bar',
      marker: { color: '#002B49' },
      text: data.map(d => d.entradas > 0 ? d.entradas.toLocaleString('es-CL') : ''),
      textposition: 'auto',
      hovertemplate: data.map(d => 
        `<b>%{x}</b><br>` +
        `Acceso Entrada: <b>${d.id_in || ''} (${d.cod_in || ''})</b><br>` +
        `Total Entradas: <b>%{y:,}</b><extra></extra>`
      ),
    },
    {
      x: data.map(d => d.puerta),
      y: data.map(d => d.salidas),
      name: 'Salidas',
      type: 'bar',
      marker: { color: '#C59B27' },
      text: data.map(d => d.salidas > 0 ? d.salidas.toLocaleString('es-CL') : ''),
      textposition: 'auto',
      hovertemplate: data.map(d => 
        `<b>%{x}</b><br>` +
        `Acceso Salida: <b>${d.id_out || ''} (${d.cod_out || ''})</b><br>` +
        `Total Salidas: <b>%{y:,}</b><extra></extra>`
      ),
    },
  ]

  const layout = {
    title: { 
      text: 'Distribución de Flujo por Torniquetes y Accesos Universales — Salas Biblioteca CSF',
      font: { size: 12.5, color: '#1E293B' },
      x: 0.5,
      xanchor: 'center' as const,
      y: 0.98,
      yanchor: 'top' as const,
    },
    xaxis: { 
      title: { text: '' },
      automargin: true,
      tickangle: -30,
      tickfont: { size: 9.5, color: '#475569' },
    },
    yaxis: { 
      title: { text: 'Total de Marcajes', font: { size: 11, color: '#64748B' } },
      automargin: true,
      tickfont: { size: 10, color: '#64748B' },
      gridcolor: '#F1F5F9',
    },
    barmode: 'group' as const,
    bargap: 0.25,
    bargroupgap: 0.1,
    margin: { t: 75, r: 25, b: 85, l: 55 },
    showlegend: true,
    legend: {
      orientation: 'h' as const,
      x: 0.5,
      xanchor: 'center' as const,
      y: 1.03,
      yanchor: 'bottom' as const,
      font: { size: 11, color: '#334155' },
    },
  }

  return (
    <div className="w-full space-y-3">
      <InteractiveChart
        data={chartData}
        layout={layout}
        filename="uso_torniquetes_salas_biblioteca"
        height={360}
      />

      {/* Tarjetas de Métricas Físicas por Torniquete y Acceso */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2.5 pt-1 border-t border-slate-100">
        {data.map(d => {
          const isUniversal = d.tipo_acceso === 'Universal' || d.puerta_id.includes('UNIVERSAL')
          return (
            <div 
              key={d.puerta_id || d.puerta}
              className={`p-2.5 rounded-xl border text-xs space-y-1.5 transition-all ${
                isUniversal ? 'bg-amber-50/40 border-amber-200/80' : 'bg-slate-50/80 border-slate-200/80'
              }`}
            >
              <div className="flex items-center justify-between font-bold text-slate-800">
                <span className="flex items-center gap-1.5 truncate" title={d.puerta}>
                  <DoorClosed size={13} className={isUniversal ? 'text-amber-600' : 'text-uct-blue-primary'} />
                  <span className="truncate">{d.puerta}</span>
                </span>
                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full shrink-0 ${
                  isUniversal ? 'bg-amber-100 text-amber-800' : 'bg-blue-100/70 text-uct-blue-primary'
                }`}>
                  {d.tipo_acceso || (isUniversal ? 'Universal' : 'Principal')}
                </span>
              </div>

              <div className="text-[10px] text-slate-500 font-medium">
                {d.sala || 'Biblioteca CSF'}
              </div>

              <div className="grid grid-cols-2 gap-1.5 text-[10px] text-slate-600 bg-white p-1.5 rounded-lg border border-slate-200/60 font-mono">
                <div>
                  <span className="text-[9px] uppercase font-bold text-slate-400 block font-sans">Entrada</span>
                  <span className="text-slate-800 font-bold">{d.id_in || '—'}</span>
                  <span className="text-[9px] text-slate-400 block truncate" title={d.cod_in}>
                    {d.cod_in || ''}
                  </span>
                </div>
                <div>
                  <span className="text-[9px] uppercase font-bold text-slate-400 block font-sans">Salida</span>
                  <span className="text-slate-800 font-bold">{d.id_out || '—'}</span>
                  <span className="text-[9px] text-slate-400 block truncate" title={d.cod_out}>
                    {d.cod_out || ''}
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-between text-[11px] pt-0.5 px-0.5">
                <span className="flex items-center gap-1 text-slate-700 text-[10px]">
                  <ArrowDownRight size={11} className="text-uct-blue-primary" />
                  <b className="text-slate-900">{d.entradas.toLocaleString('es-CL')}</b>
                </span>
                <span className="flex items-center gap-1 text-slate-700 text-[10px]">
                  <ArrowUpRight size={11} className="text-amber-600" />
                  <b className="text-slate-900">{d.salidas.toLocaleString('es-CL')}</b>
                </span>
                <span className="text-slate-500 font-bold text-[10px]">
                  {d.total.toLocaleString('es-CL')}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default DoorUsagePlotlyChart
