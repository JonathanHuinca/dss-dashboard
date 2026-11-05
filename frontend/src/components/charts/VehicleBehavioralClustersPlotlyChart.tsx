import { memo, useMemo } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { BehavioralClustersResponse } from '../../api/client'
import type { Data } from 'plotly.js-dist-min'

interface Props {
  data: BehavioralClustersResponse
}

function VehicleBehavioralClustersPlotlyChartComponent({ data }: Props) {
  const chartData = useMemo<Data[]>(() => {
    const profiles = Array.from(new Set(data.scatter_sample.map(p => p.perfil)))

    return profiles.map(profileName => {
      const pts = data.scatter_sample.filter(p => p.perfil === profileName)
      const color = pts[0]?.color || '#002B49'
      return {
        x: pts.map(p => p.hora_llegada),
        y: pts.map(p => p.permanencia_min),
        name: profileName,
        mode: 'markers',
        type: 'scatter',
        marker: {
          color: color,
          size: profileName.includes('Externo') ? 9 : 7,
          opacity: profileName.includes('Externo') ? 0.9 : 0.65,
          symbol: profileName.includes('Externo') ? 'diamond' : 'circle',
        },
        text: pts.map(p => `Patente: ${p.patente_hash}<br>Días: ${p.dias}`),
        hovertemplate: '<b>%{text}</b><br>Hora Llegada: %{x:.2f} hrs<br>Permanencia: %{y:.1f} min<extra></extra>',
      }
    })
  }, [data])

  const layout = useMemo(() => ({
    title: { text: 'Segmentación de Perfiles de Comportamiento (K-Means Clustering)' },
    xaxis: {
      title: { text: 'Hora Promedio de Llegada (hrs)' },
      range: [7, 21] as [number, number],
      dtick: 2,
    },
    yaxis: {
      title: { text: 'Permanencia Promedio (minutos)' },
      dtick: 120,
    },
    legend: { orientation: 'h' as const, y: 1.15, x: 0.5, xanchor: 'center' as const },
  }), [])

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="perfiles_clustering_vehicular_kmeans"
      height={350}
    />
  )
}

export const VehicleBehavioralClustersPlotlyChart = memo(VehicleBehavioralClustersPlotlyChartComponent)
export default VehicleBehavioralClustersPlotlyChart
