import React, { useState, memo, useMemo } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { RoomComparisonResponse } from '../../api/client'
import type { Data } from 'plotly.js-dist-min'
import { Layers } from 'lucide-react'

interface Props {
  data?: RoomComparisonResponse
}

function RoomComparisonPlotlyChartComponent({ data }: Props) {
  const [rebanadaSeleccionada, setRebanadaSeleccionada] = useState<string | null>(null)

  const resumen_salas = useMemo(() => {
    return (data?.resumen_salas && data.resumen_salas.length > 0)
      ? data.resumen_salas
      : [
        {
          sala: 'Sala 1 (CSF02)',
          total_marcajes: 0,
          usuarios_unicos: 0,
          entradas: 0,
          salidas: 0,
          porcentaje_afluencia: 0,
          capacidad_asientos: 124,
          edificio: 'CSF02',
          permite_24h_examenes: false,
        },
        {
          sala: 'Sala 2 (CSF04 Pecera)',
          total_marcajes: 0,
          usuarios_unicos: 0,
          entradas: 0,
          salidas: 0,
          porcentaje_afluencia: 0,
          capacidad_asientos: 226,
          edificio: 'CSF04',
          permite_24h_examenes: true,
        },
      ]
  }, [data?.resumen_salas])

  const flujo_horario_comparado = useMemo(() => {
    return (data?.flujo_horario_comparado && data.flujo_horario_comparado.length > 0)
      ? data.flujo_horario_comparado
      : Array.from({ length: 24 }, (_, h) => ({
        hora: `${h.toString().padStart(2, '0')}:00`,
        hora_num: h,
        entradas_sala1: 0,
        entradas_sala2: 0,
      }))
  }, [data?.flujo_horario_comparado])

  const getOrderWeight = (salaName: string) => {
    const s = salaName.toLowerCase()
    if (s.includes('sala 1') || s.includes('csf02') || s.includes('piso 2') || s.includes('2° piso')) return 1
    if (s.includes('sala 2') || s.includes('csf04') || s.includes('pecera') || s.includes('1er piso')) return 2
    return 3
  }

  const salasOrdenadas = useMemo(() => {
    return [...resumen_salas].sort((a, b) => getOrderWeight(a.sala) - getOrderWeight(b.sala))
  }, [resumen_salas])

  // Datos para curva horaria comparada
  const chartHourlyData = useMemo<Data[]>(() => [
    {
      x: flujo_horario_comparado.map(d => d.hora),
      y: flujo_horario_comparado.map(d => d.entradas_sala1),
      name: 'Sala 1 (CSF02 — 2° Piso)',
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: '#002B49', width: 2.5, shape: 'spline' },
      marker: { size: 5, color: '#002B49' },
      hovertemplate: '<b>Sala 1 (CSF02)</b><br>Hora: %{x}<br>Entradas: <b>%{y:,}</b><extra></extra>',
    },
    {
      x: flujo_horario_comparado.map(d => d.hora),
      y: flujo_horario_comparado.map(d => d.entradas_sala2),
      name: 'Sala 2 (CSF04 — Pecera 1° Piso)',
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: '#C59B27', width: 2.5, shape: 'spline' },
      marker: { size: 5, color: '#C59B27' },
      hovertemplate: '<b>Sala 2 (CSF04 Pecera)</b><br>Hora: %{x}<br>Entradas: <b>%{y:,}</b><extra></extra>',
    },
  ], [flujo_horario_comparado])

  const layoutHourly = useMemo(() => ({
    title: {
      text: 'Afluencia Horaria Comparada por Sala (Ciclo 00:00 a 23:00)',
      font: { size: 12, color: '#1E293B' },
      x: 0.02,
      xanchor: 'left' as const,
    },
    xaxis: {
      title: { text: '' },
      automargin: true,
      tickfont: { size: 10, color: '#475569' },
      gridcolor: '#F1F5F9',
    },
    yaxis: {
      title: { text: 'Ingresos Registrados', font: { size: 10, color: '#64748B' } },
      automargin: true,
      tickfont: { size: 10, color: '#64748B' },
      gridcolor: '#F1F5F9',
    },
    margin: { t: 52, r: 20, b: 40, l: 45 },
    showlegend: true,
    legend: {
      orientation: 'h' as const,
      x: 0.5,
      xanchor: 'center' as const,
      y: 1.08,
      yanchor: 'bottom' as const,
      font: { size: 10.5, color: '#334155' },
    },
  }), [])

  // Datos para Donut de distribución de afluencia
  const { labelsDonut, baseColors } = useMemo(() => {
    const lbls = salasOrdenadas.map(s => s.sala.includes('Sala 1') ? 'Sala 1 (CSF02)' : 'Sala 2 (CSF04)')
    const colors = salasOrdenadas.map(s => s.sala.includes('Sala 1') ? '#002B49' : '#C59B27')
    return { labelsDonut: lbls, baseColors: colors }
  }, [salasOrdenadas])

  const chartDonutData = useMemo<Data[]>(() => {
    const pullArray = labelsDonut.map(l => (l === rebanadaSeleccionada ? 0.14 : 0))
    return [
      {
        values: salasOrdenadas.map(s => s.total_marcajes),
        labels: labelsDonut,
        type: 'pie',
        hole: 0.55,
        pull: pullArray,
        marker: {
          colors: rebanadaSeleccionada
            ? labelsDonut.map((l, idx) => (l === rebanadaSeleccionada ? baseColors[idx] : '#E2E8F0'))
            : baseColors,
          line: {
            color: rebanadaSeleccionada
              ? labelsDonut.map(l => (l === rebanadaSeleccionada ? '#002B49' : '#FFFFFF'))
              : '#FFFFFF',
            width: rebanadaSeleccionada ? labelsDonut.map(l => (l === rebanadaSeleccionada ? 2.5 : 1)) : 2,
          },
        },
        textinfo: 'percent',
        textposition: 'inside',
        insidetextfont: { color: '#FFFFFF', size: 12, family: 'Inter, sans-serif' },
        hoverinfo: 'label+value+percent',
      },
    ]
  }, [salasOrdenadas, labelsDonut, baseColors, rebanadaSeleccionada])

  const layoutDonut = useMemo(() => ({
    title: {
      text: 'Participación por Sala',
      font: { size: 11.5, color: '#1E293B' },
      x: 0.02,
      xanchor: 'left' as const,
    },
    margin: { t: 35, r: 10, b: 50, l: 10 },
    showlegend: true,
    legend: {
      orientation: 'h' as const,
      x: 0.5,
      xanchor: 'center' as const,
      y: -0.12,
      yanchor: 'top' as const,
      font: { size: 10, color: '#334155' },
      itemclick: false as const,
      itemdoubleclick: false as const,
    },
  }), [])

  const handleDonutClick = (event: Readonly<Plotly.PlotMouseEvent>) => {
    if (event.points && event.points.length > 0) {
      const label = (event.points[0] as any).label
      if (label) {
        setRebanadaSeleccionada(prev => (prev === label ? null : label))
      }
    }
  }

  return (
    <div className="w-full space-y-4">
      {/* Tarjetas de Ficha Técnica y Estado Físico por Sala */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        {salasOrdenadas.map(s => {
          const isSala1 = getOrderWeight(s.sala) === 1
          return (
            <div
              key={s.sala}
              className={`p-3.5 rounded-2xl border transition-all shadow-xs ${isSala1
                  ? 'bg-slate-50/70 border-slate-200/90'
                  : 'bg-amber-50/30 border-amber-200/70'
                }`}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2.5 h-2.5 rounded-full ${isSala1 ? 'bg-uct-blue-primary' : 'bg-amber-600'
                        }`}
                    />
                    <h4 className="text-xs font-bold text-slate-800 tracking-tight">
                      {s.sala}
                    </h4>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Edificio {s.edificio} • Capacidad física: {s.capacidad_asientos} asientos
                  </p>
                </div>
                {s.permite_24h_examenes && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 border border-amber-300 font-bold">
                    Horario Extendido Exámenes
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Barra de Leyenda de Identificación Cromática por Sala */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-50/90 p-3 rounded-xl border border-slate-200/90 shadow-2xs">
        <div className="flex items-center gap-2 text-xs font-bold text-slate-700">
          <Layers size={14} className="text-uct-blue-primary" />
          <span>Leyenda Cromática por Sala:</span>
        </div>
        <div className="flex flex-wrap items-center gap-5 text-xs">
          <div className="flex items-center gap-2">
            <span className="w-3.5 h-3.5 rounded-md bg-[#002B49] shadow-2xs border border-white shrink-0" />
            <span className="font-bold text-slate-900">Sala 1:</span>
            <span className="text-slate-600">CSF02 — 2° Piso (Estudio y Biblioteca con Locker, 124 asientos)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3.5 h-3.5 rounded-md bg-[#C59B27] shadow-2xs border border-white shrink-0" />
            <span className="font-bold text-amber-900">Sala 2:</span>
            <span className="text-slate-600">CSF04 — 1° Piso (Pecera de Estudio 24h, 226 asientos)</span>
          </div>
        </div>
      </div>

      {/* Gráficos Plotly: Curva Horaria y Distribución */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3.5">
        <div className="lg:col-span-2 bg-white p-3.5 rounded-2xl border border-slate-200/80 shadow-xs">
          <InteractiveChart
            data={chartHourlyData}
            layout={layoutHourly}
            filename="flujo_horario_comparado_salas_biblioteca"
            height={360}
          />
        </div>
        <div className="bg-white p-3.5 rounded-2xl border border-slate-200/80 shadow-xs">
          <InteractiveChart
            data={chartDonutData}
            layout={layoutDonut}
            filename="participacion_salas_biblioteca"
            height={360}
            onClick={handleDonutClick}
          />
        </div>
      </div>
    </div>
  )
}

export const RoomComparisonPlotlyChart = memo(RoomComparisonPlotlyChartComponent)
export default RoomComparisonPlotlyChart
