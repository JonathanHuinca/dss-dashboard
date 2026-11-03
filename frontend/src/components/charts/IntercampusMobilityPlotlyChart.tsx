import { InteractiveChart } from '../ui/InteractiveChart'
import { IntercampusMobilityResponse } from '../../api/client'
import { Data } from 'plotly.js-dist-min'
import { formatDayMonthSpanish } from '../../types/dateRange'

interface Props {
  data: IntercampusMobilityResponse
}

export function IntercampusMobilityPlotlyChart({ data }: Props) {
  const chartData: Data[] = [
    {
      x: data.flujo_por_fecha.map(d => formatDayMonthSpanish(d.fecha)),
      y: data.flujo_por_fecha.map(d => d.chs_a_csf),
      name: 'CHS → CSF (Hosp. Simulación a San Francisco)',
      type: 'bar',
      marker: { color: '#003865' },
      text: data.flujo_por_fecha.map(d => d.chs_a_csf > 0 ? d.chs_a_csf.toLocaleString('es-CL') : ''),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      hovertemplate: '<b>%{x}</b><br>CHS → CSF: %{y} viajes<extra></extra>',
    },
    {
      x: data.flujo_por_fecha.map(d => formatDayMonthSpanish(d.fecha)),
      y: data.flujo_por_fecha.map(d => d.csf_a_chs),
      name: 'CSF → CHS (San Francisco a Hosp. Simulación)',
      type: 'bar',
      marker: { color: '#C59B27' },
      text: data.flujo_por_fecha.map(d => d.csf_a_chs > 0 ? d.csf_a_chs.toLocaleString('es-CL') : ''),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      hovertemplate: '<b>%{x}</b><br>CSF → CHS: %{y} viajes<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Migración Vehicular Diaria Inter-Campus (CSF ↔ CHS)' },
    margin: { t: 40, r: 25, b: 75, l: 55 },
    xaxis: {
      title: { text: 'Fecha de Operación' },
      automargin: true,
      tickangle: -45,
      tickfont: { size: 10, color: '#475569' },
    },
    yaxis: {
      title: { text: 'Traslados Detectados' },
      automargin: true,
    },
    barmode: 'stack' as const,
    legend: { orientation: 'h' as const, y: 1.15, x: 0.5, xanchor: 'center' as const },
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="movilidad_intercampus_uct"
      height={330}
    />
  )
}
