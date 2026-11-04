import { useState, useMemo } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { ForecastPoint, obtenerResumenAnualCalendario, DiaCalendarioResumen, fetchHorarios, HorarioOperacion } from '../../api/client'
import { Data, Layout, Shape, Annotations } from 'plotly.js-dist-min'
import { Activity, Users, RotateCw, Calendar } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

interface Props {
  actual?: { bucket: string; ingresos?: number; entradas?: number }[]
  forecast: ForecastPoint[]
  historico7d?: ForecastPoint[]
  pronostico7d?: ForecastPoint[]
  capacidad?: number
  salaNombre?: string
  recinto?: string
  onRetrain?: () => void
  isRetraining?: boolean
  retrainMsg?: string | null
  esAdminSistema?: boolean
}

const DIAS_SEMANA_COMPLETOS = [
  'Domingo',
  'Lunes',
  'Martes',
  'Miércoles',
  'Jueves',
  'Viernes',
  'Sábado',
]

const MESES_COMPLETOS = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
]

function formatearFechaHoraPronosticoEspanol(isoStr: string): string {
  if (!isoStr) return ''
  const normalizado = isoStr.includes('T') ? isoStr : isoStr.replace(' ', 'T')
  const dt = new Date(normalizado)
  if (Number.isNaN(dt.getTime())) return isoStr
  const diaSemana = DIAS_SEMANA_COMPLETOS[dt.getDay()]
  const diaMes = dt.getDate()
  const mesNombre = MESES_COMPLETOS[dt.getMonth()]
  const anioNum = dt.getFullYear()
  const hh = String(dt.getHours()).padStart(2, '0')
  const mm = String(dt.getMinutes()).padStart(2, '0')
  return `${diaSemana} ${diaMes} de ${mesNombre} de ${anioNum} — ${hh}:${mm} hrs`
}

export function ForecastLineChart({
  actual,
  forecast = [],
  historico7d,
  pronostico7d,
  capacidad,
  salaNombre = 'General',
  recinto = 'biblioteca',
  onRetrain,
  isRetraining = false,
  retrainMsg,
  esAdminSistema = false,
}: Props) {

  const [soloAtencion, setSoloAtencion] = useState<boolean>(false)

  // Capas contextuales del calendario institucional y operacional
  const [mostrarFeriados, setMostrarFeriados] = useState(true)
  const [mostrarRecesos, setMostrarRecesos] = useState(true)
  const [mostrarExamenes, setMostrarExamenes] = useState(true)
  const [mostrarClases, setMostrarClases] = useState(true)
  const [mostrarSuspensiones, setMostrarSuspensiones] = useState(true)
  const [mostrarParos, setMostrarParos] = useState(true)
  const [mostrar24h, setMostrar24h] = useState(true)

  const espacioId = recinto === 'vehicular' ? 2 : 1

  const { data: horariosOperacion = [] } = useQuery<HorarioOperacion[]>({
    queryKey: ['horarios-capas-forecast', espacioId],
    queryFn: () => fetchHorarios({ espacio_id: espacioId }),
    staleTime: 30_000,
  })

  // Períodos de régimen extendido / continuo 24 horas activos
  const periodos24h = useMemo(() => {
    return horariosOperacion.filter((h: HorarioOperacion) => {
      if (!h.activo) return false
      const es24h = Boolean(h.es_continuo_24h || h.tipo_horario === 'extendido_24h')
      return es24h && Boolean(h.fecha_inicio && h.fecha_fin)
    })
  }, [horariosOperacion])

  const es24hFecha = (fechaIso: string): boolean => {
    if (!mostrar24h || periodos24h.length === 0) return false
    return periodos24h.some((h) => {
      const fIni = String(h.fecha_inicio).slice(0, 10)
      const fFin = String(h.fecha_fin).slice(0, 10)
      if (fechaIso < fIni || fechaIso > fFin) return false
      const sub = (h.subespacio || 'todos').toLowerCase()
      if (sub === 'todos') return true
      const sNom = (salaNombre || '').toLowerCase()
      if (recinto === 'biblioteca') {
        if (sNom.includes('sala 1') || sNom.includes('csf02')) {
          return sub === 'sala_1' || sub === 'sala1'
        }
        if (sNom.includes('sala 2') || sNom.includes('csf04') || sNom.includes('pecera')) {
          return sub === 'sala_2' || sub === 'sala2'
        }
      }
      return true
    })
  }

  // Separar y ordenar cronológicamente los puntos históricos (semana pasada) y futuros (próxima semana)
  const { histPoints, futPoints, anchorDateStr } = useMemo(() => {
    let hist: ForecastPoint[] = []
    let fut: ForecastPoint[] = []

    if (historico7d && historico7d.length > 0 && pronostico7d && pronostico7d.length > 0) {
      hist = [...historico7d]
      fut = [...pronostico7d]
    } else if (forecast.length > 0) {
      const tieneActual = forecast.filter(p => p.actual !== null && p.actual !== undefined)
      if (tieneActual.length > 0) {
        hist = tieneActual
        fut = forecast.filter(p => p.actual === null || p.actual === undefined)
      } else {
        const half = Math.floor(forecast.length / 2)
        hist = forecast.slice(0, half)
        fut = forecast.slice(half)
      }
    }

    // Ordenar explícitamente en orden cronológico ascendente (pasado -> presente -> futuro)
    hist.sort((a, b) => new Date(a.ds).getTime() - new Date(b.ds).getTime())
    fut.sort((a, b) => new Date(a.ds).getTime() - new Date(b.ds).getTime())

    const anchor = hist.length > 0 ? hist[hist.length - 1].ds : (fut[0]?.ds ?? '')
    return { histPoints: hist, futPoints: fut, anchorDateStr: anchor }
  }, [forecast, historico7d, pronostico7d])

  // Inferir año para la consulta del calendario institucional
  const anio = useMemo(() => {
    const p = histPoints[0] || futPoints[0]
    return p?.ds ? new Date(p.ds).getFullYear() : 2026
  }, [histPoints, futPoints])

  const { data: diasCalendario = [] } = useQuery({
    queryKey: ['calendario-resumen-anual', anio],
    queryFn: () => obtenerResumenAnualCalendario(anio),
    staleTime: 30_000,
  })

  // Mapa de fecha YYYY-MM-DD a evento de calendario
  const mapaFechas = useMemo(() => {
    const mapa = new Map<string, DiaCalendarioResumen>()
    diasCalendario.forEach((d: DiaCalendarioResumen) => {
      mapa.set(d.fecha, d)
    })
    return mapa
  }, [diasCalendario])

  const esSuspensionAplicableASala = (cal?: DiaCalendarioResumen) => {
    if (!cal?.suspension_actividades || cal.is_holiday || cal.is_break || cal.is_strike_federado) return false
    const subs = cal.subespacios_suspendidos || []
    const esps = cal.espacios_suspendidos || []
    const espActual = recinto === 'vehicular' ? 2 : 1
    if (esps.length > 0 && !esps.includes(espActual)) return false
    if (subs.length === 0 || subs.includes('todos')) return true
    const nombreNorm = (salaNombre || '').toLowerCase()
    if (recinto === 'biblioteca') {
      if (nombreNorm.includes('sala 1') || nombreNorm.includes('csf02')) {
        return subs.includes('sala_1') || subs.includes('sala1')
      }
      if (nombreNorm.includes('sala 2') || nombreNorm.includes('csf04')) {
        return subs.includes('sala_2') || subs.includes('sala2')
      }
    }
    return true
  }

  // Filtro de horario de atención
  const filteredHist = useMemo(() => {
    if (!soloAtencion) return histPoints
    return histPoints.filter(p => (p.es_abierto !== undefined ? p.es_abierto === 1 : (p.actual ?? p.yhat) > 0))
  }, [histPoints, soloAtencion])

  const filteredFut = useMemo(() => {
    if (!soloAtencion) return futPoints
    return futPoints.filter(p => (p.es_abierto !== undefined ? p.es_abierto === 1 : p.yhat > 0))
  }, [futPoints, soloAtencion])

  // Fechas únicas del horizonte para construir las bandas verticales de calendario
  const uniqueDates = useMemo(() => {
    const dates = new Set<string>()
    filteredHist.forEach(p => { if (p.ds) dates.add(p.ds.slice(0, 10)) })
    filteredFut.forEach(p => { if (p.ds) dates.add(p.ds.slice(0, 10)) })
    return Array.from(dates).sort()
  }, [filteredHist, filteredFut])

  // Franjas de fondo para cada categoría de calendario
  const contextShapes = useMemo(() => {
    const shapes: Partial<Shape>[] = []
    if (uniqueDates.length === 0) return shapes

    const agregarShapesCategoria = (
      activo: boolean,
      esPredicado: (cal?: DiaCalendarioResumen, fechaIso?: string) => boolean,
      fillcolor: string,
      linecolor: string,
    ) => {
      if (!activo) return
      let rStart: string | null = null
      let rEnd: string | null = null

      for (let i = 0; i < uniqueDates.length; i++) {
        const fechaIso = uniqueDates[i]
        const cal = mapaFechas.get(fechaIso)
        const coincide = esPredicado(cal, fechaIso)

        if (coincide) {
          if (rStart === null) rStart = fechaIso
          rEnd = fechaIso
        } else {
          if (rStart !== null && rEnd !== null) {
            shapes.push({
              type: 'rect',
              xref: 'x',
              yref: 'paper',
              x0: `${rStart} 00:00:00`,
              x1: `${rEnd} 23:59:59`,
              y0: 0,
              y1: 1,
              fillcolor,
              line: { width: 1.2, color: linecolor },
              layer: 'below',
            })
            rStart = null
            rEnd = null
          }
        }
      }

      if (rStart !== null && rEnd !== null) {
        shapes.push({
          type: 'rect',
          xref: 'x',
          yref: 'paper',
          x0: `${rStart} 00:00:00`,
          x1: `${rEnd} 23:59:59`,
          y0: 0,
          y1: 1,
          fillcolor,
          line: { width: 1.2, color: linecolor },
          layer: 'below',
        })
      }
    }

    // 1. Feriados Oficiales (Rojo suave con transparencia)
    agregarShapesCategoria(
      mostrarFeriados,
      (c) => Boolean(c?.is_holiday),
      'rgba(239, 68, 68, 0.22)',
      'rgba(220, 38, 38, 0.55)',
    )

    // 2. Recesos y Vacaciones (Ámbar dorado con transparencia)
    agregarShapesCategoria(
      mostrarRecesos,
      (c) => Boolean(c?.is_break),
      'rgba(245, 158, 11, 0.22)',
      'rgba(217, 119, 6, 0.55)',
    )

    // 3. Períodos de Exámenes / Solemnes (Púrpura con transparencia)
    agregarShapesCategoria(
      mostrarExamenes,
      (c) => Boolean(c?.is_exam_period),
      'rgba(147, 51, 234, 0.22)',
      'rgba(126, 34, 206, 0.55)',
    )

    // 4. Hitos de Clases (Azul cian institucional con transparencia)
    agregarShapesCategoria(
      mostrarClases,
      (c) => Boolean(c?.is_class_milestone),
      'rgba(2, 132, 199, 0.22)',
      'rgba(3, 105, 161, 0.55)',
    )

    // 5. Suspensiones / Salidas Anticipadas (Naranja con transparencia)
    agregarShapesCategoria(
      mostrarSuspensiones,
      (c) => esSuspensionAplicableASala(c),
      'rgba(249, 115, 22, 0.22)',
      'rgba(194, 65, 12, 0.55)',
    )

    // 6. Paros y Contingencias (Carmesí institucional)
    agregarShapesCategoria(
      mostrarParos,
      (c) => Boolean(c?.is_strike_federado || c?.is_strike_carrera),
      'rgba(225, 29, 72, 0.28)',
      'rgba(190, 18, 60, 0.65)',
    )

    // 7. Horario / Campaña 24 Horas (Índigo nocturno institucional)
    agregarShapesCategoria(
      mostrar24h,
      (_c, fIso) => Boolean(fIso && es24hFecha(fIso)),
      'rgba(99, 102, 241, 0.22)',
      'rgba(79, 70, 229, 0.65)',
    )

    return shapes
  }, [
    uniqueDates,
    mapaFechas,
    salaNombre,
    recinto,
    mostrarFeriados,
    mostrarRecesos,
    mostrarExamenes,
    mostrarClases,
    mostrarSuspensiones,
    mostrarParos,
    mostrar24h,
    periodos24h,
  ])

  // Métricas para los badges superiores
  const stats = useMemo(() => {
    const totalHist = filteredHist.reduce((acc, p) => acc + (p.actual ?? p.yhat ?? 0), 0)
    const maxHist = filteredHist.reduce((max, p) => Math.max(max, p.actual ?? p.yhat ?? 0), 0)
    const totalFut = filteredFut.reduce((acc, p) => acc + (p.yhat ?? 0), 0)
    const maxFut = filteredFut.reduce((max, p) => Math.max(max, p.yhat ?? 0), 0)
    return {
      totalHist: Math.round(totalHist),
      maxHist: Math.round(maxHist),
      totalFut: Math.round(totalFut),
      maxFut: Math.round(maxFut),
    }
  }, [filteredHist, filteredFut])

  // Construcción de ejes con tipo de fecha ISO (Plotly date axis)
  const { chartData, layout } = useMemo(() => {
    // 1. Serie Histórica (Últimos 7 días): timestamps ISO exactos
    const xHist = filteredHist.map(p => p.ds)
    const yHist = filteredHist.map(p => Math.max(0, Math.round(p.actual ?? p.yhat ?? 0)))
    const customHist = filteredHist.map(p => {
      const fechaIso = p.ds.slice(0, 10)
      const cal = mapaFechas.get(fechaIso)
      const ctx: string[] = []
      if (cal?.is_holiday) ctx.push('Feriado Oficial UCT')
      if (cal?.is_break) ctx.push('Receso / Vacaciones')
      if (cal?.is_exam_period) ctx.push('Exámenes / Solemnes')
      if (cal?.is_class_milestone) ctx.push('Hito de Clases')
      if (esSuspensionAplicableASala(cal)) ctx.push('Suspensión Actividades')
      if (cal?.is_strike_federado) ctx.push('Paro Federado FEUCT')
      if (cal?.is_strike_carrera) ctx.push('Paro por Carrera')
      if (mostrar24h && es24hFecha(fechaIso)) ctx.push('Campaña 24 Horas')
      const ctxStr = ctx.length > 0 ? `<br><b>Contexto:</b> ${ctx.join(', ')}` : ''
      const fechaLegible = formatearFechaHoraPronosticoEspanol(p.ds)
      return [fechaLegible, ctxStr]
    })

    // 2. Serie Futura (Próximos 7 días): conectada al último punto histórico
    const ultimoHist = filteredHist[filteredHist.length - 1]
    let futConConexion: ForecastPoint[] = [...filteredFut]

    if (ultimoHist && !soloAtencion) {
      // Crear punto de anclaje inicial para dar continuidad visual perfecta
      const puntoConector: ForecastPoint = {
        ds: ultimoHist.ds,
        yhat: ultimoHist.actual ?? ultimoHist.yhat,
        yhat_lower: ultimoHist.actual ?? ultimoHist.yhat,
        yhat_upper: ultimoHist.actual ?? ultimoHist.yhat,
        actual: ultimoHist.actual,
        es_abierto: ultimoHist.es_abierto,
      }
      futConConexion = [puntoConector, ...filteredFut]
    }

    const xFut = futConConexion.map(p => p.ds)
    const yFut = futConConexion.map(p => Math.max(0, Math.round(p.yhat)))
    const lowerFut = futConConexion.map(p => Math.max(0, Math.round(p.yhat_lower ?? p.yhat * 0.8)))
    const upperFut = futConConexion.map(p => Math.max(0, Math.round(p.yhat_upper ?? p.yhat * 1.2)))
    const customFut = futConConexion.map((_, i) => {
      const fechaIso = futConConexion[i].ds.slice(0, 10)
      const cal = mapaFechas.get(fechaIso)
      const ctx: string[] = []
      if (cal?.is_holiday) ctx.push('Feriado Oficial UCT')
      if (cal?.is_break) ctx.push('Receso / Vacaciones')
      if (cal?.is_exam_period) ctx.push('Exámenes / Solemnes')
      if (cal?.is_class_milestone) ctx.push('Hito de Clases')
      if (esSuspensionAplicableASala(cal)) ctx.push('Suspensión Actividades')
      if (cal?.is_strike_federado) ctx.push('Paro Federado FEUCT')
      if (cal?.is_strike_carrera) ctx.push('Paro por Carrera')
      if (mostrar24h && es24hFecha(fechaIso)) ctx.push('Campaña 24 Horas')
      const ctxStr = ctx.length > 0 ? `<br><b>Contexto:</b> ${ctx.join(', ')}` : ''
      const fechaLegible = formatearFechaHoraPronosticoEspanol(futConConexion[i].ds)
      return [yFut[i], upperFut[i], lowerFut[i], ctxStr, fechaLegible]
    })

    const unidad = recinto === 'vehicular' ? 'vehículos/h' : 'personas/h'
    const etiquetaReal = recinto === 'vehicular' ? 'Flujo Real' : 'Asistencia Real'

    // ORDEN CRONOLÓGICO ESTRICTO: Primero Histórico Real, luego Pronóstico
    const data: Data[] = [
      // 1. Traza Principal: Asistencia Real (Azul Marino Institucional UCT)
      {
        x: xHist,
        y: yHist,
        customdata: customHist,
        type: 'scatter',
        mode: 'lines',
        name: `${etiquetaReal} (Última Semana)`,
        line: { color: '#002855', width: 2.8 },
        hovertemplate: `<b>%{customdata[0]}</b><br>${etiquetaReal}: <b>%{y}</b> ${unidad}%{customdata[1]}<extra></extra>`,
      },
      // 2. Banda inferior de incertidumbre (transparente)
      {
        x: xFut,
        y: lowerFut,
        type: 'scatter',
        mode: 'lines',
        line: { color: 'transparent' },
        showlegend: false,
        hoverinfo: 'skip',
      },
      // 3. Banda superior con relleno tonexty (Ámbar suave)
      {
        x: xFut,
        y: upperFut,
        customdata: customFut,
        type: 'scatter',
        mode: 'lines',
        fill: 'tonexty',
        fillcolor: 'rgba(217, 119, 6, 0.18)',
        line: { color: 'rgba(217, 119, 6, 0.35)', width: 1, dash: 'dot' },
        name: 'Incertidumbre Pronóstico (80%)',
        hovertemplate:
          `<b>%{customdata[4]}</b><br>` +
          `<span style="color:#B45309">▲</span> <b>Límite Superior (80%):</b> %{customdata[1]} ${unidad}<br>` +
          `<b>Estimación Central:</b> %{customdata[0]} ${unidad}<br>` +
          `<span style="color:#B45309">▼</span> <b>Límite Inferior (80%):</b> %{customdata[2]} ${unidad}` +
          `%{customdata[3]}<extra></extra>`,
      },
      // 4. Traza de Pronóstico Prophet (Ámbar Dorado UCT)
      {
        x: xFut,
        y: yFut,
        customdata: customFut,
        type: 'scatter',
        mode: 'lines',
        name: 'Pronóstico Prophet (Próximos 7 Días)',
        line: { color: '#D97706', width: 2.8 },
        hovertemplate:
          `<b>%{customdata[4]}</b><br>` +
          `<b>Pronóstico Central:</b> <b>%{customdata[0]}</b> ${unidad}<br>` +
          `<span style="color:#B45309">▲</span> <b>Límite Superior (80%):</b> %{customdata[1]} ${unidad}<br>` +
          `<span style="color:#B45309">▼</span> <b>Límite Inferior (80%):</b> %{customdata[2]} ${unidad}` +
          `%{customdata[3]}<extra></extra>`,
      },
    ]

    // Formas de referencia: Capacidad Máxima y Separador Temporal
    const shapes: Partial<Shape>[] = []
    const annotations: Partial<Annotations>[] = []

    if (capacidad && capacidad > 0) {
      shapes.push({
        type: 'line',
        xref: 'paper',
        x0: 0,
        x1: 1,
        yref: 'y',
        y0: capacidad,
        y1: capacidad,
        line: {
          color: '#DC2626',
          width: 1.8,
          dash: 'dash',
        },
      })
      annotations.push({
        xref: 'paper',
        yref: 'y',
        x: 0.01,
        y: capacidad * 1.03,
        text: `Capacidad Máx: ${capacidad} asientos`,
        showarrow: false,
        font: { size: 9, color: '#DC2626' },
        bgcolor: 'rgba(254, 242, 242, 0.85)',
        bordercolor: '#F87171',
        borderwidth: 1,
        borderpad: 2,
      })
    }

    // Línea vertical que divide el histórico empírico del pronóstico futuro
    if (anchorDateStr) {
      shapes.push({
        type: 'line',
        xref: 'x',
        x0: anchorDateStr,
        x1: anchorDateStr,
        yref: 'paper',
        y0: 0,
        y1: 1,
        line: {
          color: '#475569',
          width: 1.8,
          dash: 'dot',
        },
      })
      annotations.push({
        xref: 'x',
        yref: 'paper',
        x: anchorDateStr,
        y: 0.98,
        text: 'Hoy (Inicio Pronóstico)',
        showarrow: false,
        font: { size: 9, color: '#1E293B' },
        bgcolor: 'rgba(241, 245, 249, 0.92)',
        bordercolor: '#94A3B8',
        borderwidth: 1,
        borderpad: 3,
      })
    }

    const maxVal = Math.max(
      ...yHist,
      ...upperFut,
      capacidad ? capacidad * 1.05 : 0,
      10
    )

    const chartLayout: Partial<Layout> = {
      height: 320,
      margin: { t: 30, r: 25, b: 50, l: 45 },
      shapes: [
        ...contextShapes,
        ...shapes,
      ],
      annotations,
      xaxis: {
        type: 'date',
        tickformat: '%d/%m %H:%M',
        showgrid: true,
        automargin: true,
        gridcolor: 'rgba(226, 232, 240, 0.6)',
        tickfont: { size: 9.5, color: '#64748B' },
        tickangle: -45,
        nticks: 16,
      },
      yaxis: {
        showgrid: true,
        automargin: true,
        gridcolor: 'rgba(226, 232, 240, 0.8)',
        tickfont: { size: 10, color: '#64748B' },
        range: [0, Math.ceil(maxVal * 1.12)],
        title: {
          text: recinto === 'vehicular' ? 'Vehículos / hora' : 'Personas / hora',
          font: { size: 10, color: '#64748B' },
        },
      },
      legend: {
        orientation: 'h',
        y: 1.15,
        x: 0.5,
        xanchor: 'center',
        font: { size: 10, color: '#334155' },
      },
    }

    return { chartData: data, layout: chartLayout }
  }, [filteredHist, filteredFut, soloAtencion, capacidad, anchorDateStr, recinto, contextShapes, mapaFechas, mostrar24h])

  return (
    <div className="space-y-3">
      {/* Barra de Capas Contextuales del Calendario Institucional */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 p-2 bg-slate-50/90 dark:bg-slate-800/80 rounded-lg border border-slate-200/80 dark:border-slate-700/80 text-xs">
        <div className="flex items-center gap-1.5 font-semibold text-slate-700 dark:text-slate-200 shrink-0">
          <Calendar size={13} className="text-uct-navy dark:text-sky-400" />
          <span>Capas:</span>
        </div>

        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1.5">
          <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 select-none">
            <input
              type="checkbox"
              checked={mostrarFeriados}
              onChange={(e) => setMostrarFeriados(e.target.checked)}
              className="rounded text-red-600 focus:ring-red-500 h-3.5 w-3.5 cursor-pointer"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-xs bg-red-500 border border-red-600/60 shrink-0" />
            <span>Feriados Oficiales</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 select-none">
            <input
              type="checkbox"
              checked={mostrarRecesos}
              onChange={(e) => setMostrarRecesos(e.target.checked)}
              className="rounded text-amber-500 focus:ring-amber-500 h-3.5 w-3.5 cursor-pointer"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-xs bg-amber-500 border border-amber-600/60 shrink-0" />
            <span>Recesos y Vacaciones</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 select-none">
            <input
              type="checkbox"
              checked={mostrarExamenes}
              onChange={(e) => setMostrarExamenes(e.target.checked)}
              className="rounded text-purple-600 focus:ring-purple-500 h-3.5 w-3.5 cursor-pointer"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-xs bg-purple-600 border border-purple-700/60 shrink-0" />
            <span>Exámenes / Solemnes</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 select-none">
            <input
              type="checkbox"
              checked={mostrarClases}
              onChange={(e) => setMostrarClases(e.target.checked)}
              className="rounded text-sky-600 focus:ring-sky-500 h-3.5 w-3.5 cursor-pointer"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-xs bg-sky-500 border border-sky-600/60 shrink-0" />
            <span>Hitos de Clases</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 select-none">
            <input
              type="checkbox"
              checked={mostrarSuspensiones}
              onChange={(e) => setMostrarSuspensiones(e.target.checked)}
              className="rounded text-orange-500 focus:ring-orange-500 h-3.5 w-3.5 cursor-pointer"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-xs bg-orange-500 border border-orange-600/60 shrink-0" />
            <span>Suspensiones</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 select-none">
            <input
              type="checkbox"
              checked={mostrarParos}
              onChange={(e) => setMostrarParos(e.target.checked)}
              className="rounded text-rose-600 focus:ring-rose-500 h-3.5 w-3.5 cursor-pointer"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-xs bg-rose-600 border border-rose-700/60 shrink-0" />
            <span>Paros y Contingencias</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 select-none">
            <input
              type="checkbox"
              checked={mostrar24h}
              onChange={(e) => setMostrar24h(e.target.checked)}
              className="rounded text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5 cursor-pointer"
            />
            <span className="inline-block w-2.5 h-2.5 rounded-xs bg-indigo-600 border border-indigo-700/60 shrink-0" />
            <span>Horario 24 Horas</span>
          </label>
        </div>
      </div>

      {/* Barra de Controles, Métricas y Reentrenamiento */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 pb-2 border-b border-gray-100 dark:border-gray-800 text-xs">
        {/* Métricas rápidas */}
        <div className="flex items-center gap-3 text-slate-600 dark:text-slate-300">
          <span className="flex items-center gap-1 font-medium text-uct-navy dark:text-sky-300">
            <Activity className="w-3.5 h-3.5" />
            Máximo Histórico: <strong className="font-semibold">{stats.maxHist} p/h</strong>
          </span>
          <span className="text-gray-300 dark:text-gray-700">|</span>
          <span className="flex items-center gap-1 font-medium text-amber-700 dark:text-amber-400">
            <Users className="w-3.5 h-3.5" />
            Máximo Proyectado: <strong className="font-semibold">{stats.maxFut} p/h</strong>
          </span>
          {capacidad && (
            <>
              <span className="text-gray-300 dark:text-gray-700">|</span>
              <span className="text-slate-500">
                Ocupación proyectada:{' '}
                <strong className="font-semibold">
                  {Math.round((stats.maxFut / capacidad) * 100)}%
                </strong>
              </span>
            </>
          )}
        </div>

        {/* Toggle de Horario */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800 p-0.5 rounded-lg border border-slate-200 dark:border-slate-700">
            <button
              type="button"
              onClick={() => setSoloAtencion(false)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${!soloAtencion
                ? 'bg-white dark:bg-slate-700 text-uct-navy dark:text-white shadow-xs font-semibold'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                }`}
            >
              Semana Completa (24/7)
            </button>
            <button
              type="button"
              onClick={() => setSoloAtencion(true)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${soloAtencion
                ? 'bg-white dark:bg-slate-700 text-uct-navy dark:text-white shadow-xs font-semibold'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                }`}
            >
              Solo Horario de Atención
            </button>
          </div>
        </div>
      </div>

      {/* Gráfico Interactivo Plotly */}
      <InteractiveChart
        data={chartData}
        layout={layout}
        filename={`pronostico_prophet_14dias_${salaNombre.toLowerCase().replace(/\s+/g, '_')}`}
        height={380}
      />
    </div>
  )
}

export default ForecastLineChart

