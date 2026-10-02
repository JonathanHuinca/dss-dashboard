import { InteractiveChart } from '../ui/InteractiveChart'
import { Forecast14DayItem } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: Forecast14DayItem[]
  title?: string
}

export function Forecast14DaysPlotlyChart({ data, title = 'Proyección Cuantitativa de Demanda (Próximos 14 Días)' }: Props) {
  const chartData: Data[] = [
    {
      x: data.map(d => `${d.fecha.substring(5)} (${d.dia_nombre.substring(0, 3)})`),
      y: data.map(d => d.demanda_estimada),
      type: 'bar',
      marker: {
        color: data.map(d => d.color),
      },
      customdata: data.map(d => d.hito),
      hovertemplate: '<b>%{x}</b><br>Estimación: %{y:,} personas<br>Hito: %{customdata}<extra></extra>',
    },
  ]

  const layout = {
    title: { text: title },
    xaxis: { title: { text: 'Fecha y Día de la Semana' }, tickangle: -45 },
    yaxis: { title: { text: 'Demanda Proyectada (HistGradientBoosting)' } },
  }

  return (
    <div>
      <InteractiveChart
        data={chartData}
        layout={layout}
        filename="proyeccion_demanda_14_dias"
        height={320}
      />
      <div className="flex flex-wrap items-center justify-center gap-4 mt-2 text-xs text-uct-text-muted">
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm inline-block" style={{ backgroundColor: '#003865' }} /> Clases Regulares</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm inline-block" style={{ backgroundColor: '#DC2626' }} /> Certámenes / Exámenes</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm inline-block" style={{ backgroundColor: '#C59B27' }} /> Receso Académico</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm inline-block" style={{ backgroundColor: '#0284C7' }} /> Fin de Semana / Feriado</span>
      </div>
    </div>
  )
}
