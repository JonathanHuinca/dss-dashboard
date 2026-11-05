import {  useMemo, useState , memo } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { HeatmapPoint } from '../../api/client'
import type { Data, Layout  } from 'plotly.js-dist-min'
import { Clock, Moon } from 'lucide-react'

interface Props {
  data: HeatmapPoint[]
  modoInicial?: '24h' | 'diurno' | 'nocturno'
  permitirModoNocturno?: boolean
}

const DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
const HORAS_24 = Array.from({ length: 24 }, (_, i) => i) // 00-23
const HORAS_DIURNO = Array.from({ length: 16 }, (_, i) => i + 6) // 06-21
const HORAS_NOCTURNO = [22, 23, 0, 1, 2, 3, 4, 5, 6, 7] // 22:00 a 07:00 (Ventana 24 Horas)

function HeatmapChartComponent({ data, modoInicial = '24h', permitirModoNocturno = false }: Props) {
  const [modo, setModo] = useState<'24h' | 'diurno' | 'nocturno'>(modoInicial)

  const horasActivas =
    modo === 'nocturno' ? HORAS_NOCTURNO : modo === 'diurno' ? HORAS_DIURNO : HORAS_24

  const { zMatrix, xLabels } = useMemo(() => {
    const lookup = new Map(
      data.map(d => [`${d.dia_semana}-${d.hora}`, { avg: d.ingresos_promedio, esNocturno: d.es_nocturno }])
    )
    const z: number[][] = DIAS.map((_, di) =>
      horasActivas.map(h => {
        const item = lookup.get(`${di}-${h}`)
        if (!item) return 0
        // En modo nocturno exclusivo: si se especifica es_nocturno y no lo es, mostrar 0 (fuera de régimen)
        if (modo === 'nocturno' && item.esNocturno === false) return 0
        return item.avg
      })
    )
    return { zMatrix: z, xLabels: horasActivas.map(h => `${String(h).padStart(2, '0')}:00`) }
  }, [data, modo, horasActivas])

  const colorscaleDiurno24: [number, string][] = [
    [0.0, '#f0fdf4'],
    [0.35, '#fef08a'],
    [0.65, '#f59e0b'],
    [1.0, '#991b1b'],
  ]

  const colorscaleNocturno: [number, string][] = [
    [0.0, '#f8fafc'],
    [0.15, '#c7d2fe'],
    [0.35, '#818cf8'],
    [0.65, '#f59e0b'],
    [1.0, '#b91c1c'],
  ]

  const chartData: Data[] = useMemo(() => [
    {
      z: zMatrix,
      x: xLabels,
      y: DIAS,
      type: 'heatmap',
      colorscale: modo === 'nocturno' ? colorscaleNocturno : colorscaleDiurno24,
      hoverongaps: false,
      hovertemplate:
        modo === 'nocturno'
          ? '<b>%{y}</b> a las <b>%{x}</b><br>Ingresos nocturnos 24h: <b>%{z:.1f} pers/h</b><extra></extra>'
          : '<b>%{y}</b> a las <b>%{x}</b><br>Ingresos promedio: <b>%{z:.1f} pers/h</b><extra></extra>',
      colorbar: {
        title: { text: modo === 'nocturno' ? 'Noc/h' : 'Ingresos/h', side: 'right', font: { size: 10 } },
        thickness: 12,
        len: 0.85,
        tickfont: { size: 9, color: '#64748B' },
      },
    },
  ], [zMatrix, xLabels, modo])

  const layout: Partial<Layout> = useMemo(() => ({
    height: 280,
    margin: { t: 15, r: 20, b: modo === '24h' ? 42 : 35, l: 75 },
    yaxis: {
      autorange: 'reversed',
      tickfont: { size: 10, color: '#64748B' },
      showgrid: false,
    },
    xaxis: {
      tickfont: { size: modo === '24h' ? 8.5 : 9, color: '#64748B' },
      tickangle: modo === '24h' ? -45 : 0,
      showgrid: false,
    },
  }), [modo])

  return (
    <div className="w-full space-y-2">
      <div className="flex flex-wrap items-center justify-between text-xs px-1 gap-2">
        <span className="text-slate-500 font-medium flex items-center gap-1.5 text-[11px]">
          {modo === 'nocturno' ? (
            <>
              <Moon size={12} className="text-indigo-600" />
              <span>Extensión 24h (Fuera de Horario Regular: L-J 23h-07h | Vie 22h-06h)</span>
            </>
          ) : (
            <>
              <Clock size={12} className="text-uct-blue-primary" />
              <span>{modo === '24h' ? 'Ciclo 24 Horas Completo (00:00 - 23:00)' : 'Ventana Diurna Operativa (06:00 - 21:00)'}</span>
            </>
          )}
        </span>
        <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200">
          {(permitirModoNocturno || modoInicial === 'nocturno') && (
            <button
              type="button"
              onClick={() => setModo('nocturno')}
              className={`px-2 py-0.5 text-[10px] font-semibold rounded-md transition cursor-pointer ${
                modo === 'nocturno'
                  ? 'bg-indigo-600 text-white shadow-xs font-bold'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              Extensión 24h (22-07h)
            </button>
          )}
          <button
            type="button"
            onClick={() => setModo('24h')}
            className={`px-2 py-0.5 text-[10px] font-semibold rounded-md transition cursor-pointer ${
              modo === '24h'
                ? 'bg-white text-uct-blue-primary shadow-xs font-bold'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            24 Horas (00-23)
          </button>
          <button
            type="button"
            onClick={() => setModo('diurno')}
            className={`px-2 py-0.5 text-[10px] font-semibold rounded-md transition cursor-pointer ${
              modo === 'diurno'
                ? 'bg-white text-uct-blue-primary shadow-xs font-bold'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            Diurno (06-21)
          </button>
        </div>
      </div>

      <InteractiveChart
        data={chartData}
        layout={layout}
        filename="mapa_calor_ocupacion_dia_hora"
        height={320}
      />
    </div>
  )
}

export const HeatmapChart = memo(HeatmapChartComponent)
export default HeatmapChart
