import React, { useState, useMemo, useEffect, useRef, memo } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'
import type { Data, Layout  } from 'plotly.js-dist-min'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  obtenerResumenAnualCalendario,
  DiaCalendarioResumen,
  fetchHorarios,
  HorarioOperacion,
  IncidenciaOperativaResumen,
  eliminarContingencia,
} from '../../api/client'
import { Calendar, Info, ClipboardEdit, Trash2, ChevronDown, X } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { ModalRegistrarMotivoOperativo } from '../ui/ModalRegistrarMotivoOperativo'
import { obtenerFechaHoyChileIso } from '../../utils/fechaChile'

const TIPOS_INCIDENCIA_OPERATIVA = new Set([
  'falla_sensor',
  'apertura_manual',
  'mantencion_cierre',
  'suspension_sala',
  'sin_demanda',
  'otro',
])

const ETIQUETAS_INCIDENCIA: Record<string, { etiqueta: string; tono: string; texto: string }> = {
  falla_sensor: {
    etiqueta: 'Falla de sensor / torniquete',
    tono: 'bg-indigo-50/90 border-indigo-200 text-indigo-900',
    texto: 'text-indigo-600',
  },
  apertura_manual: {
    etiqueta: 'Apertura manual sin marcaje',
    tono: 'bg-sky-50/90 border-sky-200 text-sky-900',
    texto: 'text-sky-600',
  },
  mantencion_cierre: {
    etiqueta: 'Cierre / mantención',
    tono: 'bg-orange-50/90 border-orange-200 text-orange-900',
    texto: 'text-orange-600',
  },
  suspension_sala: {
    etiqueta: 'Suspensión de sala / sector',
    tono: 'bg-orange-50/90 border-orange-200 text-orange-900',
    texto: 'text-orange-600',
  },
  sin_demanda: {
    etiqueta: 'Sin afluencia confirmada',
    tono: 'bg-emerald-50/90 border-emerald-200 text-emerald-900',
    texto: 'text-emerald-600',
  },
  otro: {
    etiqueta: 'Observación operativa',
    tono: 'bg-slate-100/90 border-slate-300 text-slate-800',
    texto: 'text-slate-600',
  },
}

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
    vehiculos_csf11?: number
    vehiculos_csf21?: number
    vehiculos_chs01?: number
    entradas_csf11?: number
    salidas_csf11?: number
    entradas_csf21?: number
    salidas_csf21?: number
    entradas_chs01?: number
    salidas_chs01?: number
    capacidad_csf11?: number
    capacidad_csf21?: number
    capacidad_chs01?: number
    sin_registros?: boolean
    sin_registros_sala1?: boolean
    sin_registros_sala2?: boolean
  }[]
  capacidad: number
  title?: string
  unit?: string
  salaLabel?: string
  capSala1?: number
  capSala2?: number
  capCSF11?: number
  capCSF21?: number
  capCHS01?: number
  comparativaSalas?: { hora: string; entradas_sala1: number; entradas_sala2: number }[]
  ultimaLectura?: string | null
  ultimaLecturaSala1?: string | null
  ultimaLecturaSala2?: string | null
}

function OccupancyAreaChartComponent({
  data,
  capacidad,
  unit = 'ocupantes',
  salaLabel,
  capSala1 = 150,
  capSala2 = 126,
  capCSF11,
  capCSF21,
  capCHS01,
  ultimaLectura,
  ultimaLecturaSala1,
  ultimaLecturaSala2,
}: Props) {
  const esBiblioteca = unit !== 'vehículos'

  // Controles independientes para Sala 1, Sala 2 y Total Combinado
  const [mostrarSala1, setMostrarSala1] = useState(true)
  const [mostrarSala2, setMostrarSala2] = useState(true)
  const [mostrarTotalCombinado, setMostrarTotalCombinado] = useState(false)

  // Controles independientes para Sectores de Estacionamiento (CSF11, CSF21, CHS01)
  const [mostrarCSF11, setMostrarCSF11] = useState(true)
  const [mostrarCSF21, setMostrarCSF21] = useState(true)
  const [mostrarCHS01, setMostrarCHS01] = useState(true)

  const capSector1 = capCSF11 ?? data?.[0]?.capacidad_csf11 ?? 40
  const capSector2 = capCSF21 ?? data?.[0]?.capacidad_csf21 ?? 50
  const capSector3 = capCHS01 ?? data?.[0]?.capacidad_chs01 ?? 35

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
  const { isAuthenticated, canAccessAdmin } = useAuth()
  const puedeEditarIncidente = Boolean(isAuthenticated && canAccessAdmin)
  const queryClient = useQueryClient()
  const [modalMotivoAbierto, setModalMotivoAbierto] = useState(false)
  const [fechaModalMotivo, setFechaModalMotivo] = useState<string>('')
  const [subespacioModalMotivo, setSubespacioModalMotivo] = useState<string>('')
  const [popoverDiasAbierto, setPopoverDiasAbierto] = useState(false)
  const [filtroEstadoDias, setFiltroEstadoDias] = useState<'todos' | 'sin_motivo' | 'con_motivo' | 'calendario'>('todos')
  const [filtroSalaDias, setFiltroSalaDias] = useState<'todas' | 'sala_1' | 'sala_2'>('todas')
  const popoverDiasRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!popoverDiasAbierto) return
    const handleOutside = (ev: MouseEvent) => {
      if (popoverDiasRef.current && !popoverDiasRef.current.contains(ev.target as Node)) {
        setPopoverDiasAbierto(false)
      }
    }
    const handleKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setPopoverDiasAbierto(false)
    }
    document.addEventListener('mousedown', handleOutside)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleOutside)
      document.removeEventListener('keydown', handleKey)
    }
  }, [popoverDiasAbierto])

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

  const subespacioActivo = useMemo(() => {
    const lbl = (salaLabel || '').toLowerCase()
    if (esBiblioteca) {
      if (lbl.includes('sala 1') || lbl.includes('csf02')) return 'sala_1'
      if (lbl.includes('sala 2') || lbl.includes('csf04') || lbl.includes('pecera')) return 'sala_2'
      return 'todos'
    }
    if (lbl.includes('csf11')) return 'CSF11'
    if (lbl.includes('csf21')) return 'CSF21'
    if (lbl.includes('chs01')) return 'CHS01'
    return 'todos'
  }, [esBiblioteca, salaLabel])

  const obtenerIncidenciasDia = (fechaIso: string, subespacioObjetivo?: string): IncidenciaOperativaResumen[] => {
    const incs = mapaFechas.get(fechaIso)?.incidencias_operativas || []
    const objetivo = (subespacioObjetivo ?? subespacioActivo).toLowerCase()
    return incs.filter((inc) => {
      if (!TIPOS_INCIDENCIA_OPERATIVA.has((inc.tipo || '').toLowerCase())) return false
      if (inc.espacio_id != null && inc.espacio_id !== espacioId) return false
      const sub = (inc.subespacio || 'todos').trim().toLowerCase()
      if (sub === 'todos' || objetivo === 'todos') return true
      return sub === objetivo
    })
  }

  const obtenerContextoAcademicoDia = (
    fechaIso: string,
  ): { etiqueta: string; tono: string; detalle?: string } | null => {
    const cal = mapaFechas.get(fechaIso)
    if (!cal) return null
    if (cal.is_strike_federado) {
      return {
        etiqueta: 'Paro Federado FEUCT',
        tono: 'bg-rose-50 border-rose-200 text-rose-800',
        detalle: cal.descripcion || undefined,
      }
    }
    if (cal.is_strike_carrera) {
      return {
        etiqueta: 'Paro por Carrera',
        tono: 'bg-rose-50 border-rose-200 text-rose-800',
        detalle: cal.descripcion || undefined,
      }
    }
    if (cal.is_break) {
      const esVac = (cal.descripcion || '').toLowerCase().includes('vacacion')
      return {
        etiqueta: esVac ? 'Vacaciones institucionales' : 'Semana de receso',
        tono: esVac
          ? 'bg-teal-50 border-teal-200 text-teal-800'
          : 'bg-sky-50 border-sky-200 text-sky-800',
        detalle: cal.descripcion || undefined,
      }
    }
    if (cal.is_holiday) {
      return {
        etiqueta: 'Feriado oficial',
        tono: 'bg-red-50 border-red-200 text-red-800',
        detalle: cal.descripcion || undefined,
      }
    }
    if (cal.suspension_actividades) {
      return {
        etiqueta: 'Suspensión institucional',
        tono: 'bg-orange-50 border-orange-200 text-orange-800',
        detalle: cal.descripcion || undefined,
      }
    }
    return null
  }

  const eliminarIncidenciaMutation = useMutation({
    mutationFn: (id: number) => eliminarContingencia(id),
    onSuccess: () => {
      const claves = [
        'calendario-resumen-anual',
        'contingencias',
        'calendar-events',
        'calendar-status',
        'attendance-presence-curve',
        'attendance-kpis',
        'occupancy-realtime',
        'hourly-flow',
        'vehicle-presence-curve',
        'vehicle-hourly-flow',
        'vehicle-kpis',
        'forecast-attendance',
        'forecast-parking',
        'forecast-14days',
      ]
      claves.forEach((k) => queryClient.invalidateQueries({ queryKey: [k] }))
    },
  })

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

  const hasSectorData = useMemo(() => {
    return sortedData.some(d => (d.vehiculos_csf11 ?? 0) > 0 || (d.vehiculos_csf21 ?? 0) > 0 || (d.vehiculos_chs01 ?? 0) > 0)
  }, [sortedData])
  const esSuperponibleVehicular = Boolean(!salaLabel && !esBiblioteca && hasSectorData)

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

  const estadoSinRegistros = useMemo(() => {
    const puntosSinReg = sortedData.filter(d => Boolean(d.sin_registros))
    const todoSinReg = sortedData.length > 0 && puntosSinReg.length === sortedData.length
    const ultimoPunto = sortedData.length > 0 ? sortedData[sortedData.length - 1] : null
    const tramoFinalSinReg = Boolean(ultimoPunto?.sin_registros)
    const fechaFinalIso = ultimoPunto
      ? String(ultimoPunto.bucket || (ultimoPunto as any).fecha || '').slice(0, 10)
      : ''

    const formatearFecha = (isoRaw?: string | null, incluirHora = false) => {
      if (!isoRaw) return ''
      // Evita desfase UTC en fechas YYYY-MM-DD sin componente horario
      const normalizado = /^\d{4}-\d{2}-\d{2}$/.test(isoRaw) ? `${isoRaw}T12:00:00` : isoRaw
      const dt = new Date(normalizado)
      if (Number.isNaN(dt.getTime())) return ''
      return format(dt, incluirHora ? 'dd/MM/yyyy HH:mm' : 'dd/MM/yyyy', { locale: es })
    }

    const formatearDiaLista = (fechaIso: string) => {
      const dt = new Date(`${fechaIso}T12:00:00`)
      if (Number.isNaN(dt.getTime())) return fechaIso
      const txt = format(dt, 'EEE dd/MM/yyyy', { locale: es })
      return txt.charAt(0).toUpperCase() + txt.slice(1)
    }

    let incidenciasDiaFinal: IncidenciaOperativaResumen[] = fechaFinalIso ? obtenerIncidenciasDia(fechaFinalIso) : []
    if (todoSinReg && incidenciasDiaFinal.length === 0 && puntosSinReg.length > 0) {
      const vistas = new Set<number>()
      const fechasVacias = Array.from(
        new Set(puntosSinReg.map(p => String(p.bucket || (p as any).fecha || '').slice(0, 10)).filter(Boolean))
      )
      incidenciasDiaFinal = fechasVacias
        .flatMap(f => obtenerIncidenciasDia(f))
        .filter(inc => {
          if (vistas.has(inc.id)) return false
          vistas.add(inc.id)
          return true
        })
    }

    interface AlertaSinMotivo {
      key: string
      subespacio: string
      etiqueta: string
      fechaIso: string
      fechaFmt: string
      todoPeriodo: boolean
      ultimaLecturaFmt: string
      contextoAcademico?: string
    }
    const alertasSinMotivo: AlertaSinMotivo[] = []
    if (esBiblioteca && fechaFinalIso) {
      const ctxFinal = obtenerContextoAcademicoDia(fechaFinalIso)?.etiqueta
      const puntosDiaFinal = sortedData.filter(
        p => String(p.bucket || (p as any).fecha || '').slice(0, 10) === fechaFinalIso
      )
      const s1VaciaFinal = puntosDiaFinal.some(p => Boolean(p.sin_registros_sala1))
      const s2VaciaFinal = puntosDiaFinal.some(p => Boolean(p.sin_registros_sala2))

      if (todoSinReg || tramoFinalSinReg) {
        const tieneMotivo = todoSinReg
          ? incidenciasDiaFinal.length > 0
          : obtenerIncidenciasDia(fechaFinalIso, subespacioActivo).length > 0
        if (!tieneMotivo) {
          alertasSinMotivo.push({
            key: `global-${subespacioActivo}`,
            subespacio: subespacioActivo,
            etiqueta: salaLabel || 'Biblioteca',
            fechaIso: fechaFinalIso,
            fechaFmt: formatearFecha(ultimoPunto?.bucket || (ultimoPunto as any)?.fecha, false),
            todoPeriodo: todoSinReg,
            ultimaLecturaFmt: formatearFecha(ultimaLectura, true),
            contextoAcademico: ctxFinal,
          })
        } else if (!salaLabel && !todoSinReg) {
          // Si solo una sala registró motivo en un cierre total de vista global, advertir por la otra sala sin motivo
          if (s1VaciaFinal && obtenerIncidenciasDia(fechaFinalIso, 'sala_1').length === 0) {
            alertasSinMotivo.push({
              key: 'sala_1',
              subespacio: 'sala_1',
              etiqueta: 'Sala 1 (CSF02 2° Piso)',
              fechaIso: fechaFinalIso,
              fechaFmt: formatearFecha(fechaFinalIso, false),
              todoPeriodo: false,
              ultimaLecturaFmt: formatearFecha(ultimaLecturaSala1, true),
              contextoAcademico: ctxFinal,
            })
          }
          if (s2VaciaFinal && obtenerIncidenciasDia(fechaFinalIso, 'sala_2').length === 0) {
            alertasSinMotivo.push({
              key: 'sala_2',
              subespacio: 'sala_2',
              etiqueta: 'Sala 2 (CSF04 Pecera 1° Piso)',
              fechaIso: fechaFinalIso,
              fechaFmt: formatearFecha(fechaFinalIso, false),
              todoPeriodo: false,
              ultimaLecturaFmt: formatearFecha(ultimaLecturaSala2, true),
              contextoAcademico: ctxFinal,
            })
          }
        }
      } else if (!salaLabel) {
        if (s1VaciaFinal && obtenerIncidenciasDia(fechaFinalIso, 'sala_1').length === 0) {
          alertasSinMotivo.push({
            key: 'sala_1',
            subespacio: 'sala_1',
            etiqueta: 'Sala 1 (CSF02 2° Piso)',
            fechaIso: fechaFinalIso,
            fechaFmt: formatearFecha(fechaFinalIso, false),
            todoPeriodo: false,
            ultimaLecturaFmt: formatearFecha(ultimaLecturaSala1, true),
            contextoAcademico: ctxFinal,
          })
        }
        if (s2VaciaFinal && obtenerIncidenciasDia(fechaFinalIso, 'sala_2').length === 0) {
          alertasSinMotivo.push({
            key: 'sala_2',
            subespacio: 'sala_2',
            etiqueta: 'Sala 2 (CSF04 Pecera 1° Piso)',
            fechaIso: fechaFinalIso,
            fechaFmt: formatearFecha(fechaFinalIso, false),
            todoPeriodo: false,
            ultimaLecturaFmt: formatearFecha(ultimaLecturaSala2, true),
            contextoAcademico: ctxFinal,
          })
        }
      }
    }

    interface DiaSinRegistroResumen {
      key: string
      fechaIso: string
      fechaFmt: string
      diaCorto: string
      subespacio: string
      etiquetaSala: string
      incidencias: IncidenciaOperativaResumen[]
      contextoAcademico: { etiqueta: string; tono: string; detalle?: string } | null
    }
    const diasResumen: DiaSinRegistroResumen[] = []
    if (esBiblioteca) {
      const porFecha = new Map<string, { sinGlobal: boolean; sinS1: boolean; sinS2: boolean }>()
      sortedData.forEach(p => {
        const raw = p.bucket || (p as any).fecha || ''
        const f = raw ? String(raw).slice(0, 10) : ''
        if (!f) return
        let entry = porFecha.get(f)
        if (!entry) {
          entry = { sinGlobal: false, sinS1: false, sinS2: false }
          porFecha.set(f, entry)
        }
        if (p.sin_registros) entry.sinGlobal = true
        if (p.sin_registros_sala1) entry.sinS1 = true
        if (p.sin_registros_sala2) entry.sinS2 = true
      })

      const incRepresentadas = new Set<string>()
      const registrarItem = (f: string, sub: string, etiquetaSala: string, incs: IncidenciaOperativaResumen[]) => {
        incs.forEach(i => incRepresentadas.add(`${f}:${i.id}`))
        diasResumen.push({
          key: `${f}-${sub}`,
          fechaIso: f,
          fechaFmt: formatearFecha(f, false),
          diaCorto: formatearDiaLista(f),
          subespacio: sub,
          etiquetaSala,
          incidencias: incs,
          contextoAcademico: obtenerContextoAcademicoDia(f),
        })
      }

      porFecha.forEach((flags, f) => {
        if (subespacioActivo === 'sala_1' || subespacioActivo === 'sala_2') {
          if (flags.sinGlobal) {
            const etiq = subespacioActivo === 'sala_1' ? 'Sala 1 (CSF02)' : 'Sala 2 (CSF04 Pecera)'
            registrarItem(f, subespacioActivo, etiq, obtenerIncidenciasDia(f, subespacioActivo))
          }
        } else {
          if (flags.sinGlobal) {
            registrarItem(f, 'todos', 'Ambas salas', obtenerIncidenciasDia(f, 'todos'))
          } else {
            if (flags.sinS1) {
              registrarItem(f, 'sala_1', 'Sala 1 (CSF02)', obtenerIncidenciasDia(f, 'sala_1'))
            }
            if (flags.sinS2) {
              registrarItem(f, 'sala_2', 'Sala 2 (CSF04 Pecera)', obtenerIncidenciasDia(f, 'sala_2'))
            }
          }
        }
      })

      // Complementar con días del rango con incidencia operativa aunque no tengan puntos sin_registros (>7d)
      if (minFechaStr && maxFechaStr) {
        diasCalendario.forEach((d: DiaCalendarioResumen) => {
          if (d.fecha < minFechaStr || d.fecha > maxFechaStr) return
          const incsDia = obtenerIncidenciasDia(d.fecha).filter(
            inc => !incRepresentadas.has(`${d.fecha}:${inc.id}`)
          )
          if (incsDia.length === 0) return
          const grupos = new Map<string, IncidenciaOperativaResumen[]>()
          incsDia.forEach(inc => {
            const subRaw = (inc.subespacio || 'todos').trim().toLowerCase()
            const subKey = subespacioActivo !== 'todos'
              ? subespacioActivo
              : (subRaw === 'sala_1' || subRaw === 'sala_2' ? subRaw : 'todos')
            const arr = grupos.get(subKey) || []
            arr.push(inc)
            grupos.set(subKey, arr)
          })
          grupos.forEach((lista, subKey) => {
            const existente = diasResumen.find(item => item.fechaIso === d.fecha && item.subespacio === subKey)
            if (existente) {
              lista.forEach(inc => {
                if (!existente.incidencias.some(x => x.id === inc.id)) {
                  existente.incidencias.push(inc)
                }
              })
              return
            }
            const etiq = subKey === 'sala_1'
              ? 'Sala 1 (CSF02)'
              : subKey === 'sala_2'
                ? 'Sala 2 (CSF04 Pecera)'
                : 'Biblioteca (Global)'
            registrarItem(d.fecha, subKey, etiq, lista)
          })
        })
      }

      diasResumen.sort((a, b) => (a.fechaIso < b.fechaIso ? 1 : a.fechaIso > b.fechaIso ? -1 : a.subespacio.localeCompare(b.subespacio)))
    }

    const conMotivoCount = diasResumen.filter(d => d.incidencias.length > 0).length
    const contextoCalendarioCount = diasResumen.filter(d => d.incidencias.length === 0 && Boolean(d.contextoAcademico)).length
    const sinMotivoCount = diasResumen.length - conMotivoCount - contextoCalendarioCount

    return {
      todoSinReg,
      tramoFinalSinReg,
      fechaFinalIso,
      fechaFinalFmt: formatearFecha(ultimoPunto?.bucket || (ultimoPunto as any)?.fecha, false),
      ultimaLecturaFmt: formatearFecha(ultimaLectura, true),
      incidenciasDiaFinal,
      alertasSinMotivo,
      diasResumen,
      sinMotivoCount,
      conMotivoCount,
      contextoCalendarioCount,
    }
  }, [
    sortedData,
    ultimaLectura,
    ultimaLecturaSala1,
    ultimaLecturaSala2,
    mapaFechas,
    diasCalendario,
    minFechaStr,
    maxFechaStr,
    espacioId,
    subespacioActivo,
    salaLabel,
    esBiblioteca,
  ])

  const abrirModalMotivo = (fechaIso?: string, subespacioOverride?: string) => {
    setFechaModalMotivo(fechaIso || estadoSinRegistros.fechaFinalIso || obtenerFechaHoyChileIso())
    setSubespacioModalMotivo(subespacioOverride ?? '')
    setPopoverDiasAbierto(false)
    setModalMotivoAbierto(true)
  }

  // Disparar resize reactivo al montar o cuando cambian los datos o filtros
  useEffect(() => {
    const timer = setTimeout(() => {
      window.dispatchEvent(new Event('resize'))
    }, 120)
    return () => clearTimeout(timer)
  }, [sortedData.length, mostrarSala1, mostrarSala2, mostrarTotalCombinado, capacidad, salaLabel])

  const xVals: string[] = []
  const yVals: number[] = []
  const yValsSala1: number[] = []
  const yValsSala2: number[] = []
  const yValsCSF11: number[] = []
  const yValsCSF21: number[] = []
  const yValsCHS01: number[] = []
  const customDataListSala1: any[] = []
  const customDataListSala2: any[] = []
  const customDataListCSF11: any[] = []
  const customDataListCSF21: any[] = []
  const customDataListCHS01: any[] = []
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

    const valCSF11 = d.vehiculos_csf11 ?? 0
    const valCSF21 = d.vehiculos_csf21 ?? 0
    const valCHS01 = d.vehiculos_chs01 ?? 0
    yValsCSF11.push(valCSF11)
    yValsCSF21.push(valCSF21)
    yValsCHS01.push(valCHS01)

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
    const incidenciasDia = obtenerIncidenciasDia(fechaIso)
    if (incidenciasDia.length > 0) {
      incidenciasDia.forEach((inc) => {
        const meta = ETIQUETAS_INCIDENCIA[inc.tipo] || ETIQUETAS_INCIDENCIA.otro
        const rangoH = inc.hora_inicio && inc.hora_fin ? ` (${inc.hora_inicio}–${inc.hora_fin})` : ''
        contextParts.push(`<b>${meta.etiqueta}${rangoH}:</b> ${inc.titulo}`)
        if (inc.descripcion && (!cal?.descripcion || !cal.descripcion.includes(inc.descripcion))) {
          contextParts.push(`Observación: ${inc.descripcion}`)
        }
      })
    }
    if (mostrar24h && es24hFecha(fechaIso)) {
      contextParts.push('<b>Campaña 24 Horas Activa</b>')
    }
    const contextPartsComb = [...contextParts]
    if (d.sin_registros && incidenciasDia.length === 0) {
      contextPartsComb.push('<i>Sin marcajes registrados en esta franja operativa</i>')
    }
    const contextStr = contextPartsComb.length > 0 ? `<br>${contextPartsComb.join('<br>')}` : ''

    let contextStrS1 = contextStr
    let contextStrS2 = contextStr
    if (esSuperponible) {
      if (d.sin_registros_sala1 && obtenerIncidenciasDia(fechaIso, 'sala_1').length === 0) {
        contextStrS1 = `${contextStr}<br><i>Sin marcajes registrados en Sala 1 en esta franja operativa</i>`
      }
      if (d.sin_registros_sala2 && obtenerIncidenciasDia(fechaIso, 'sala_2').length === 0) {
        contextStrS2 = `${contextStr}<br><i>Sin marcajes registrados en Sala 2 en esta franja operativa</i>`
      }
    }

    // Cabecera exacta: Miércoles 13 de mayo 2026, 10:00 hrs
    let fullDateHeader = ''
    if (rawBucket) {
      const f = format(dObj, "EEEE d 'de' MMMM yyyy, HH:mm' hrs'", { locale: es })
      fullDateHeader = f.charAt(0).toUpperCase() + f.slice(1)
    }

    const pctS1 = capSala1 > 0 ? Math.round((valS1 / capSala1) * 100) : 0
    const pctS2 = capSala2 > 0 ? Math.round((valS2 / capSala2) * 100) : 0
    const pctCSF11 = capSector1 > 0 ? Math.round((valCSF11 / capSector1) * 100) : 0
    const pctCSF21 = capSector2 > 0 ? Math.round((valCSF21 / capSector2) * 100) : 0
    const pctCHS01 = capSector3 > 0 ? Math.round((valCHS01 / capSector3) * 100) : 0
    const pctComb = capacidad > 0 ? Math.round((aforo / capacidad) * 100) : 0

    customDataListSala1.push([fullDateHeader, pctS1, contextStrS1])
    customDataListSala2.push([fullDateHeader, pctS2, contextStrS2])
    customDataListCSF11.push([fullDateHeader, pctCSF11, contextStr, d.entradas_csf11 ?? 0, d.salidas_csf11 ?? 0])
    customDataListCSF21.push([fullDateHeader, pctCSF21, contextStr, d.entradas_csf21 ?? 0, d.salidas_csf21 ?? 0])
    customDataListCHS01.push([fullDateHeader, pctCHS01, contextStr, d.entradas_chs01 ?? 0, d.salidas_chs01 ?? 0])
    customDataListCombinado.push([fullDateHeader, pctComb, contextStr, inCount, d.salidas ?? 0, valS1, valS2])
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

  // Construir datos del gráfico según los checkboxes de Sala 1, Sala 2 y Total Combinado
  const chartData: Data[] = useMemo(() => {
    if (esSuperponible && (mostrarSala1 || mostrarSala2 || mostrarTotalCombinado)) {
      const traces: Data[] = []

      if (mostrarTotalCombinado) {
        traces.push({
          x: xVals,
          y: yVals,
          customdata: customDataListCombinado,
          type: 'scatter',
          mode: 'lines',
          name: `Total Combinado (${capacidad} as.)`,
          fill: 'tozeroy',
          fillcolor: 'rgba(5, 150, 105, 0.08)',
          line: { color: '#059669', width: 2.5, shape: 'spline' },
          hovertemplate:
            `<b>%{customdata[0]}</b><br>` +
            `<b>Total Combinado:</b> %{y} personas (Sala 1: %{customdata[5]} | Sala 2: %{customdata[6]})<br>` +
            `Ocupación agregada: <b>%{customdata[1]}%</b> (Capacidad: ${capacidad} asientos)` +
            `%{customdata[2]}<extra></extra>`,
        })
      }

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

    if (esSuperponibleVehicular && (mostrarCSF11 || mostrarCSF21 || mostrarCHS01)) {
      const traces: Data[] = []

      if (mostrarCSF11) {
        traces.push({
          x: xVals,
          y: yValsCSF11,
          customdata: customDataListCSF11,
          type: 'scatter',
          mode: 'lines',
          name: `CSF11: Edificio 11 (${capSector1} pl.)`,
          fill: 'tozeroy',
          fillcolor: 'rgba(0, 43, 73, 0.12)',
          line: { color: '#002B49', width: 2.5, shape: 'spline' },
          hovertemplate:
            `<b>%{customdata[0]}</b><br>` +
            `<b>Vehículos presentes (CSF11 — Edificio 11):</b> %{y} vehículos<br>` +
            `<b>Flujo horario:</b> %{customdata[3]} entradas | %{customdata[4]} salidas<br>` +
            `Ocupación de sector: <b>%{customdata[1]}%</b> (Capacidad: ${capSector1} plazas)` +
            `%{customdata[2]}<extra></extra>`,
        })
      }

      if (mostrarCSF21) {
        traces.push({
          x: xVals,
          y: yValsCSF21,
          customdata: customDataListCSF21,
          type: 'scatter',
          mode: 'lines',
          name: `CSF21: Edificio 21 (${capSector2} pl.)`,
          fill: 'tozeroy',
          fillcolor: 'rgba(217, 119, 6, 0.14)',
          line: { color: '#D97706', width: 2.5, shape: 'spline' },
          hovertemplate:
            `<b>%{customdata[0]}</b><br>` +
            `<b>Vehículos presentes (CSF21 — Edificio 21):</b> %{y} vehículos<br>` +
            `<b>Flujo horario:</b> %{customdata[3]} entradas | %{customdata[4]} salidas<br>` +
            `Ocupación de sector: <b>%{customdata[1]}%</b> (Capacidad: ${capSector2} plazas)` +
            `%{customdata[2]}<extra></extra>`,
        })
      }

      if (mostrarCHS01) {
        traces.push({
          x: xVals,
          y: yValsCHS01,
          customdata: customDataListCHS01,
          type: 'scatter',
          mode: 'lines',
          name: `CHS01: Hosp. Simulación (${capSector3} pl.)`,
          fill: 'tozeroy',
          fillcolor: 'rgba(13, 148, 136, 0.14)',
          line: { color: '#0D9488', width: 2.5, shape: 'spline' },
          hovertemplate:
            `<b>%{customdata[0]}</b><br>` +
            `<b>Vehículos presentes (CHS01 — Hospital Simulación):</b> %{y} vehículos<br>` +
            `<b>Flujo horario:</b> %{customdata[3]} entradas | %{customdata[4]} salidas<br>` +
            `Ocupación de sector: <b>%{customdata[1]}%</b> (Capacidad: ${capSector3} plazas)` +
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
    esSuperponibleVehicular,
    mostrarSala1,
    mostrarSala2,
    mostrarTotalCombinado,
    mostrarCSF11,
    mostrarCSF21,
    mostrarCHS01,
    salaLabel,
    xVals,
    yValsSala1,
    yValsSala2,
    yValsCSF11,
    yValsCSF21,
    yValsCHS01,
    yVals,
    customDataListSala1,
    customDataListSala2,
    customDataListCSF11,
    customDataListCSF21,
    customDataListCHS01,
    customDataListCombinado,
    capSala1,
    capSala2,
    capacidad,
    unit,
  ])

  // Formar líneas de umbrales según salas activas
  const thresholdShapes = useMemo(() => {
    if (esSuperponible && (mostrarSala1 || mostrarSala2 || mostrarTotalCombinado)) {
      const lines: any[] = []

      if (mostrarTotalCombinado) {
        lines.push({
          type: 'line' as const,
          x0: 0,
          x1: 1,
          xref: 'paper' as const,
          y0: capacidad,
          y1: capacidad,
          line: { color: '#059669', width: 1.8, dash: 'dash' },
        })
      }

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

    if (esSuperponibleVehicular && (mostrarCSF11 || mostrarCSF21 || mostrarCHS01)) {
      const lines: any[] = []

      if (mostrarCSF21) {
        lines.push({
          type: 'line' as const,
          x0: 0,
          x1: 1,
          xref: 'paper' as const,
          y0: capSector2,
          y1: capSector2,
          line: { color: '#D97706', width: 1.5, dash: 'dash' },
        })
      }

      if (mostrarCSF11) {
        lines.push({
          type: 'line' as const,
          x0: 0,
          x1: 1,
          xref: 'paper' as const,
          y0: capSector1,
          y1: capSector1,
          line: { color: '#002B49', width: 1.5, dash: 'dash' },
        })
      }

      if (mostrarCHS01) {
        lines.push({
          type: 'line' as const,
          x0: 0,
          x1: 1,
          xref: 'paper' as const,
          y0: capSector3,
          y1: capSector3,
          line: { color: '#0D9488', width: 1.5, dash: 'dash' },
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
  }, [esSuperponible, esSuperponibleVehicular, mostrarSala1, mostrarSala2, mostrarTotalCombinado, mostrarCSF11, mostrarCSF21, mostrarCHS01, capSala1, capSala2, capSector1, capSector2, capSector3, capacidad, alerta70, alerta85])

  const annotations = useMemo(() => {
    if (esSuperponible && (mostrarSala1 || mostrarSala2 || mostrarTotalCombinado)) {
      const ann: any[] = []

      if (mostrarTotalCombinado) {
        ann.push({
          xref: 'paper' as const,
          x: 1.01,
          y: capacidad,
          text: `Máx Total (${capacidad})`,
          showarrow: false,
          font: { size: 9, color: '#059669' },
          xanchor: 'left' as const,
        })
      }

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

    if (esSuperponibleVehicular && (mostrarCSF11 || mostrarCSF21 || mostrarCHS01)) {
      const ann: any[] = []

      if (mostrarCSF21) {
        ann.push({
          xref: 'paper' as const,
          x: 1.01,
          y: capSector2,
          text: `Máx CSF21 (${capSector2})`,
          showarrow: false,
          font: { size: 9, color: '#D97706' },
          xanchor: 'left' as const,
        })
      }

      if (mostrarCSF11) {
        ann.push({
          xref: 'paper' as const,
          x: 1.01,
          y: capSector1,
          text: `Máx CSF11 (${capSector1})`,
          showarrow: false,
          font: { size: 9, color: '#002B49' },
          xanchor: 'left' as const,
        })
      }

      if (mostrarCHS01) {
        ann.push({
          xref: 'paper' as const,
          x: 1.01,
          y: capSector3,
          text: `Máx CHS01 (${capSector3})`,
          showarrow: false,
          font: { size: 9, color: '#0D9488' },
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
  }, [esSuperponible, esSuperponibleVehicular, mostrarSala1, mostrarSala2, mostrarTotalCombinado, mostrarCSF11, mostrarCSF21, mostrarCHS01, capSala1, capSala2, capSector1, capSector2, capSector3, capacidad, alerta70, alerta85])

  const maxY = useMemo(() => {
    if (esSuperponible && (mostrarSala1 || mostrarSala2 || mostrarTotalCombinado)) {
      let maxVal = 0
      let maxCap = 0
      if (mostrarTotalCombinado) {
        maxVal = Math.max(maxVal, ...(yVals.length > 0 ? yVals : [0]))
        maxCap = Math.max(maxCap, capacidad)
      }
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

    if (esSuperponibleVehicular && (mostrarCSF11 || mostrarCSF21 || mostrarCHS01)) {
      let maxVal = 0
      let maxCap = 0
      if (mostrarCSF11) {
        maxVal = Math.max(maxVal, ...(yValsCSF11.length > 0 ? yValsCSF11 : [0]))
        maxCap = Math.max(maxCap, capSector1)
      }
      if (mostrarCSF21) {
        maxVal = Math.max(maxVal, ...(yValsCSF21.length > 0 ? yValsCSF21 : [0]))
        maxCap = Math.max(maxCap, capSector2)
      }
      if (mostrarCHS01) {
        maxVal = Math.max(maxVal, ...(yValsCHS01.length > 0 ? yValsCHS01 : [0]))
        maxCap = Math.max(maxCap, capSector3)
      }
      return Math.max(maxCap + 15, maxVal + 10, 50)
    }

    const maxVal = yVals.length > 0 ? Math.max(...yVals) : 0
    return Math.max(Math.ceil(capacidad * 1.15), maxVal + 5, 20)
  }, [esSuperponible, esSuperponibleVehicular, mostrarSala1, mostrarSala2, mostrarTotalCombinado, mostrarCSF11, mostrarCSF21, mostrarCHS01, capSala1, capSala2, capSector1, capSector2, capSector3, capacidad, yValsSala1, yValsSala2, yValsCSF11, yValsCSF21, yValsCHS01, yVals])

  const layout: Partial<Layout> = {
    autosize: true,
    hovermode: 'closest',
    uirevision: `${sortedData.length}_${capacidad}_${mostrarSala1}_${mostrarSala2}_${mostrarTotalCombinado}_${mostrarCSF11}_${mostrarCSF21}_${mostrarCHS01}_${salaLabel || 'global'}_${contextShapes.length}`,
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
      range: [0, salaLabel ? maxY : Math.max(maxY, esBiblioteca ? 240 : 65)],
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
    showlegend: Boolean((esSuperponible && (mostrarSala1 || mostrarSala2 || mostrarTotalCombinado)) || (esSuperponibleVehicular && (mostrarCSF11 || mostrarCSF21 || mostrarCHS01))),
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
          {/* Checkboxes independientes para Salas (Biblioteca) o Sectores (Estacionamientos) */}
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
              <label className="flex items-center gap-1.5 cursor-pointer font-semibold text-[#059669] select-none hover:opacity-85 ml-1.5">
                <input
                  type="checkbox"
                  checked={mostrarTotalCombinado}
                  onChange={(e) => setMostrarTotalCombinado(e.target.checked)}
                  className="rounded text-[#059669] focus:ring-[#059669] h-3.5 w-3.5 cursor-pointer"
                />
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#059669]" />
                <span>Total Combinado</span>
              </label>
            </div>
          ) : esSuperponibleVehicular ? (
            <div className="flex items-center gap-2 bg-white px-2.5 py-1 rounded-lg border border-slate-200 shadow-2xs">
              <span className="text-[10.5px] font-bold text-slate-700 mr-0.5">Sectores:</span>
              <label className="flex items-center gap-1.5 cursor-pointer font-semibold text-[#002B49] select-none hover:opacity-85">
                <input
                  type="checkbox"
                  checked={mostrarCSF11}
                  onChange={(e) => setMostrarCSF11(e.target.checked)}
                  className="rounded text-[#002B49] focus:ring-[#002B49] h-3.5 w-3.5 cursor-pointer"
                />
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#002B49]" />
                <span>CSF11 (40 pl.)</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer font-semibold text-[#D97706] select-none hover:opacity-85 ml-1.5">
                <input
                  type="checkbox"
                  checked={mostrarCSF21}
                  onChange={(e) => setMostrarCSF21(e.target.checked)}
                  className="rounded text-[#D97706] focus:ring-[#D97706] h-3.5 w-3.5 cursor-pointer"
                />
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#D97706]" />
                <span>CSF21 (50 pl.)</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer font-semibold text-[#0D9488] select-none hover:opacity-85 ml-1.5">
                <input
                  type="checkbox"
                  checked={mostrarCHS01}
                  onChange={(e) => setMostrarCHS01(e.target.checked)}
                  className="rounded text-[#0D9488] focus:ring-[#0D9488] h-3.5 w-3.5 cursor-pointer"
                />
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#0D9488]" />
                <span>CHS01 (35 pl.)</span>
              </label>
            </div>
          ) : salaLabel ? (
            <span className="text-[10.5px] font-bold px-2 py-0.5 rounded-md bg-blue-100 text-uct-blue-primary">
              Filtrado por: {salaLabel} ({capacidad} {esBiblioteca ? 'asientos' : 'plazas'})
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

        <div className="ml-auto flex flex-wrap items-center gap-2 relative" ref={popoverDiasRef}>
          {esBiblioteca && isMultiDay && estadoSinRegistros.diasResumen.length > 0 && (
            <>
              <button
                type="button"
                onClick={() => setPopoverDiasAbierto((v) => !v)}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border font-semibold text-[11px] transition cursor-pointer shadow-2xs ${
                  estadoSinRegistros.sinMotivoCount > 0
                    ? 'bg-amber-50 hover:bg-amber-100 text-amber-900 border-amber-300/90'
                    : estadoSinRegistros.conMotivoCount > 0
                      ? 'bg-indigo-50 hover:bg-indigo-100 text-indigo-900 border-indigo-200'
                      : 'bg-slate-100 hover:bg-slate-200 text-slate-700 border-slate-200'
                }`}
                title="Auditar días operativos sin marcajes e incidencias registradas en este período"
              >
                <Info
                  size={13}
                  className={
                    estadoSinRegistros.sinMotivoCount > 0
                      ? 'text-amber-600'
                      : estadoSinRegistros.conMotivoCount > 0
                        ? 'text-indigo-600'
                        : 'text-slate-500'
                  }
                />
                <span>
                  {(() => {
                    const { sinMotivoCount, conMotivoCount, contextoCalendarioCount } = estadoSinRegistros
                    const otros = conMotivoCount + contextoCalendarioCount
                    if (sinMotivoCount > 0) {
                      return `${sinMotivoCount} día${sinMotivoCount === 1 ? '' : 's'} sin motivo${otros > 0 ? ` · ${otros} con contexto` : ''}`
                    }
                    if (conMotivoCount > 0) {
                      return `${conMotivoCount} incidencia${conMotivoCount === 1 ? '' : 's'} operativa${conMotivoCount === 1 ? '' : 's'}`
                    }
                    return `${contextoCalendarioCount} día${contextoCalendarioCount === 1 ? '' : 's'} en receso/paro`
                  })()}
                </span>
                <ChevronDown
                  size={13}
                  className={`transition-transform duration-150 ${popoverDiasAbierto ? 'rotate-180' : ''}`}
                />
              </button>

              {popoverDiasAbierto && (
                <div className="absolute right-0 top-full mt-1.5 w-[min(92vw,460px)] bg-white border border-slate-200 rounded-xl shadow-xl z-40 p-3 text-xs text-slate-700">
                  <div className="flex items-center justify-between gap-2 pb-2 mb-2 border-b border-slate-100">
                    <div>
                      <div className="font-bold text-slate-900">Días operativos sin marcajes e incidencias</div>
                      <div className="text-[11px] text-slate-500">
                        {estadoSinRegistros.sinMotivoCount} sin motivo | {estadoSinRegistros.conMotivoCount} incidencia{estadoSinRegistros.conMotivoCount === 1 ? '' : 's'} | {estadoSinRegistros.contextoCalendarioCount} calendario
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setPopoverDiasAbierto(false)}
                      className="p-1 text-slate-400 hover:text-slate-700 rounded-md cursor-pointer"
                      aria-label="Cerrar resumen"
                    >
                      <X size={14} />
                    </button>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-1.5 mb-2">
                    <div className="flex flex-wrap items-center gap-1">
                      {([
                        { id: 'todos', label: 'Todos' },
                        { id: 'sin_motivo', label: 'Sin motivo' },
                        { id: 'calendario', label: 'Calendario' },
                        { id: 'con_motivo', label: 'Con motivo' },
                      ] as const).map((op) => (
                        <button
                          key={op.id}
                          type="button"
                          onClick={() => setFiltroEstadoDias(op.id)}
                          className={`px-2 py-0.5 rounded-md text-[11px] font-semibold border transition cursor-pointer ${
                            filtroEstadoDias === op.id
                              ? 'bg-slate-800 text-white border-slate-800'
                              : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                          }`}
                        >
                          {op.label}
                        </button>
                      ))}
                    </div>

                    {subespacioActivo === 'todos' && (
                      <div className="flex items-center gap-1">
                        {([
                          { id: 'todas', label: 'Todas' },
                          { id: 'sala_1', label: 'Sala 1' },
                          { id: 'sala_2', label: 'Sala 2' },
                        ] as const).map((op) => (
                          <button
                            key={op.id}
                            type="button"
                            onClick={() => setFiltroSalaDias(op.id)}
                            className={`px-2 py-0.5 rounded-md text-[11px] font-semibold border transition cursor-pointer ${
                              filtroSalaDias === op.id
                                ? 'bg-uct-blue-primary text-white border-uct-blue-primary'
                                : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                            }`}
                          >
                            {op.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="max-h-[280px] overflow-y-auto divide-y divide-slate-100 pr-0.5">
                    {(() => {
                      const salaDiasEfectiva = subespacioActivo === 'todos' ? filtroSalaDias : 'todas'
                      const filtrados = estadoSinRegistros.diasResumen.filter((item) => {
                        if (filtroEstadoDias === 'sin_motivo' && (item.incidencias.length > 0 || item.contextoAcademico)) return false
                        if (filtroEstadoDias === 'con_motivo' && item.incidencias.length === 0) return false
                        if (filtroEstadoDias === 'calendario' && (item.incidencias.length > 0 || !item.contextoAcademico)) return false
                        if (salaDiasEfectiva !== 'todas' && item.subespacio !== 'todos' && item.subespacio !== salaDiasEfectiva) {
                          return false
                        }
                        return true
                      })
                      if (filtrados.length === 0) {
                        return (
                          <div className="py-6 text-center text-slate-400 text-[11px]">
                            No hay registros que coincidan con el filtro seleccionado.
                          </div>
                        )
                      }
                      return filtrados.map((item) => {
                        const sinCobertura = item.incidencias.length === 0 && !item.contextoAcademico
                        return (
                          <div key={item.key} className="py-2 flex items-start justify-between gap-2">
                            <div className="min-w-0 space-y-1">
                              <div className="flex flex-wrap items-center gap-1.5">
                                <span className="font-semibold text-slate-900">{item.diaCorto}</span>
                                <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-semibold">
                                  {item.etiquetaSala}
                                </span>
                                {sinCobertura ? (
                                  <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-900 text-[10px] font-bold">
                                    Sin motivo
                                  </span>
                                ) : item.contextoAcademico && (
                                  <span
                                    className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold ${item.contextoAcademico.tono}`}
                                    title={item.contextoAcademico.detalle || item.contextoAcademico.etiqueta}
                                  >
                                    {item.contextoAcademico.etiqueta}
                                  </span>
                                )}
                              </div>
                              {item.incidencias.length > 0 && (
                                <div className="space-y-1">
                                  {item.incidencias.map((inc) => {
                                    const meta = ETIQUETAS_INCIDENCIA[inc.tipo] || ETIQUETAS_INCIDENCIA.otro
                                    return (
                                      <div key={inc.id} className="flex flex-wrap items-center gap-1.5 text-[11px]">
                                        <span className={`px-1.5 py-0.5 rounded border ${meta.tono} font-semibold`}>
                                          {meta.etiqueta}
                                        </span>
                                        <span className="text-slate-700 truncate max-w-[210px]" title={inc.titulo}>
                                          {inc.titulo}
                                        </span>
                                        {puedeEditarIncidente && (
                                          <button
                                            type="button"
                                            disabled={eliminarIncidenciaMutation.isPending}
                                            onClick={() => {
                                              if (window.confirm(`¿Eliminar el registro "${inc.titulo}"?`)) {
                                                eliminarIncidenciaMutation.mutate(inc.id)
                                              }
                                            }}
                                            className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-slate-50 hover:bg-rose-50 text-slate-600 hover:text-rose-700 border border-slate-200 text-[10px] font-semibold cursor-pointer disabled:opacity-50"
                                            title="Quitar incidencia"
                                          >
                                            <Trash2 size={10} />
                                            <span>Quitar</span>
                                          </button>
                                        )}
                                      </div>
                                    )
                                  })}
                                </div>
                              )}
                            </div>

                            {puedeEditarIncidente && (
                              <button
                                type="button"
                                onClick={() => abrirModalMotivo(item.fechaIso, item.subespacio)}
                                className={`shrink-0 px-2 py-1 rounded-md text-[11px] font-semibold border transition cursor-pointer ${
                                  sinCobertura
                                    ? 'bg-amber-100 hover:bg-amber-200 text-amber-900 border-amber-300'
                                    : 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200'
                                }`}
                              >
                                {sinCobertura ? 'Registrar' : item.incidencias.length > 0 ? '+ Otro' : '+ Incidencia'}
                              </button>
                            )}
                          </div>
                        )
                      })
                    })()}
                  </div>
                </div>
              )}
            </>
          )}

          {puedeEditarIncidente && (
            <button
              type="button"
              onClick={() => abrirModalMotivo(estadoSinRegistros.fechaFinalIso, subespacioActivo)}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white hover:bg-amber-50 text-slate-700 hover:text-amber-800 border border-slate-200 hover:border-amber-300 font-semibold text-[11px] transition cursor-pointer shadow-2xs"
              title="Documentar falla de sensor, apertura manual, mantención o jornada sin afluencia"
            >
              <ClipboardEdit size={13} />
              <span>Anotar incidente</span>
            </button>
          )}
        </div>
      </div>

      {estadoSinRegistros.incidenciasDiaFinal.length > 0 && (
        <div className="space-y-1.5 shrink-0">
          {estadoSinRegistros.incidenciasDiaFinal.map((inc) => {
            const meta = ETIQUETAS_INCIDENCIA[inc.tipo] || ETIQUETAS_INCIDENCIA.otro
            const rangoH = inc.hora_inicio && inc.hora_fin ? ` (${inc.hora_inicio}–${inc.hora_fin} hrs)` : ''
            const scopeTag =
              subespacioActivo === 'todos' && inc.subespacio === 'sala_1'
                ? '[Sala 1] '
                : subespacioActivo === 'todos' && inc.subespacio === 'sala_2'
                  ? '[Sala 2] '
                  : ''
            return (
              <div
                key={inc.id}
                className={`flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 rounded-lg border text-xs ${meta.tono}`}
              >
                <div className="flex items-start sm:items-center gap-2 min-w-0">
                  <Info size={14} className={`${meta.texto} shrink-0 mt-0.5 sm:mt-0`} />
                  <span className="leading-snug">
                    {scopeTag && <span className="font-bold">{scopeTag}</span>}
                    <span className="font-bold">{meta.etiqueta}{rangoH}:</span>{' '}
                    <span className="font-semibold">{inc.titulo}</span>
                    {inc.descripcion ? ` — ${inc.descripcion}` : ''}
                    {estadoSinRegistros.ultimaLecturaFmt && (estadoSinRegistros.todoSinReg || estadoSinRegistros.tramoFinalSinReg) && (
                      <span className="ml-1.5 opacity-80">
                        (Último marcaje: {estadoSinRegistros.ultimaLecturaFmt})
                      </span>
                    )}
                  </span>
                </div>
                {puedeEditarIncidente && (
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      type="button"
                      onClick={() => abrirModalMotivo(estadoSinRegistros.fechaFinalIso, inc.subespacio || subespacioActivo)}
                      className="px-2 py-0.5 rounded bg-white/80 hover:bg-white border border-current/20 text-[11px] font-semibold transition cursor-pointer"
                    >
                      Agregar otro
                    </button>
                    <button
                      type="button"
                      disabled={eliminarIncidenciaMutation.isPending}
                      onClick={() => {
                        if (window.confirm(`¿Eliminar el registro "${inc.titulo}"?`)) {
                          eliminarIncidenciaMutation.mutate(inc.id)
                        }
                      }}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white/80 hover:bg-rose-50 hover:text-rose-700 border border-current/20 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
                      title="Quitar observación registrada"
                    >
                      <Trash2 size={11} />
                      <span>Quitar</span>
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {estadoSinRegistros.alertasSinMotivo.length > 0 && (
        <div className="space-y-1.5 shrink-0">
          {estadoSinRegistros.alertasSinMotivo.map((alerta) => (
            <div
              key={alerta.key}
              className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 rounded-lg bg-amber-50/90 border border-amber-200/80 text-amber-900 text-xs"
            >
              <div className="flex items-center gap-2 min-w-0">
                <Info size={14} className="text-amber-600 shrink-0" />
                <span>
                  {alerta.todoPeriodo
                    ? `Sin marcajes registrados en ${alerta.etiqueta} para este período (horario operativo graficado en 0).`
                    : `Sin marcajes registrados en ${alerta.etiqueta} el ${alerta.fechaFmt} (horario operativo graficado en 0).`}
                  {alerta.contextoAcademico && (
                    <span className="ml-1 opacity-85">({alerta.contextoAcademico}).</span>
                  )}
                  {alerta.ultimaLecturaFmt && (
                    <span className="font-semibold ml-1">
                      Último marcaje registrado: {alerta.ultimaLecturaFmt}.
                    </span>
                  )}
                </span>
              </div>
              {puedeEditarIncidente && (
                <button
                  type="button"
                  onClick={() => abrirModalMotivo(alerta.fechaIso, alerta.subespacio)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-amber-100 hover:bg-amber-200 text-amber-900 border border-amber-300 font-semibold text-[11px] transition cursor-pointer shrink-0"
                >
                  <ClipboardEdit size={12} />
                  <span>Registrar motivo</span>
                </button>
              )}
            </div>
          ))}
        </div>
      )}

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
        {esSuperponible && (mostrarSala1 || mostrarSala2 || mostrarTotalCombinado) ? (
          <div className="flex flex-wrap items-center gap-4">
            {mostrarTotalCombinado && (
              <span className="flex items-center gap-1.5 font-medium text-slate-800">
                <span className="w-3.5 h-1 rounded-xs bg-[#059669] inline-block" />
                <span>Total Combinado</span>
                <span className="text-slate-500 font-normal">| Capacidad: <b>{capacidad} as.</b></span>
              </span>
            )}
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
        ) : esSuperponibleVehicular && (mostrarCSF11 || mostrarCSF21 || mostrarCHS01) ? (
          <div className="flex flex-wrap items-center gap-4">
            {mostrarCSF11 && (
              <span className="flex items-center gap-1.5 font-medium text-slate-800">
                <span className="w-3.5 h-1 rounded-xs bg-[#002B49] inline-block" />
                <span>CSF11: Edificio 11</span>
                <span className="text-slate-500 font-normal">| Capacidad: <b>{capSector1} pl.</b></span>
              </span>
            )}
            {mostrarCSF21 && (
              <span className="flex items-center gap-1.5 font-medium text-slate-800">
                <span className="w-3.5 h-1 rounded-xs bg-[#D97706] inline-block" />
                <span>CSF21: Edificio 21</span>
                <span className="text-slate-500 font-normal">| Capacidad: <b>{capSector2} pl.</b></span>
              </span>
            )}
            {mostrarCHS01 && (
              <span className="flex items-center gap-1.5 font-medium text-slate-800">
                <span className="w-3.5 h-1 rounded-xs bg-[#059669] inline-block" />
                <span>CHS01: Hosp. Simulación</span>
                <span className="text-slate-500 font-normal">| Capacidad: <b>{capSector3} pl.</b></span>
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

      {puedeEditarIncidente && (
        <ModalRegistrarMotivoOperativo
          abierto={modalMotivoAbierto}
          onClose={() => setModalMotivoAbierto(false)}
          espacioId={espacioId as 1 | 2}
          subespacioInicial={subespacioModalMotivo || subespacioActivo}
          fechaInicial={fechaModalMotivo || estadoSinRegistros.fechaFinalIso}
          etiquetaRecinto={
            subespacioModalMotivo === 'sala_1'
              ? 'Sala 1 (CSF02 2° Piso)'
              : subespacioModalMotivo === 'sala_2'
                ? 'Sala 2 (CSF04 Pecera 1° Piso)'
                : salaLabel
          }
        />
      )}
    </div>
  )
}

export const OccupancyAreaChart = memo(OccupancyAreaChartComponent)
export default OccupancyAreaChart
