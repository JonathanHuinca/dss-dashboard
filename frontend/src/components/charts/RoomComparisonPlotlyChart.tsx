import React, { useState } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { RoomComparisonResponse } from '../../api/client'
import { Data } from 'plotly.js-dist-min'
import { Layers, Users, Clock, CheckCircle2, Moon } from 'lucide-react'

interface Props {
  data?: RoomComparisonResponse
}

export function RoomComparisonPlotlyChart({ data }: Props) {
  const [rebanadaSeleccionada, setRebanadaSeleccionada] = useState<string | null>(null)

  const resumen_salas = (data?.resumen_salas && data.resumen_salas.length > 0)
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

  const flujo_horario_comparado = (data?.flujo_horario_comparado && data.flujo_horario_comparado.length > 0)
    ? data.flujo_horario_comparado
    : Array.from({ length: 24 }, (_, h) => ({
      hora: `${h.toString().padStart(2, '0')}:00`,
      hora_num: h,
      entradas_sala1: 0,
      entradas_sala2: 0,
    }))

  const getOrderWeight = (salaName: string) => {
    const s = salaName.toLowerCase()
    if (s.includes('sala 1') || s.includes('csf02') || s.includes('piso 2') || s.includes('2° piso')) return 1
    if (s.includes('sala 2') || s.includes('csf04') || s.includes('pecera') || s.includes('1er piso')) return 2
    return 3
  }


  const salasOrdenadas = [...resumen_salas].sort((a, b) => getOrderWeight(a.sala) - getOrderWeight(b.sala))

  // Datos para curva horaria comparada
  const chartHourlyData: Data[] = [
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
  ]

  const layoutHourly = {
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
  }

  // Datos para Donut de distribución de afluencia
  const labelsDonut = salasOrdenadas.map(s => s.sala.includes('Sala 1') ? 'Sala 1 (CSF02)' : 'Sala 2 (CSF04)')
  const pullArray = labelsDonut.map(l => (l === rebanadaSeleccionada ? 0.14 : 0))
  const baseColors = salasOrdenadas.map(s => s.sala.includes('Sala 1') ? '#002B49' : '#C59B27')

  const chartDonutData: Data[] = [
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

  const layoutDonut = {
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
                    {isSala1
                      ? 'Edificio 2, 2do Piso — Sala de Estudio y Biblioteca con Locker'
                      : 'Edificio 4, 1er Piso — Sala Pecera de Estudio'}
                  </p>
                </div>
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${isSala1
                      ? 'bg-blue-100/80 text-uct-blue-primary'
                      : 'bg-amber-100 text-amber-800'
                    }`}
                >
                  {s.edificio}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 py-2 border-y border-slate-200/60 text-center">
                <div className="p-1.5 bg-white rounded-lg border border-slate-100 shadow-2xs">
                  <span className="text-[10px] uppercase font-semibold text-slate-400 block">Capacidad</span>
                  <span className="text-sm font-extrabold text-slate-800">
                    {s.capacidad_asientos}
                  </span>
                  <span className="text-[9px] text-slate-500 block">asientos</span>
                </div>
                <div className="p-1.5 bg-white rounded-lg border border-slate-100 shadow-2xs">
                  <span className="text-[10px] uppercase font-semibold text-slate-400 block">Afluencia Total</span>
                  <span className="text-sm font-extrabold text-slate-800">
                    {s.total_marcajes.toLocaleString('es-CL')}
                  </span>
                  <span className="text-[9px] text-slate-500 block">
                    {s.porcentaje_afluencia}% del total
                  </span>
                </div>
                <div className="p-1.5 bg-white rounded-lg border border-slate-100 shadow-2xs">
                  <span className="text-[10px] uppercase font-semibold text-slate-400 block">Visitantes Únicos</span>
                  <span className="text-sm font-extrabold text-slate-800">
                    {s.usuarios_unicos.toLocaleString('es-CL')}
                  </span>
                  <span className="text-[9px] text-slate-500 block">personas</span>
                </div>
              </div>

              <div className="flex items-center justify-between text-[11px] pt-2 text-slate-600">
                <span className="flex items-center gap-1">
                  <CheckCircle2 size={12} className="text-emerald-600" />
                  Accesos: 1 Torniquete + 1 Universal
                </span>
                {s.permite_24h_examenes && (
                  <span className="flex items-center gap-1 font-semibold text-amber-700 bg-amber-100/60 px-2 py-0.5 rounded-md">
                    <Moon size={11} />
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
