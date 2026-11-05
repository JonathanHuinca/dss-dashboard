import { memo, useMemo } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { format } from 'date-fns'
import type { Data, Layout } from 'plotly.js-dist-min'

interface Props {
  data: { bucket: string; ingresos?: number; entradas?: number; salidas: number }[]
}

function HourlyBarChartComponent({ data }: Props) {
  const { chartData, layout } = useMemo(() => {
    const aggMap = new Map<string, { ingresos: number; salidas: number }>()

    data.forEach(d => {
      if (!d.bucket) return
      const hora = format(new Date(d.bucket), 'HH:00')
      const prev = aggMap.get(hora) ?? { ingresos: 0, salidas: 0 }
      prev.ingresos += (d.ingresos ?? d.entradas ?? 0)
      prev.salidas += (d.salidas ?? 0)
      aggMap.set(hora, prev)
    })

    const sortedHoras = Array.from(aggMap.keys()).sort((a, b) => a.localeCompare(b))
    const ingresos = sortedHoras.map(h => aggMap.get(h)!.ingresos)
    const salidas = sortedHoras.map(h => aggMap.get(h)!.salidas)

    const cData: Data[] = [
      {
        x: sortedHoras,
        y: ingresos,
        type: 'bar',
        name: 'Ingresos',
        marker: { color: '#002B49' },
        text: ingresos.map(v => v > 0 ? v.toLocaleString('es-CL') : ''),
        textposition: 'auto',
        textfont: { size: 9, color: '#ffffff' },
        hovertemplate: '<b>%{x} hrs</b><br>Ingresos: %{y:,}<extra></extra>',
      },
      {
        x: sortedHoras,
        y: salidas,
        type: 'bar',
        name: 'Salidas',
        marker: { color: '#C59B27' },
        text: salidas.map(v => v > 0 ? v.toLocaleString('es-CL') : ''),
        textposition: 'auto',
        textfont: { size: 9, color: '#ffffff' },
        hovertemplate: '<b>%{x} hrs</b><br>Salidas: %{y:,}<extra></extra>',
      },
    ]

    const lyt: Partial<Layout> = {
      title: {
        text: 'Flujo Horario de Ingresos y Salidas',
        font: { size: 12.5, color: '#1E293B' },
        x: 0.02,
        xanchor: 'left',
      },
      barmode: 'group',
      bargap: 0.25,
      bargroupgap: 0.1,
      margin: { t: 40, r: 20, b: 40, l: 45 },
      xaxis: {
        title: { text: '' },
        automargin: true,
        tickfont: { size: 10, color: '#475569' },
        gridcolor: '#F1F5F9',
      },
      yaxis: {
        title: { text: 'Personas / Hora', font: { size: 10, color: '#64748B' } },
        automargin: true,
        tickfont: { size: 10, color: '#64748B' },
        gridcolor: '#F1F5F9',
      },
      showlegend: true,
      legend: {
        orientation: 'h',
        x: 0.5,
        xanchor: 'center',
        y: 1.05,
        yanchor: 'bottom',
        font: { size: 10.5, color: '#334155' },
      },
    }

    return { chartData: cData, layout: lyt }
  }, [data])

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="flujo_horario_ingresos_salidas"
      height={320}
    />
  )
}

export const HourlyBarChart = memo(HourlyBarChartComponent)
export default HourlyBarChart
