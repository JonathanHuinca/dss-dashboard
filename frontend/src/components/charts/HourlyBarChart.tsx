import { InteractiveChart } from '../ui/InteractiveChart'
import { format } from 'date-fns'
import { Data, Layout } from 'plotly.js-dist-min'

interface Props {
  data: { bucket: string; ingresos?: number; entradas?: number; salidas: number }[]
}

export function HourlyBarChart({ data }: Props) {
  // Consolidar flujo de ingresos y salidas por franja horaria (00:00 - 23:00)
  const aggMap = new Map<string, { ingresos: number; salidas: number }>()

  data.forEach(d => {
    if (!d.bucket) return
    const hora = format(new Date(d.bucket), 'HH:00')
    const prev = aggMap.get(hora) ?? { ingresos: 0, salidas: 0 }
    prev.ingresos += (d.ingresos ?? d.entradas ?? 0)
    prev.salidas += (d.salidas ?? 0)
    aggMap.set(hora, prev)
  })

  // Ordenar cronológicamente ascendente por hora (00:00 -> 23:00)
  const sortedHoras = Array.from(aggMap.keys()).sort((a, b) => a.localeCompare(b))
  const ingresos = sortedHoras.map(h => aggMap.get(h)!.ingresos)
  const salidas = sortedHoras.map(h => aggMap.get(h)!.salidas)

  const chartData: Data[] = [
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

  const layout: Partial<Layout> = {
    title: {
      text: 'Flujo Horario de Ingresos y Salidas',
      font: { size: 12.5, color: '#1E293B' },
      x: 0.02,
      xanchor: 'left',
    },
    barmode: 'group',
    bargap: 0.25,
    bargroupgap: 0.1,
    margin: { t: 40, r: 25, b: 75, l: 55 },
    xaxis: {
      title: { text: 'Hora del Día (00:00 - 23:00 hrs)', font: { size: 10, color: '#64748B' } },
      showgrid: false,
      automargin: true,
      tickfont: { size: 10, color: '#64748B' },
      categoryorder: 'category ascending',
    },
    yaxis: {
      title: { text: 'Cantidad de Marcajes', font: { size: 10, color: '#64748B' } },
      showgrid: true,
      automargin: true,
      gridcolor: '#e2e8f0',
      tickfont: { size: 10, color: '#64748B' },
    },
    showlegend: true,
    legend: {
      orientation: 'h',
      y: -0.28,
      x: 0.5,
      xanchor: 'center',
      yanchor: 'top',
      font: { size: 10.5, color: '#334155' },
    },
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="flujo_horario_accesos"
      height={340}
    />
  )
}

export default HourlyBarChart
