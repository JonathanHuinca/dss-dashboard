import { InteractiveChart } from '../ui/InteractiveChart'
import { IntercampusMobilityResponse } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: IntercampusMobilityResponse
}

export function IntercampusMobilityPlotlyChart({ data }: Props) {
  const chartData: Data[] = [
    {
      x: data.flujo_por_fecha.map(d => d.fecha),
      y: data.flujo_por_fecha.map(d => d.chs_a_csf),
      name: 'CHS → CSF (Hosp. Simulación a San Francisco)',
      type: 'bar',
      marker: { color: '#003865' },
      hovertemplate: '<b>%{x}</b><br>CHS → CSF: %{y} viajes<extra></extra>',
    },
    {
      x: data.flujo_por_fecha.map(d => d.fecha),
      y: data.flujo_por_fecha.map(d => d.csf_a_chs),
      name: 'CSF → CHS (San Francisco a Hosp. Simulación)',
      type: 'bar',
      marker: { color: '#C59B27' },
      hovertemplate: '<b>%{x}</b><br>CSF → CHS: %{y} viajes<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Migración Vehicular Diaria Inter-Campus (CSF ↔ CHS)' },
    xaxis: { title: { text: 'Fecha de Operación' }, tickangle: -45 },
    yaxis: { title: { text: 'Traslados Detectados' } },
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
