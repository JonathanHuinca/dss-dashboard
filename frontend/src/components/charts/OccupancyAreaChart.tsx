import React, {  useState, useMemo, useEffect , memo } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'
import type { Data, Layout  } from 'plotly.js-dist-min'
import { useQuery } from '@tanstack/react-query'
import { obtenerResumenAnualCalendario, DiaCalendarioResumen, fetchHorarios, HorarioOperacion } from '../../api/client'
import { Calendar } from 'lucide-react'

interface Props {
  data: {
    bucket: string
    ingresos?: number
    entradas?: number
    salidas: number
    vehiculos_presentes?: number
    personas_unicas?: number
    personas_sala1?: number
    personas_sala2?: number
    ingresos_sala1?: number
    ingresos_sala2?: number
  }[]
  capacidad: number
  title?: string
  unit?: string
  salaLabel?: string
  capSala1?: number
  capSala2?: number
  comparativaSalas?: { hora: string; entradas_sala1: number; entradas_sala2: number }[]
}

function OccupancyAreaChartComponent({
  data,
  capacidad,
  unit = 'ocupantes',
  salaLabel,
  capSala1 = 124,
  capSala2 = 226,
}: Props) {
  const esBiblioteca = unit !== 'vehículos'

  // Controles independientes para Sala 1 y Sala 2
  const [mostrarSala1, setMostrarSala1] = useState(true)
  const [mostrarSala2, setMostrarSala2] = useState(true)

  // Estados para conmutar las categorías contextuales del calendario institucional y operacional
  const [mostrarFeriados, setMostrarFeriados] = useState(true)
  const [mostrarRecesos, setMostrarRecesos] = useState(true)
  const [mostrarVacaciones, setMostrarVacaciones] = useState(true)
  const [mostrarExamenes, setMostrarExamenes] = useState(true)
  const [mostrarClases, setMostrarClases] = useState(true)
  const [mostrarSuspensiones, setMostrarSuspensiones] = useState(true)
  const [mostrarParos, setMostrarParos] = useState(true)
  const [mostrar24h, setMostrar24h] = useState(true)

  const espacioId = esBiblioteca ? 1 : 2

  const { data: horariosOperacion = [] } = useQuery<HorarioOperacion[]>({
    queryKey: ['horarios-capas-ocupacion', espacioId],
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
      if (esBiblioteca) {
        const lbl = (salaLabel || '').toLowerCase()
        if (lbl.includes('sala 1') || lbl.includes('csf02')) {
          return sub === 'sala_1' || sub === 'sala1'
        }
        if (lbl.includes('sala 2') || lbl.includes('csf04') || lbl.includes('pecera')) {
          return sub === 'sala_2' || sub === 'sala2'
        }
        if (esSuperponible) {
          if (mostrarSala1 && !mostrarSala2) return sub === 'sala_1' || sub === 'sala1'
          if (mostrarSala2 && !mostrarSala1) return sub === 'sala_2' || sub === 'sala2'
        }
      }
      return true
    })
  }

  const anioBase = useMemo(() => {
    if (!data || data.length === 0) return 2026
    const raw = data[0].bucket || (data[0] as any).fecha || ''
    return raw ? new Date(raw).getFullYear() : 2026
  }, [data])

  const { data: diasCalendario = [] } = useQuery({
    queryKey: ['calendario-resumen-anual', anioBase],
    queryFn: () => obtenerResumenAnualCalendario(anioBase),
    staleTime: 30_000,
  })

  // Mapa de fecha YYYY-MM-DD a evento
  const mapaFechas = useMemo(() => {
    const mapa = new Map<string, DiaCalendarioResumen>()
    diasCalendario.forEach((d: DiaCalendarioResumen) => {
      mapa.set(d.fecha, d)
    })
    return mapa
  }, [diasCalendario])

  const sortedData = useMemo(() => {
    const base = [...(data || [])].sort((a, b) => {
      const rawA = a.bucket || (a as any).fecha || ''
      const rawB = b.bucket || (b as any).fecha || ''
      return rawA && rawB ? new Date(rawA).getTime() - new Date(rawB).getTime() : 0
    })
    if (base.length <= 1 || diasCalendario.length === 0) return base

    const fMin = String(base[0].bucket || (base[0] as any).fecha || '').slice(0, 10)
    const fMax = String(base[base.length - 1].bucket || (base[base.length - 1] as any).fecha || '').slice(0, 10)
    if (!fMin || !fMax || fMin === fMax) return base

    const fechasConPuntos = new Set(
      base.map(item => String(item.bucket || (item as any).fecha || '').slice(0, 10)).filter(Boolean)
    )

    // Si algún día con evento de calendario (feriado, suspensión, paro, receso) dentro del rango tiene 0 registros,
    // insertar puntos con aforo 0 para que la banda contextual de Capas siempre pueda dibujarse en el eje X
    const puntosCierreSinteticos: typeof base = []
    diasCalendario.forEach((d: DiaCalendarioResumen) => {
      if (
        d.fecha >= fMin &&
        d.fecha <= fMax &&
        !fechasConPuntos.has(d.fecha) &&
        (d.is_holiday || d.is_break || d.suspension_actividades || d.is_strike_federado || d.is_strike_carrera)
      ) {
        puntosCierreSinteticos.push({
          bucket: `${d.fecha}T09:00:00`,
          ingresos: 0,
          entradas: 0,
          salidas: 0,
          vehiculos_presentes: 0,
          personas_unicas: 0,
          personas_sala1: 0,
          personas_sala2: 0,
          ingresos_sala1: 0,
          ingresos_sala2: 0,
        })
        puntosCierreSinteticos.push({
          bucket: `${d.fecha}T18:00:00`,
          ingresos: 0,
          entradas: 0,
          salidas: 0,
          vehiculos_presentes: 0,
          personas_unicas: 0,
          personas_sala1: 0,
          personas_sala2: 0,
          ingresos_sala1: 0,
          ingresos_sala2: 0,
        })
      }
    })

    if (puntosCierreSinteticos.length === 0) return base
    return [...base, ...puntosCierreSinteticos].sort((a, b) => {
      const rawA = a.bucket || (a as any).fecha || ''
      const rawB = b.bucket || (b as any).fecha || ''
      return rawA && rawB ? new Date(rawA).getTime() - new Date(rawB).getTime() : 0
    })
  }, [data, diasCalendario])

  const hasSalaData = useMemo(() => {
    return sortedData.some(d => (d.personas_sala1 ?? 0) > 0 || (d.personas_sala2 ?? 0) > 0 || (d.ingresos_sala1 ?? 0) > 0)
  }, [sortedData])
  const esSuperponible = Boolean(!salaLabel && esBiblioteca && hasSalaData)

  const esSuspensionAplicable = (cal?: DiaCalendarioResumen) => {
    if (!cal?.suspension_actividades || cal.is_holiday || cal.is_break || cal.is_strike_federado) return false
    const esps = cal.espacios_suspendidos || []
    const espActual = esBiblioteca ? 1 : 2
    if (esps.length > 0 && !esps.includes(espActual)) return false
    const subs = cal.subespacios_suspendidos || []
    if (subs.length === 0 || subs.includes('todos')) return true
    if (esBiblioteca) {
      const lbl = (salaLabel || '').toLowerCase()
      if (lbl.includes('sala 1') || lbl.includes('csf02')) {
        return subs.includes('sala_1') || subs.includes('sala1')
      }
      if (lbl.includes('sala 2') || lbl.includes('csf04')) {
        return subs.includes('sala_2') || subs.includes('sala2')
      }
      if (esSuperponible) {
        if (mostrarSala1 && !mostrarSala2) return subs.includes('sala_1') || subs.includes('sala1')
        if (mostrarSala2 && !mostrarSala1) return subs.includes('sala_2') || subs.includes('sala2')
      }
    }
    return true
  }

  let running = 0
  let ultimaFechaVehicular = ''
  const uniqueDates = useMemo(() => {
    return new Set(sortedData.map(d => {
      const raw = d.bucket || (d as any).fecha || ''
      return raw ? String(raw).slice(0, 10) : ''
    }).filter(Boolean))
  }, [sortedData])
  const isMultiDay = uniqueDates.size > 1

  // Mapa de fechas a rango de índices de puntos para vincular formas contextuales en eje categórico
  const fechaIndicesMap = useMemo(() => {
    const map = new Map<string, { start: number; end: number }>()
    sortedData.forEach((d, idx) => {
      const raw = d.bucket || (d as any).fecha || ''
      const fStr = raw ? String(raw).slice(0, 10) : ''
      if (!fStr) return
      if (!map.has(fStr)) {
        map.set(fStr, { start: idx, end: idx })
      } else {
        map.get(fStr)!.end = idx
      }
    })
    return map
  }, [sortedData])

  // Rango de fechas real de los datos
  const minDateIso = useMemo(() => {
    if (sortedData.length === 0) return undefined
    const raw = sortedData[0].bucket || (sortedData[0] as any).fecha || ''
    return raw ? String(raw).replace('T', ' ') : undefined
  }, [sortedData])

  const maxDateIso = useMemo(() => {
    if (sortedData.length === 0) return undefined
    const raw = sortedData[sortedData.length - 1].bucket || (sortedData[sortedData.length - 1] as any).fecha || ''
    return raw ? String(raw).replace('T', ' ') : undefined
  }, [sortedData])

  const minFechaStr = minDateIso ? minDateIso.slice(0, 10) : ''
  const maxFechaStr = maxDateIso ? maxDateIso.slice(0, 10) : ''

  // Disparar resize reactivo al montar o cuando cambian los datos o filtros
  useEffect(() => {
    const timer = setTimeout(() => {
      window.dispatchEvent(new Event('resize'))
    }, 120)
    return () => clearTimeout(timer)
  }, [sortedData.length, mostrarSala1, mostrarSala2, capacidad, salaLabel])

  const xVals: string[] = []
  const yVals: number[] = []
  const yValsSala1: number[] = []
  const yValsSala2: number[] = []
  const customDataListSala1: any[] = []
  const customDataListSala2: any[] = []
  const customDataListCombinado: any[] = []

  sortedData.forEach(d => {
    const inCount = d.ingresos ?? d.entradas ?? 0
    const rawBucket = d.bucket || (d as any).fecha || ''
    const fechaDiaActual = rawBucket ? String(rawBucket).slice(0, 10) : ''
    let aforo = 0
    if (unit === 'vehículos') {
      if (typeof d.vehiculos_presentes === 'number') {
        aforo = Math.min(capacidad > 0 ? capacidad : 9999, Math.max(0, d.vehiculos_presentes))
      } else if (typeof d.personas_unicas === 'number') {
        aforo = Math.min(capacidad > 0 ? capacidad : 9999, Math.max(0, d.personas_unicas))
      } else {
        if (fechaDiaActual && fechaDiaActual !== ultimaFechaVehicular) {
          running = 0
          ultimaFechaVehicular = fechaDiaActual
        }
        running = Math.min(capacidad > 0 ? capacidad : 9999, Math.max(0, running + inCount - d.salidas))
        aforo = running
      }
    } else {
      aforo = d.personas_unicas ?? inCount
    }
    const dObj = rawBucket ? new Date(rawBucket) : new Date()

    // Etiqueta secuencial continua en eje categórico para evitar huecos temporales vacíos
    const xCoord = rawBucket
      ? format(dObj, isMultiDay ? 'dd/MM HH:mm' : 'HH:mm')
      : ''
    xVals.push(xCoord)
    yVals.push(aforo)

    const valS1 = d.personas_sala1 ?? 0
    const valS2 = d.personas_sala2 ?? 0
    yValsSala1.push(valS1)
    yValsSala2.push(valS2)

    // Contexto del día para hover
    const fechaIso = rawBucket ? String(rawBucket).slice(0, 10) : ''
    const cal = mapaFechas.get(fechaIso)
    const contextParts: string[] = []
    if (cal) {
      if (cal.is_holiday) contextParts.push('<b>Feriado Oficial UCT</b>')
      const descMin = (cal.descripcion || '').toLowerCase()
      if (cal.is_break && descMin.includes('vacacion')) {
        contextParts.push('<b>Vacaciones Institucionales</b>')
      } else if (cal.is_break) {
        contextParts.push('<b>Semana de Receso</b>')
      }
      if (cal.is_exam_period) contextParts.push('<b>Período de Exámenes / Solemnes</b>')
      if (cal.is_class_milestone) contextParts.push('<b>Hito de Clases (Semestre)</b>')
      if (esSuspensionAplicable(cal)) {
        contextParts.push('<b>Suspensión / Salida Anticipada</b>')
      }
      if (cal.is_strike_federado) contextParts.push('<b>Paro Federado FEUCT</b>')
      if (cal.is_strike_carrera) contextParts.push('<b>Paro por Carrera</b>')
      if (cal.descripcion) contextParts.push(`Detalle: ${cal.descripcion}`)
    }
    if (mostrar24h && es24hFecha(fechaIso)) {
      contextParts.push('<b>Campaña 24 Horas Activa</b>')
    }
    const contextStr = contextParts.length > 0 ? `<br>${contextParts.join('<br>')}` : ''

    // Cabecera exacta: Miércoles 13 de mayo 2026, 10:00 hrs
    let fullDateHeader = ''
    if (rawBucket) {
      const f = format(dObj, "EEEE d 'de' MMMM yyyy, HH:mm' hrs'", { locale: es })
      fullDateHeader = f.charAt(0).toUpperCase() + f.slice(1)
    }

    const pctS1 = capSala1 > 0 ? Math.round((valS1 / capSala1) * 100) : 0
    const pctS2 = capSala2 > 0 ? Math.round((valS2 / capSala2) * 100) : 0
    const pctComb = capacidad > 0 ? Math.round((aforo / capacidad) * 100) : 0

    customDataListSala1.push([fullDateHeader, pctS1, contextStr])
    customDataListSala2.push([fullDateHeader, pctS2, contextStr])
    customDataListCombinado.push([fullDateHeader, pctComb, contextStr, inCount, d.salidas ?? 0])
  })

  // Franjas verticales continuas calculadas desde el calendario institucional vinculadas a las categorías
  const contextShapes = useMemo(() => {
    const shapes: any[] = []
    if (!minFechaStr || !maxFechaStr || diasCalendario.length === 0 || sortedData.length === 0) return shapes

    // Filtrar estrictamente días dentro del rango visible [minFechaStr, maxFechaStr]
    const diasFiltrados = diasCalendario.filter((d: DiaCalendarioResumen) =>
      d.fecha >= minFechaStr && d.fecha <= maxFechaStr
    )
    if (diasFiltrados.length === 0) return shapes

    const sonConsecutivos = (f1: string, f2: string) => {
      const t1 = new Date(f1 + 'T00:00:00').getTime()
      const t2 = new Date(f2 + 'T00:00:00').getTime()
      return Math.round((t2 - t1) / 86_400_000) === 1
    }

    const agregarShapesCategoria = (
      activo: boolean,
      esPredicado: (cal: DiaCalendarioResumen) => boolean,
      fillcolor: string,
      linecolor: string,
    ) => {
      if (!activo) return
      let rStartFecha: string | null = null
      let prevFecha: string | null = null

      const emitirShape = (fInicio: string, fFin: string) => {
        let idxStart: number | null = null
        let idxEnd: number | null = null
        for (const [fStr, range] of fechaIndicesMap.entries()) {
          if (fStr >= fInicio && fStr <= fFin) {
            if (idxStart === null || range.start < idxStart) idxStart = range.start
            if (idxEnd === null || range.end > idxEnd) idxEnd = range.end
          }
        }
        if (idxStart !== null && idxEnd !== null) {
          shapes.push({
            type: 'rect',
            xref: 'x',
            yref: 'paper',
            x0: idxStart - 0.45,
            x1: idxEnd + 0.45,
            y0: 0,
            y1: 1,
            fillcolor,
            line: { width: 1.5, color: linecolor },
            layer: 'below',
          })
        }
      }

      for (let i = 0; i < diasFiltrados.length; i++) {
        const dia = diasFiltrados[i]
        const coincide = esPredicado(dia)

        if (coincide) {
          if (rStartFecha === null) {
            rStartFecha = dia.fecha
          } else if (prevFecha && !sonConsecutivos(prevFecha, dia.fecha)) {
            emitirShape(rStartFecha, prevFecha)
            rStartFecha = dia.fecha
          }
          prevFecha = dia.fecha
        } else {
          if (rStartFecha !== null && prevFecha !== null) {
            emitirShape(rStartFecha, prevFecha)
            rStartFecha = null
            prevFecha = null
          }
        }
      }

      if (rStartFecha !== null && prevFecha !== null) {
        emitirShape(rStartFecha, prevFecha)
      }
    }

    // 1. Feriados Oficiales (Rojo visible de día completo)
    agregarShapesCategoria(
      mostrarFeriados,
      (c) => Boolean(c?.is_holiday),
      'rgba(239, 68, 68, 0.32)',
      'rgba(220, 38, 38, 0.75)',
    )

    // 2. Semana de Receso (Ámbar cálido, sin incluir vacaciones)
    agregarShapesCategoria(
      mostrarRecesos,
      (c) => Boolean(c?.is_break) && !(c?.descripcion || '').toLowerCase().includes('vacacion'),
      'rgba(245, 158, 11, 0.25)',
      'rgba(217, 119, 6, 0.65)',
    )

    // 3. Vacaciones Institucionales (Verde-grisáceo / Slate-teal de referencia)
    agregarShapesCategoria(
      mostrarVacaciones,
      (c) => Boolean(c?.is_break) && (c?.descripcion || '').toLowerCase().includes('vacacion'),
      'rgba(95, 158, 160, 0.30)',
      'rgba(70, 130, 133, 0.70)',
    )

    // 4. Períodos de Exámenes / Solemnes (Púrpura vibrante)
    agregarShapesCategoria(
      mostrarExamenes,
      (c) => Boolean(c?.is_exam_period),
      'rgba(192, 132, 252, 0.28)',
      'rgba(168, 85, 247, 0.65)',
    )

    // 5. Hitos de Clases (Azul cian / cielo)
    agregarShapesCategoria(
      mostrarClases,
      (c) => Boolean(c?.is_class_milestone),
      'rgba(56, 189, 248, 0.32)',
      'rgba(14, 165, 233, 0.70)',
    )

    // 6. Suspensiones / Salidas Anticipadas (Naranja salmón)
    agregarShapesCategoria(
      mostrarSuspensiones,
      (c) => esSuspensionAplicable(c),
      'rgba(249, 115, 22, 0.28)',
      'rgba(234, 88, 12, 0.70)',
    )

    // 7. Paros y Contingencias (Carmesí / Rosa de contingencia)
    agregarShapesCategoria(
      mostrarParos,
      (c) => Boolean(c?.is_strike_federado || c?.is_strike_carrera),
      'rgba(225, 29, 72, 0.30)',
      'rgba(190, 18, 60, 0.75)',
    )

    // 8. Horario / Campaña 24 Horas (Índigo nocturno institucional)
    if (mostrar24h && periodos24h.length > 0) {
      periodos24h.forEach((h) => {
        const sub = (h.subespacio || 'todos').toLowerCase()
        if (sub !== 'todos' && esBiblioteca) {
          const lbl = (salaLabel || '').toLowerCase()
          if (lbl.includes('sala 1') || lbl.includes('csf02')) {
            if (sub !== 'sala_1' && sub !== 'sala1') return
          } else if (lbl.includes('sala 2') || lbl.includes('csf04') || lbl.includes('pecera')) {
            if (sub !== 'sala_2' && sub !== 'sala2') return
          } else if (esSuperponible) {
            if (mostrarSala1 && !mostrarSala2 && sub !== 'sala_1' && sub !== 'sala1') return
            if (mostrarSala2 && !mostrarSala1 && sub !== 'sala_2' && sub !== 'sala2') return
          }
        }

        const fIni = String(h.fecha_inicio).slice(0, 10)
        const fFin = String(h.fecha_fin).slice(0, 10)
        const fechasVisiblesEnPeriodo = Array.from(uniqueDates)
          .filter((f) => f >= fIni && f <= fFin)
          .sort()

        if (fechasVisiblesEnPeriodo.length > 0) {
          let tramoInicio = fechasVisiblesEnPeriodo[0]
          let tramoPrev = fechasVisiblesEnPeriodo[0]

          const sonConsecutivos = (f1: string, f2: string) => {
            const t1 = new Date(f1 + 'T00:00:00').getTime()
            const t2 = new Date(f2 + 'T00:00:00').getTime()
            return Math.round(Math.abs(t2 - t1) / (1000 * 60 * 60 * 24)) <= 1
          }

          const emitirTramo24h = (inicio: string, fin: string) => {
            const idxStart = fechaIndicesMap.get(inicio)?.start
            const idxEnd = fechaIndicesMap.get(fin)?.end
            if (idxStart !== undefined && idxEnd !== undefined) {
              shapes.push({
                type: 'rect',
                xref: 'x',
                yref: 'paper',
                x0: idxStart - 0.5,
                x1: idxEnd + 0.5,
                y0: 0,
                y1: 1,
                fillcolor: 'rgba(99, 102, 241, 0.22)',
                line: { width: 1.5, color: 'rgba(79, 70, 229, 0.65)' },
                layer: 'below',
              })
            }
          }

          for (let i = 1; i < fechasVisiblesEnPeriodo.length; i++) {
            const fActual = fechasVisiblesEnPeriodo[i]
            if (sonConsecutivos(tramoPrev, fActual)) {
              tramoPrev = fActual
            } else {
              emitirTramo24h(tramoInicio, tramoPrev)
              tramoInicio = fActual
              tramoPrev = fActual
            }
          }
          emitirTramo24h(tramoInicio, tramoPrev)
        }
      })
    }

    return shapes
  }, [
    minFechaStr,
    maxFechaStr,
    diasCalendario,
    sortedData,
    fechaIndicesMap,
    mostrarSala1,
    mostrarSala2,
    salaLabel,
    mostrarFeriados,
    mostrarRecesos,
    mostrarVacaciones,
    mostrarExamenes,
    mostrarClases,
    mostrarSuspensiones,
    mostrarParos,
    mostrar24h,
    periodos24h,
    uniqueDates,
    esBiblioteca,
    esSuperponible,
  ])

  const alerta70 = Math.round(capacidad * 0.70)
  const alerta85 = Math.round(capacidad * 0.85)

  // Construir datos del gráfico según los checkboxes de Sala 1 y Sala 2
  const chartData: Data[] = useMemo(() => {
    if (esSuperponible && (mostrarSala1 || mostrarSala2)) {
      const traces: Data[] = []

      if (mostrarSala1) {
        traces.push({
          x: xVals,
          y: yValsSala1,
          customdata: customDataListSala1,
          type: 'scatter',
          mode: 'lines',
          name: `Sala 1: CSF02 (${capSala1} as.)`,
          fill: 'tozeroy',
          fillcolor: 'rgba(0, 43, 73, 0.12)',
          line: { color: '#002B49', width: 2.5, shape: 'spline' },
          hovertemplate:
            `<b>%{customdata[0]}</b><br>` +
            `<b>Aforo en este punto (Sala 1 CSF02):</b> %{y} personas<br>` +
            `Ocupación de sala: <b>%{customdata[1]}%</b> (Capacidad: ${capSala1} asientos)` +
            `%{customdata[2]}<extra></extra>`,
        })
      }

      if (mostrarSala2) {
        traces.push({
          x: xVals,
          y: yValsSala2,
          customdata: customDataListSala2,
          type: 'scatter',
          mode: 'lines',
          name: `Sala 2: CSF04 Pecera (${capSala2} as.)`,
          fill: 'tozeroy',
          fillcolor: 'rgba(217, 119, 6, 0.14)',
          line: { color: '#D97706', width: 2.5, shape: 'spline' },
          hovertemplate:
            `<b>%{customdata[0]}</b><br>` +
            `<b>Aforo en este punto (Sala 2 CSF04 Pecera):</b> %{y} personas<br>` +
            `Ocupación de sala: <b>%{customdata[1]}%</b> (Capacidad: ${capSala2} asientos)` +
            `%{customdata[2]}<extra></extra>`,
        })
      }

      return traces
    }

    const esVeh = unit === 'vehículos'
    return [
      {
        x: xVals,
        y: yVals,
        customdata: customDataListCombinado,
        type: 'scatter',
        mode: 'lines',
        name: salaLabel || (esVeh ? 'Ocupación Vehicular' : 'Aforo Total Combinado'),
        fill: 'tozeroy',
        fillcolor: 'rgba(0, 56, 101, 0.15)',
        line: { color: '#003865', width: 2.5, shape: 'spline' },
        hovertemplate: esVeh
          ? `<b>%{customdata[0]}</b><br>` +
            `<b>Vehículos presentes en esta hora (${salaLabel || 'Estacionamiento CSF'}):</b> %{y} vehículos<br>` +
            `<b>Flujo de la hora:</b> %{customdata[3]} ingresos | %{customdata[4]} salidas<br>` +
            `Ocupación de sector: <b>%{customdata[1]}%</b> (Capacidad: ${capacidad} plazas)` +
            `%{customdata[2]}<extra></extra>`
          : `<b>%{customdata[0]}</b><br>` +
            `<b>Aforo en este punto (${salaLabel || 'Total Combinado'}):</b> %{y} personas<br>` +
            `Ocupación de biblioteca: <b>%{customdata[1]}%</b> (Capacidad: ${capacidad} asientos)` +
            `%{customdata[2]}<extra></extra>`,
      },
    ]
  }, [
    esSuperponible,
    mostrarSala1,
    mostrarSala2,
    salaLabel,
    xVals,
    yValsSala1,
    yValsSala2,
    yVals,
    customDataListSala1,
    customDataListSala2,
    customDataListCombinado,
    capSala1,
    capSala2,
    capacidad,
    unit,
  ])

  // Formar líneas de umbrales según salas activas
  const thresholdShapes = useMemo(() => {
    if (esSuperponible && (mostrarSala1 || mostrarSala2)) {
      const lines: any[] = []

      if (mostrarSala2) {
        lines.push({
          type: 'line' as const,
          x0: 0,
          x1: 1,
          xref: 'paper' as const,
          y0: capSala2,
          y1: capSala2,
          line: { color: '#D97706', width: 1.5, dash: 'dash' },
        })
      }

      if (mostrarSala1) {
        lines.push({
          type: 'line' as const,
          x0: 0,
          x1: 1,
          xref: 'paper' as const,
          y0: capSala1,
          y1: capSala1,
          line: { color: '#002B49', width: 1.5, dash: 'dash' },
        })
      }

      return lines
    }

    return [
      {
        type: 'line' as const,
        x0: 0,
        x1: 1,
        xref: 'paper' as const,
        y0: capacidad,
        y1: capacidad,
        line: { color: '#DC2626', width: 2, dash: 'dash' },
      },
      {
        type: 'line' as const,
        x0: 0,
        x1: 1,
        xref: 'paper' as const,
        y0: alerta85,
        y1: alerta85,
        line: { color: '#D97706', width: 1.5, dash: 'dot' },
      },
      {
        type: 'line' as const,
        x0: 0,
        x1: 1,
        xref: 'paper' as const,
        y0: alerta70,
        y1: alerta70,
        line: { color: '#16A34A', width: 1.2, dash: 'dot' },
      },
    ]
  }, [esSuperponible, mostrarSala1, mostrarSala2, capSala1, capSala2, capacidad, alerta70, alerta85])

  const annotations = useMemo(() => {
    if (esSuperponible && (mostrarSala1 || mostrarSala2)) {
      const ann: any[] = []

      if (mostrarSala2) {
        ann.push({
          xref: 'paper' as const,
          x: 1.01,
          y: capSala2,
          text: `Máx S2 (${capSala2})`,
          showarrow: false,
          font: { size: 9, color: '#D97706' },
          xanchor: 'left' as const,
        })
      }

      if (mostrarSala1) {
        ann.push({
          xref: 'paper' as const,
          x: 1.01,
          y: capSala1,
          text: `Máx S1 (${capSala1})`,
          showarrow: false,
          font: { size: 9, color: '#002B49' },
          xanchor: 'left' as const,
        })
      }

      return ann
    }

    return [
      {
        xref: 'paper' as const,
        x: 1.01,
        y: capacidad,
        text: `Máx ${capacidad}`,
        showarrow: false,
        font: { size: 9, color: '#DC2626' },
        xanchor: 'left' as const,
      },
      {
        xref: 'paper' as const,
        x: 1.01,
        y: alerta85,
        text: '85%',
        showarrow: false,
        font: { size: 9, color: '#D97706' },
        xanchor: 'left' as const,
      },
      {
        xref: 'paper' as const,
        x: 1.01,
        y: alerta70,
        text: '70%',
        showarrow: false,
        font: { size: 9, color: '#16A34A' },
        xanchor: 'left' as const,
      },
    ]
  }, [esSuperponible, mostrarSala1, mostrarSala2, capSala1, capSala2, capacidad, alerta70, alerta85])

  const maxY = useMemo(() => {
    if (esSuperponible && (mostrarSala1 || mostrarSala2)) {
      let maxVal = 0
      let maxCap = 0
      if (mostrarSala1) {
        maxVal = Math.max(maxVal, ...(yValsSala1.length > 0 ? yValsSala1 : [0]))
        maxCap = Math.max(maxCap, capSala1)
      }
      if (mostrarSala2) {
        maxVal = Math.max(maxVal, ...(yValsSala2.length > 0 ? yValsSala2 : [0]))
        maxCap = Math.max(maxCap, capSala2)
      }
      return Math.max(maxCap + 15, maxVal + 10, 60)
    }
    const maxVal = yVals.length > 0 ? Math.max(...yVals) : 0
    return Math.max(capacidad + 15, maxVal + 10, 60)
  }, [esSuperponible, mostrarSala1, mostrarSala2, capSala1, capSala2, capacidad, yValsSala1, yValsSala2, yVals])

  const layout: Partial<Layout> = {
    autosize: true,
    hovermode: 'closest',
    uirevision: `${sortedData.length}_${capacidad}_${mostrarSala1}_${mostrarSala2}_${salaLabel || 'global'}_${contextShapes.length}`,
    margin: { t: 30, r: 75, b: isMultiDay ? 70 : 45, l: 45 },
    xaxis: {
      type: 'category',
      showgrid: true,
      automargin: true,
      gridcolor: '#f1f5f9',
      tickfont: { size: 9.5, color: '#64748B' },
      tickangle: -45,
      nticks: isMultiDay ? 18 : 24,
      showspikes: false,
    },
    yaxis: {
      rangemode: 'tozero' as const,
      range: [0, Math.max(maxY, 240)],
      zeroline: true,
      zerolinecolor: '#cbd5e1',
      zerolinewidth: 1.5,
      showgrid: true,
      automargin: true,
      gridcolor: '#e2e8f0',
      tickfont: { size: 10, color: '#64748B' },
      showspikes: false,
    },
    shapes: [...contextShapes, ...thresholdShapes],
    annotations,
    showlegend: Boolean(esSuperponible && (mostrarSala1 || mostrarSala2)),
    legend: {
      orientation: 'h' as const,
      y: 1.12,
      x: 0.5,
      xanchor: 'center' as const,
      font: { size: 10.5, color: '#334155' },
    },
  }

  return (
    <div className="space-y-2 w-full h-full flex flex-col">
      {/* Controles de Capas Contextuales y Selector de Modo de Visualización */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-1.5 px-2 bg-slate-50/90 rounded-xl border border-slate-200/80 text-[11px] shrink-0">
        <div className="flex items-center gap-2">
          {/* Checkboxes independientes para Sala 1 y Sala 2 */}
          {esSuperponible ? (
            <div className="flex items-center gap-2 bg-white px-2.5 py-1 rounded-lg border border-slate-200 shadow-2xs">
              <span className="text-[10.5px] font-bold text-slate-700 mr-0.5">Salas:</span>
              <label className="flex items-center gap-1.5 cursor-pointer font-semibold text-[#002B49] select-none hover:opacity-85">
                <input
                  type="checkbox"
                  checked={mostrarSala1}
                  onChange={(e) => setMostrarSala1(e.target.checked)}
                  className="rounded text-[#002B49] focus:ring-[#002B49] h-3.5 w-3.5 cursor-pointer"
                />
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#002B49]" />
                <span>Sala 1 (CSF02)</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer font-semibold text-[#D97706] select-none hover:opacity-85 ml-1.5">
                <input
                  type="checkbox"
                  checked={mostrarSala2}
                  onChange={(e) => setMostrarSala2(e.target.checked)}
                  className="rounded text-[#D97706] focus:ring-[#D97706] h-3.5 w-3.5 cursor-pointer"
                />
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#D97706]" />
                <span>Sala 2 (CSF04 Pecera)</span>
              </label>
            </div>
          ) : salaLabel ? (
            <span className="text-[10.5px] font-bold px-2 py-0.5 rounded-md bg-blue-100 text-uct-blue-primary">
              Filtrado por: {salaLabel} ({capacidad} asientos)
            </span>
          ) : null}

          {isMultiDay && (
            <span className="font-semibold text-slate-700 flex items-center gap-1.5 ml-1">
              <Calendar size={13} className="text-slate-500" />
              <span>Capas:</span>
            </span>
          )}
        </div>

        {isMultiDay && (
          <div className="flex flex-wrap items-center gap-2.5">
            <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
              <input
                type="checkbox"
                checked={mostrarFeriados}
                onChange={(e) => setMostrarFeriados(e.target.checked)}
                className="rounded text-red-600 focus:ring-red-500 h-3.5 w-3.5 cursor-pointer"
              />
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-red-500 border border-red-600/60 shrink-0" />
              <span>Feriados Oficiales</span>
            </label>

            <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
              <input
                type="checkbox"
                checked={mostrarRecesos}
                onChange={(e) => setMostrarRecesos(e.target.checked)}
                className="rounded text-amber-500 focus:ring-amber-500 h-3.5 w-3.5 cursor-pointer"
              />
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-amber-500 border border-amber-600/60 shrink-0" />
              <span>Semana de Receso</span>
            </label>

            <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
              <input
                type="checkbox"
                checked={mostrarVacaciones}
                onChange={(e) => setMostrarVacaciones(e.target.checked)}
                className="rounded text-[#468285] focus:ring-[#468285] h-3.5 w-3.5 cursor-pointer"
              />
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#5F9EA0] border border-[#468285] shrink-0" />
              <span>Vacaciones</span>
            </label>

            <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
              <input
                type="checkbox"
                checked={mostrarExamenes}
                onChange={(e) => setMostrarExamenes(e.target.checked)}
                className="rounded text-purple-600 focus:ring-purple-500 h-3.5 w-3.5 cursor-pointer"
              />
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-purple-600 border border-purple-700/60 shrink-0" />
              <span>Exámenes / Solemnes</span>
            </label>

            <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
              <input
                type="checkbox"
                checked={mostrarClases}
                onChange={(e) => setMostrarClases(e.target.checked)}
                className="rounded text-sky-600 focus:ring-sky-500 h-3.5 w-3.5 cursor-pointer"
              />
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-sky-500 border border-sky-600/60 shrink-0" />
              <span>Hitos de Clases</span>
            </label>

            <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
              <input
                type="checkbox"
                checked={mostrarSuspensiones}
                onChange={(e) => setMostrarSuspensiones(e.target.checked)}
                className="rounded text-orange-500 focus:ring-orange-500 h-3.5 w-3.5 cursor-pointer"
              />
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-orange-500 border border-orange-600/60 shrink-0" />
              <span>Suspensiones</span>
            </label>

            <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
              <input
                type="checkbox"
                checked={mostrarParos}
                onChange={(e) => setMostrarParos(e.target.checked)}
                className="rounded text-rose-600 focus:ring-rose-500 h-3.5 w-3.5 cursor-pointer"
              />
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-rose-600 border border-rose-700/60 shrink-0" />
              <span>Paros y Contingencias</span>
            </label>

            <label className="flex items-center gap-1.5 cursor-pointer font-medium text-slate-700 hover:text-slate-900 select-none">
              <input
                type="checkbox"
                checked={mostrar24h}
                onChange={(e) => setMostrar24h(e.target.checked)}
                className="rounded text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5 cursor-pointer"
              />
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-indigo-600 border border-indigo-700/60 shrink-0" />
              <span>Horario 24 Horas</span>
            </label>
          </div>
        )}
      </div>

      <div className="flex-1 w-full min-h-[380px]">
        <InteractiveChart
          data={chartData}
          layout={layout}
          filename="curva_aforo_concurrente"
          height={380}
          className="w-full h-full"
        />
      </div>

      {/* Leyenda Dinámica de Aforo y Capacidades */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-slate-100 text-xs text-slate-600">
        {esSuperponible && (mostrarSala1 || mostrarSala2) ? (
          <div className="flex flex-wrap items-center gap-4">
            {mostrarSala1 && (
              <span className="flex items-center gap-1.5 font-medium text-slate-800">
                <span className="w-3.5 h-1 rounded-xs bg-[#002B49] inline-block" />
                <span>Sala 1: CSF02 (2° Piso)</span>
                <span className="text-slate-500 font-normal">| Capacidad: <b>{capSala1} as.</b></span>
              </span>
            )}
            {mostrarSala2 && (
              <span className="flex items-center gap-1.5 font-medium text-slate-800">
                <span className="w-3.5 h-1 rounded-xs bg-[#D97706] inline-block" />
                <span>Sala 2: CSF04 Pecera (1° Piso)</span>
                <span className="text-slate-500 font-normal">| Capacidad: <b>{capSala2} as.</b></span>
              </span>
            )}
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-4">
            <span className="flex items-center gap-1.5 font-medium text-slate-800">
              <span className="w-3.5 h-1 rounded-xs bg-uct-blue-primary inline-block" />
              <span>{salaLabel ? `Ocupación ${salaLabel}` : 'Aforo Concurrente Total'}</span>
            </span>
            <span className="flex items-center gap-1 text-slate-600">
              <span className="w-3 h-0.5 bg-uct-success inline-block" /> 70% ({alerta70})
            </span>
            <span className="flex items-center gap-1 text-slate-600">
              <span className="w-3 h-0.5 bg-uct-warning inline-block" /> 85% ({alerta85})
            </span>
            <span className="flex items-center gap-1 text-slate-600">
              <span className="w-3 h-0.5 bg-uct-danger inline-block" /> Límite ({capacidad})
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

export const OccupancyAreaChart = memo(OccupancyAreaChartComponent)
export default OccupancyAreaChart
