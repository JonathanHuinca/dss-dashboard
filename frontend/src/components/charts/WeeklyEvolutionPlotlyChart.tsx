import React, { useState, useMemo } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { WeeklyEvolutionPoint, obtenerResumenAnualCalendario, DiaCalendarioResumen } from '../../api/client'
import { useQuery } from '@tanstack/react-query'
import { Data } from 'plotly.js-dist-min'
import { Flag, AlertOctagon, Calendar, BookOpen } from 'lucide-react'
import { formatDayMonthSpanish } from '../../types/dateRange'

interface Props {
  data: WeeklyEvolutionPoint[]
  anio?: number
}

function calcularSemanaIso(fechaIso: string): string {
  try {
    const d = new Date(fechaIso + 'T12:00:00Z')
    const target = new Date(d.valueOf())
    const dayNr = (d.getUTCDay() + 6) % 7
    target.setUTCDate(target.getUTCDate() - dayNr + 3)
    const firstThursday = target.valueOf()
    target.setUTCMonth(0, 1)
    if (target.getUTCDay() !== 4) {
      target.setUTCMonth(0, 1 + ((4 - target.getUTCDay()) + 7) % 7)
    }
    const numSemana = 1 + Math.ceil((firstThursday - target.valueOf()) / 604800000)
    return `Semana ${String(numSemana).padStart(2, '0')}`
  } catch {
    return ''
  }
}

export function WeeklyEvolutionPlotlyChart({ data, anio = 2026 }: Props) {
  // Filtros de capas visuales en el gráfico
  const [mostrarCierres, setMostrarCierres] = useState(true)
  const [mostrarSuspensiones, setMostrarSuspensiones] = useState(true)
  const [mostrarParosFed, setMostrarParosFed] = useState(true)
  const [mostrarParosCarrera, setMostrarParosCarrera] = useState(true)
  const [mostrarExamenes, setMostrarExamenes] = useState(false)

  // Consulta de calendario anual
  const { data: diasCalendario = [] } = useQuery({
    queryKey: ['calendario-resumen-anual', anio],
    queryFn: () => obtenerResumenAnualCalendario(anio),
    staleTime: 30_000,
  })

  // Agrupar eventos por semana ISO
  const mapaSemanas = useMemo(() => {
    const mapa = new Map<string, {
      tieneCierre: boolean
      tieneSuspension: boolean
      tieneParoFed: boolean
      tieneParoCarrera: boolean
      tieneExamen: boolean
      detalles: string[]
    }>()

    diasCalendario.forEach((d: DiaCalendarioResumen) => {
      const sem = calcularSemanaIso(d.fecha)
      if (!sem) return
      if (!mapa.has(sem)) {
        mapa.set(sem, {
          tieneCierre: false,
          tieneSuspension: false,
          tieneParoFed: false,
          tieneParoCarrera: false,
          tieneExamen: false,
          detalles: [],
        })
      }
      const entry = mapa.get(sem)!
      if (d.is_holiday || d.is_break) {
        entry.tieneCierre = true
        if (d.descripcion && !entry.detalles.includes(d.descripcion)) {
          entry.detalles.push(d.descripcion)
        }
      }
      if (d.suspension_actividades && !d.is_holiday && !d.is_break && !d.is_strike_federado) {
        entry.tieneSuspension = true
        if (d.descripcion && !entry.detalles.includes(d.descripcion)) {
          entry.detalles.push(d.descripcion)
        }
      }
      if (d.is_strike_federado) {
        entry.tieneParoFed = true
        if (d.descripcion && !entry.detalles.includes(d.descripcion)) {
          entry.detalles.push(d.descripcion)
        }
      }
      if (d.is_strike_carrera) {
        entry.tieneParoCarrera = true
        if (d.descripcion && !entry.detalles.includes(d.descripcion)) {
          entry.detalles.push(d.descripcion)
        }
      }
      if (d.is_exam_period) {
        entry.tieneExamen = true
      }
    })

    return mapa
  }, [diasCalendario])

  // Franjas de fondo (shapes) para marcar semanas con paros, suspensiones, cierres o exámenes
  const shapes = useMemo(() => {
    const res: any[] = []
    const semanasDisponibles = data.map(d => d.semana_iso)

    semanasDisponibles.forEach((sem, idx) => {
      const info = mapaSemanas.get(sem)
      if (!info) return

      let color = ''
      if (mostrarParosFed && info.tieneParoFed) {
        color = 'rgba(239, 68, 68, 0.25)' // Rojo para Paro Federado
      } else if (mostrarParosCarrera && info.tieneParoCarrera) {
        color = 'rgba(245, 158, 11, 0.22)' // Naranja/Ámbar para Paro Carrera
      } else if (mostrarSuspensiones && info.tieneSuspension) {
        color = 'rgba(249, 115, 22, 0.25)' // Naranja intenso para Suspensión de Sala/Recinto
      } else if (mostrarCierres && info.tieneCierre) {
        color = 'rgba(156, 163, 175, 0.22)' // Gris suave para Cierres/Feriados
      } else if (mostrarExamenes && info.tieneExamen) {
        color = 'rgba(99, 102, 241, 0.15)' // Índigo para Exámenes
      }

      if (color) {
        res.push({
          type: 'rect',
          xref: 'x',
          yref: 'paper',
          x0: idx - 0.45,
          x1: idx + 0.45,
          y0: 0,
          y1: 1,
          fillcolor: color,
          line: { width: 0 },
          layer: 'below',
        })
      }
    })

    return res
  }, [data, mapaSemanas, mostrarCierres, mostrarSuspensiones, mostrarParosFed, mostrarParosCarrera, mostrarExamenes])

  // Custom data con información del contexto para el hover
  const customDataList = data.map(d => {
    const info = mapaSemanas.get(d.semana_iso)
    if (!info) return ''
    const parts: string[] = []
    if (info.tieneParoFed) parts.push('<b>Paro Federado FEUCT</b>')
    if (info.tieneParoCarrera) parts.push('<b>Paro por Carrera</b>')
    if (info.tieneSuspension) parts.push('<b>Suspensión de Actividades</b>')
    if (info.tieneCierre) parts.push('Feriado o Receso')
    if (info.tieneExamen) parts.push('Período de Exámenes')
    if (info.detalles.length > 0) {
      parts.push(`Detalle: ${info.detalles.slice(0, 2).join(' | ')}`)
    }
    return parts.length > 0 ? parts.join('<br>') : ''
  })

  // Etiquetas formateadas para el eje X en español
  const xLabels = data.map(d =>
    d.inicio_semana ? `${d.semana_iso} (${formatDayMonthSpanish(d.inicio_semana)})` : d.semana_iso
  )

  const chartData: Data[] = [
    {
      x: xLabels,
      y: data.map(d => d.total_asistencias),
      customdata: customDataList,
      name: 'Total Marcajes',
      type: 'bar',
      marker: { color: '#003865' },
      text: data.map(d => d.total_asistencias > 0 ? d.total_asistencias.toLocaleString('es-CL') : ''),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      hovertemplate: '<b>%{x}</b><br>Marcajes: %{y:,}<br>%{customdata}<extra></extra>',
    },
    {
      x: xLabels,
      y: data.map(d => d.usuarios_unicos),
      customdata: customDataList,
      name: 'Estudiantes Únicos',
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: '#C59B27', width: 3 },
      marker: { color: '#C59B27', size: 6 },
      hovertemplate: '<b>%{x}</b><br>Únicos: %{y:,}<br>%{customdata}<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Evolución de Asistencia y Contexto Anual por Semana' },
    margin: { t: 40, r: 25, b: 85, l: 55 },
    xaxis: {
      title: { text: 'Semana Académica (ISO)' },
      automargin: true,
      tickangle: -45,
      tickfont: { size: 10, color: '#475569' },
      categoryorder: 'array' as const,
      categoryarray: xLabels,
    },
    yaxis: {
      title: { text: 'Cantidad de Personas' },
      automargin: true,
    },
    barmode: 'group' as const,
    shapes,
  }

  return (
    <div className="space-y-2">
      {/* Controles de Capas Contextuales sobre la gráfica */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-2 bg-slate-50 rounded-xl border border-slate-200/80 text-[11px]">
        <span className="font-semibold text-slate-700 flex items-center gap-1.5">
          <Calendar size={13} className="text-slate-500" />
          <span>Capas Contextuales:</span>
        </span>

        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
            <input
              type="checkbox"
              checked={mostrarParosFed}
              onChange={(e) => setMostrarParosFed(e.target.checked)}
              className="rounded text-red-600 focus:ring-red-500 h-3.5 w-3.5 cursor-pointer"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-sm bg-red-500/70 shrink-0" />
            <span>Paros Federados</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
            <input
              type="checkbox"
              checked={mostrarParosCarrera}
              onChange={(e) => setMostrarParosCarrera(e.target.checked)}
              className="rounded text-amber-600 focus:ring-amber-500 h-3.5 w-3.5 cursor-pointer"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-sm bg-amber-500/70 shrink-0" />
            <span>Paros Carrera</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
            <input
              type="checkbox"
              checked={mostrarSuspensiones}
              onChange={(e) => setMostrarSuspensiones(e.target.checked)}
              className="rounded text-orange-500 focus:ring-orange-500 h-3.5 w-3.5 cursor-pointer"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-sm bg-orange-500/80 shrink-0" />
            <span>Suspensiones</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
            <input
              type="checkbox"
              checked={mostrarCierres}
              onChange={(e) => setMostrarCierres(e.target.checked)}
              className="rounded text-slate-600 focus:ring-slate-500 h-3.5 w-3.5 cursor-pointer"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-sm bg-slate-400/70 shrink-0" />
            <span>Cierres / Feriados</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
            <input
              type="checkbox"
              checked={mostrarExamenes}
              onChange={(e) => setMostrarExamenes(e.target.checked)}
              className="rounded text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5 cursor-pointer"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-sm bg-indigo-500/70 shrink-0" />
            <span>Exámenes / 24h</span>
          </label>
        </div>
      </div>

      <InteractiveChart
        data={chartData}
        layout={layout}
        filename="evolucion_semanal_biblioteca"
        height={320}
      />
    </div>
  )
}

