import React, { useState, useMemo, useEffect } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { CurricularDistributionResponse } from '../../api/client'
import { Data } from 'plotly.js-dist-min'
import {
  ShieldCheck,
  BookOpen,
  Building2,
  Calendar,
  Users,
  Footprints,
  PieChart,
  BarChart3,
  Filter,
} from 'lucide-react'

interface Props {
  data?: CurricularDistributionResponse
}

const PALETA_COLORES = [
  '#002B49',
  '#0284C7',
  '#0D9488',
  '#16A34A',
  '#D97706',
  '#7C3AED',
  '#DB2777',
  '#EA580C',
  '#475569',
  '#2563EB',
  '#059669',
  '#9333EA',
  '#CA8A04',
  '#4B5563',
  '#64748B',
]

export function CurricularDistributionPlotlyChart({ data }: Props) {
  const [agrupacion, setAgrupacion] = useState<'carreras' | 'facultades' | 'cohortes'>('carreras')
  const [metrica, setMetrica] = useState<'visitas' | 'alumnos'>('visitas')
  const [topN, setTopN] = useState<number | 'todas'>(10)
  const [rebanadaSeleccionada, setRebanadaSeleccionada] = useState<string | null>(null)

  // Restablecer selección al cambiar filtros internos
  useEffect(() => {
    setRebanadaSeleccionada(null)
  }, [agrupacion, metrica, topN])

  if (!data || !data.carreras || data.carreras.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-slate-400 text-xs">
        Sin datos curriculares disponibles para el período o filtros seleccionados.
      </div>
    )
  }

  const {
    carreras = [],
    facultades = [],
    cohortes = [],
    total_estudiantes_catalogados = 0,
    total_eventos_asistencia = 0,
    total_estudiantes_asistentes = 0,
  } = data

  // Ordenar carreras completas según la métrica activa
  const carrerasOrdenadasSegunMetrica = useMemo(() => {
    return [...carreras].sort((a, b) => {
      const valA = metrica === 'visitas' ? (a.eventos_asistencia ?? 0) : (a.estudiantes_asistentes ?? a.total_estudiantes ?? 0)
      const valB = metrica === 'visitas' ? (b.eventos_asistencia ?? 0) : (b.estudiantes_asistentes ?? b.total_estudiantes ?? 0)
      return valB - valA
    })
  }, [carreras, metrica])

  // Preparar elementos según agrupación y Top N
  const elementos = useMemo(() => {
    if (agrupacion === 'carreras') {
      const seleccionadas =
        topN === 'todas'
          ? carrerasOrdenadasSegunMetrica
          : carrerasOrdenadasSegunMetrica.slice(0, typeof topN === 'number' ? topN : 10)

      return seleccionadas.map((c) => ({
        nombre: c.carrera,
        facultad: c.facultad,
        visitas: c.eventos_asistencia ?? 0,
        alumnos: c.estudiantes_asistentes ?? c.total_estudiantes,
        pct_visitas: c.porcentaje_eventos ?? 0,
        pct_alumnos: c.porcentaje_asistentes ?? c.porcentaje,
      }))
    } else if (agrupacion === 'facultades') {
      return facultades.map((f) => ({
        nombre: f.facultad,
        facultad: f.facultad,
        visitas: f.eventos_asistencia ?? 0,
        alumnos: f.estudiantes_asistentes ?? f.total_estudiantes,
        pct_visitas: f.porcentaje_eventos ?? 0,
        pct_alumnos: f.porcentaje_asistentes ?? f.porcentaje,
      }))
    } else {
      return cohortes
        .filter((coh) => coh.cohorte >= 2020)
        .map((coh) => ({
          nombre: coh.etiqueta,
          facultad: 'Padrón UCT',
          visitas: coh.eventos_asistencia ?? 0,
          alumnos: coh.estudiantes_asistentes ?? coh.total_estudiantes,
          pct_visitas: coh.porcentaje_eventos ?? 0,
          pct_alumnos: coh.porcentaje_asistentes ?? coh.porcentaje_estudiantes,
        }))
    }
  }, [agrupacion, carrerasOrdenadasSegunMetrica, topN, facultades, cohortes])

  // Ordenar elementos según métrica
  const elementosOrdenados = useMemo(() => {
    return [...elementos].sort((a, b) =>
      metrica === 'visitas' ? b.visitas - a.visitas : b.alumnos - a.alumnos
    )
  }, [elementos, metrica])

  // 1. Gráfico de Barras (Izquierda - Absolutos)
  const elementosBarras = useMemo(() => {
    return [...elementosOrdenados].reverse()
  }, [elementosOrdenados])

  const tituloBarras =
    agrupacion === 'carreras'
      ? `${topN === 'todas' ? 'Todas las Carreras' : `Top ${topN} Carreras`} por ${
          metrica === 'visitas' ? 'Visitas (Afluencia)' : 'Estudiantes Asistentes'
        }`
      : agrupacion === 'facultades'
      ? `Demanda por Facultad (${metrica === 'visitas' ? 'Visitas' : 'Estudiantes Asistentes'})`
      : `Demanda por Cohorte (${metrica === 'visitas' ? 'Visitas' : 'Estudiantes Asistentes'})`

  const chartBarrasData: Data[] = [
    {
      type: 'bar',
      x: elementosBarras.map((e) => (metrica === 'visitas' ? e.visitas : e.alumnos)),
      y: elementosBarras.map((e) => e.nombre),
      orientation: 'h',
      name: metrica === 'visitas' ? 'Total Visitas (Afluencia)' : 'Estudiantes Asistentes',
      marker: {
        color: elementosBarras.map((_, i) =>
          i === elementosBarras.length - 1
            ? '#002B49'
            : i >= elementosBarras.length - 3
            ? '#0284C7'
            : '#94A3B8'
        ),
      },
      text: elementosBarras.map(
        (e) =>
          `${(metrica === 'visitas' ? e.visitas : e.alumnos).toLocaleString('es-CL')} ${
            metrica === 'visitas' ? 'visitas' : 'alumnos'
          }`
      ),
      textposition: 'auto',
      hovertemplate:
        '<b>%{y}</b><br>' +
        (metrica === 'visitas' ? 'Visitas en Período: ' : 'Estudiantes Asistentes: ') +
        '<b>%{x:,}</b><extra></extra>',
    },
  ]

  const alturaBarras = useMemo(() => {
    if (agrupacion === 'carreras') {
      if (topN === 'todas') {
        return Math.max(420, elementosBarras.length * 24)
      }
      if (typeof topN === 'number' && topN > 10) {
        return Math.max(400, topN * 26)
      }
    }
    return 400
  }, [agrupacion, topN, elementosBarras.length])

  const layoutBarras = {
    title: {
      text: tituloBarras,
      font: { size: 12, color: '#1E293B' },
      x: 0.02,
      xanchor: 'left' as const,
    },
    xaxis: {
      title: {
        text: metrica === 'visitas' ? 'Total Visitas en Período' : 'Total Estudiantes Únicos',
        font: { size: 10, color: '#64748B' },
      },
      automargin: true,
      tickfont: { size: 9.5, color: '#64748B' },
      gridcolor: '#F1F5F9',
    },
    yaxis: {
      title: {
        text: agrupacion === 'carreras' ? 'Carrera / Programa' : agrupacion === 'facultades' ? 'Facultad' : 'Cohorte',
        font: { size: 10, color: '#64748B' },
      },
      automargin: true,
      tickfont: { size: 9, color: '#334155' },
    },
    margin: { t: 35, r: 20, b: 35, l: agrupacion === 'carreras' ? 180 : 160 },
  }

  // 2. Gráfico Donut de Porcentajes (Derecha)
  const chartDonutData: Data[] = useMemo(() => {
    let itemsDonut = elementosOrdenados
    if (agrupacion === 'carreras' && (topN === 'todas' || (typeof topN === 'number' && topN > 10)) && elementosOrdenados.length > 10) {
      const top9 = elementosOrdenados.slice(0, 9)
      const resto = elementosOrdenados.slice(9)
      const visitasResto = resto.reduce((acc, curr) => acc + curr.visitas, 0)
      const alumnosResto = resto.reduce((acc, curr) => acc + curr.alumnos, 0)
      itemsDonut = [
        ...top9,
        {
          nombre: `Otras (${resto.length} carreras)`,
          facultad: 'Resto de carreras',
          visitas: visitasResto,
          alumnos: alumnosResto,
          pct_visitas: 0,
          pct_alumnos: 0,
        },
      ]
    }

    const labels = itemsDonut.map((e) => e.nombre)
    const pullArray = labels.map((l) => (l === rebanadaSeleccionada ? 0.14 : 0))
    const markerColors = PALETA_COLORES.slice(0, itemsDonut.length)

    return [
      {
        type: 'pie',
        hole: 0.48,
        labels,
        values: itemsDonut.map((e) =>
          metrica === 'visitas' ? e.visitas : e.alumnos
        ),
        textinfo: 'percent',
        textposition: 'inside',
        pull: pullArray,
        marker: {
          colors: rebanadaSeleccionada
            ? labels.map((l, idx) => (l === rebanadaSeleccionada ? markerColors[idx % markerColors.length] : '#E2E8F0'))
            : markerColors,
          line: {
            color: rebanadaSeleccionada
              ? labels.map((l) => (l === rebanadaSeleccionada ? '#002B49' : '#FFFFFF'))
              : '#FFFFFF',
            width: rebanadaSeleccionada
              ? labels.map((l) => (l === rebanadaSeleccionada ? 2.5 : 1))
              : 1.5,
          },
        },
        hovertemplate:
          '<b>%{label}</b><br>' +
          (metrica === 'visitas' ? 'Visitas: ' : 'Alumnos: ') +
          '<b>%{value:,}</b><br>Participación: <b>%{percent}</b><extra></extra>',
      },
    ]
  }, [elementosOrdenados, agrupacion, topN, metrica, rebanadaSeleccionada])

  const layoutDonut = {
    title: {
      text: `Participación Porcentual (%) por ${
        agrupacion === 'carreras'
          ? (topN === 'todas' || (typeof topN === 'number' && topN > 10) ? 'Carrera (Top 9 + Otras)' : `Carrera (Top ${topN})`)
          : agrupacion === 'facultades'
          ? 'Facultad'
          : 'Cohorte'
      }`,
      font: { size: 11.5, color: '#1E293B' },
      x: 0.02,
      xanchor: 'left' as const,
    },
    showlegend: true,
    legend: {
      orientation: 'h' as const,
      x: 0.5,
      xanchor: 'center' as const,
      y: -0.12,
      yanchor: 'top' as const,
      font: { size: 9.5, color: '#334155' },
      itemclick: false as const,
      itemdoubleclick: false as const,
    },
    margin: { t: 35, r: 15, b: 85, l: 15 },
  }

  const handleDonutClick = (event: Readonly<Plotly.PlotMouseEvent>) => {
    if (event.points && event.points.length > 0) {
      const label = (event.points[0] as any).label
      if (label) {
        setRebanadaSeleccionada((prev) => (prev === label ? null : label))
      }
    }
  }

  return (
    <div className="w-full space-y-4">
      {/* Insignia y Resumen Dinámico del Período */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-slate-50 border border-slate-200/90 rounded-xl text-xs shadow-2xs">
        <div className="flex items-center gap-2 text-slate-700">
          <ShieldCheck size={16} className="text-emerald-600 shrink-0" />
          <span>
            <strong>Datos filtrados por período y alcance seleccionado:</strong> Métricas calculadas en tiempo real cruzando con el maestro curricular bajo Ley 21.719.
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 flex items-center gap-1">
            <Footprints size={12} />
            {total_eventos_asistencia.toLocaleString('es-CL')} visitas en período
          </span>
          <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-blue-100 text-uct-blue-primary flex items-center gap-1">
            <Users size={12} />
            {total_estudiantes_asistentes.toLocaleString('es-CL')} alumnos asistentes
          </span>
          <span className="text-[11px] font-medium px-2 py-0.5 rounded-md bg-slate-200 text-slate-700">
            Padrón: {total_estudiantes_catalogados.toLocaleString('es-CL')}
          </span>
        </div>
      </div>

      {/* Controles de Selección: Agrupación, Top N y Métrica */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
        {/* Selector de Agrupación */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-xl border border-slate-200">
            <button
              onClick={() => setAgrupacion('carreras')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                agrupacion === 'carreras'
                  ? 'bg-white text-uct-blue-primary shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <BookOpen size={13} />
              <span>Por Carrera</span>
            </button>

            <button
              onClick={() => setAgrupacion('facultades')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                agrupacion === 'facultades'
                  ? 'bg-white text-uct-blue-primary shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Building2 size={13} />
              <span>Por Facultad</span>
            </button>

            <button
              onClick={() => setAgrupacion('cohortes')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                agrupacion === 'cohortes'
                  ? 'bg-white text-uct-blue-primary shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Calendar size={13} />
              <span>Por Cohorte (Año)</span>
            </button>
          </div>

          {/* Selector de Top N para Carreras */}
          {agrupacion === 'carreras' && (
            <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl border border-slate-200">
              <span className="text-[10.5px] font-bold text-slate-500 uppercase px-1.5 flex items-center gap-1">
                <Filter size={12} className="text-uct-blue-primary" />
                <span>Carreras:</span>
              </span>
              {[5, 10, 15, 20].map((num) => (
                <button
                  key={num}
                  type="button"
                  onClick={() => setTopN(num)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    topN === num
                      ? 'bg-uct-blue-primary text-white shadow-xs'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
                  }`}
                >
                  Top {num}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setTopN('todas')}
                className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  topN === 'todas'
                    ? 'bg-uct-blue-primary text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
                }`}
              >
                Todas ({carreras.length})
              </button>
            </div>
          )}
        </div>

        {/* Selector de Métrica (Visitas vs Cantidad de Alumnos) */}
        <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-xl border border-slate-200">
          <span className="text-[10.5px] font-bold text-slate-500 uppercase px-2">Métrica:</span>
          <button
            onClick={() => setMetrica('visitas')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              metrica === 'visitas'
                ? 'bg-uct-blue-primary text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900 bg-transparent'
            }`}
          >
            <Footprints size={13} />
            <span>Por Visitas (Torniquetes)</span>
          </button>

          <button
            onClick={() => setMetrica('alumnos')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              metrica === 'alumnos'
                ? 'bg-uct-blue-primary text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900 bg-transparent'
            }`}
          >
            <Users size={13} />
            <span>Por Cantidad de Alumnos</span>
          </button>
        </div>
      </div>

      {/* Cuadrícula Lado a Lado: Gráfico de Barras Absolutas + Gráfico Donut con Tamaño Máximo Fijo */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        {/* Columna Izquierda (7 columnas): Gráfico de Barras con Valores Absolutos */}
        <div className="xl:col-span-7 bg-white p-3.5 rounded-2xl border border-slate-200/80 shadow-xs">
          <div className="flex items-center gap-1.5 mb-2 text-slate-700 text-xs font-bold">
            <BarChart3 size={15} className="text-uct-blue-primary" />
            <span>Valores Absolutos de Demanda</span>
          </div>
          <InteractiveChart
            data={chartBarrasData}
            layout={layoutBarras}
            filename={`distribucion_${agrupacion}_${metrica}_uct`}
            height={alturaBarras}
          />
        </div>

        {/* Columna Derecha (5 columnas): Gráfico Donut de Porcentajes con Límite Fijo Óptimo */}
        <div className="xl:col-span-5 bg-white p-3.5 rounded-2xl border border-slate-200/80 shadow-xs xl:sticky xl:top-4">
          <div className="flex items-center gap-1.5 mb-2 text-slate-700 text-xs font-bold">
            <PieChart size={15} className="text-uct-blue-primary" />
            <span>Distribución Porcentual (%)</span>
          </div>
          <InteractiveChart
            data={chartDonutData}
            layout={layoutDonut}
            filename={`porcentaje_${agrupacion}_${metrica}_uct`}
            height={480}
            onClick={handleDonutClick}
          />
        </div>
      </div>
    </div>
  )
}
