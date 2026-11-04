import React, { useState, useMemo, useEffect } from 'react'
import {
  ShieldCheck,
  Database,
  AlertTriangle,
  Clock,
  ArrowUpDown,
  Calendar,
  DoorClosed,
  UserCheck,
  RotateCcw,
  X,
  CheckCircle2,
  Sparkles,
  Building2,
  GraduationCap,
  School,
  SlidersHorizontal,
  ChevronUp,
  ChevronDown,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { DataFilters, fetchHorarios, HorarioOperacion } from '../../api/client'
import { useSalasBiblioteca, useAvailableFilters } from '../../hooks/useAttendance'
import { DateRange } from '../../types/dateRange'

export type DataScope = 'conformes' | 'todos' | 'anomalias'

interface ScopeSelectorProps {
  modulo?: 'biblioteca' | 'estacionamiento'
  filters?: DataFilters
  onChangeFilters?: (filters: DataFilters) => void
  value?: DataScope
  onChange?: (scope: DataScope) => void
  totalCount?: number
  actionRight?: React.ReactNode
  dateRange?: DateRange
  onRangeChange?: (range: DateRange) => void
}

const DIAS_OPTIONS = [
  { id: 'lunes', label: 'Lun' },
  { id: 'martes', label: 'Mar' },
  { id: 'miercoles', label: 'Mié' },
  { id: 'jueves', label: 'Jue' },
  { id: 'viernes', label: 'Vie' },
  { id: 'sabado', label: 'Sáb' },
  { id: 'domingo', label: 'Dom' },
]

export const ScopeSelector: React.FC<ScopeSelectorProps> = ({
  modulo = 'biblioteca',
  filters = {
    alcance: 'conformes',
    regimen_horario: 'todos',
    direccion: 'todos',
    dias_semana: '',
    door: '',
    perfil_visita: 'todos',
    marcajes: 'todos',
    incluir_pausas_bano: true,
    desduplicar_rafagas: true,
  },
  onChangeFilters,
  value,
  onChange,
  totalCount,
  actionRight,
  dateRange,
  onRangeChange,
}) => {
  // Sincronización entre props legacy (value/onChange) y filters completos
  const currentScope = filters.alcance || value || 'conformes'

  // --- 1. Régimen Horario Dinámico (Casillas Multi-Selección) ---
  const espacioId = modulo === 'biblioteca' ? 1 : 2
  const { data: salasBiblioteca = [] } = useSalasBiblioteca(espacioId)
  const { data: availableFilters } = useAvailableFilters(espacioId)

  // Año dinámico derivado del rango de fechas consultado (dateRange)
  const anioConsultado = useMemo(() => {
    if (dateRange?.fin) {
      const y = parseInt(dateRange.fin.slice(0, 4), 10)
      if (!isNaN(y)) return y
    }
    if (dateRange?.inicio) {
      const y = parseInt(dateRange.inicio.slice(0, 4), 10)
      if (!isNaN(y)) return y
    }
    return new Date().getFullYear()
  }, [dateRange?.fin, dateRange?.inicio])

  const { data: horariosList = [] } = useQuery({
    queryKey: ['horarios-operacion-scope', espacioId, anioConsultado],
    queryFn: () => fetchHorarios({ espacio_id: espacioId, anio: anioConsultado }),
    staleTime: 60_000,
  })

  const [pendingScheduleModal, setPendingScheduleModal] = useState<HorarioOperacion | null>(null)
  const [noticeMessage, setNoticeMessage] = useState<string | null>(null)

  // Campañas especiales o 24h activas en la BD para el año consultado
  const specialSchedules = useMemo(() => {
    return horariosList.filter(
      h => h.activo && (h.es_continuo_24h || h.tipo_horario === 'extendido_24h' || (h.fecha_inicio && h.fecha_fin && h.tipo_horario !== 'regular'))
    )
  }, [horariosList])

  const isScheduleActiveInDateRange = (h: HorarioOperacion) => {
    if (!h.fecha_inicio || !h.fecha_fin || !dateRange?.inicio || !dateRange?.fin) {
      return true
    }
    const hStart = new Date(h.fecha_inicio.slice(0, 10)).getTime()
    const hEnd = new Date(h.fecha_fin.slice(0, 10)).getTime()
    const rStart = new Date(dateRange.inicio.slice(0, 10)).getTime()
    const rEnd = new Date(dateRange.fin.slice(0, 10)).getTime()
    return !(rEnd < hStart || rStart > hEnd)
  }

  const formatIsoDate = (dStr?: string | null) => {
    if (!dStr) return ''
    try {
      const [y, m, d] = dStr.slice(0, 10).split('-')
      return `${d}/${m}/${y}`
    } catch {
      return dStr
    }
  }

  const getNombreCampaña = (h: HorarioOperacion) => {
    if (h.descripcion) {
      return h.descripcion.replace(/^(Sala \d+ [^—–-]+ [—–-] )/i, '')
    }
    return 'Campaña 24 Horas'
  }

  // Presets inteligentes al cambiar el alcance superior
  const handleScopeChange = (newScope: DataScope) => {
    if (onChange) onChange(newScope)
    if (!onChangeFilters) return

    if (newScope === 'conformes') {
      // 1. Detectar si en el período consultado hay fechas de campaña 24h activas
      const active24h = specialSchedules.filter(
        h => (h.es_continuo_24h || h.tipo_horario === 'extendido_24h') && isScheduleActiveInDateRange(h)
      )

      // Si hay fechas de 24h en el rango consultado, marcar el filtro 24h junto al horario oficial
      // para habilitar el uso y análisis del período de horario nocturno y dominical 24h conforme
      const defaultRegimen = active24h.length > 0
        ? ['dentro_horario', ...active24h.map(h => `horario_${h.id}_delta`), '24h_delta'].join(',')
        : 'dentro_horario'

      onChangeFilters({
        alcance: 'conformes',
        regimen_horario: defaultRegimen,
        direccion: modulo === 'biblioteca' ? 'completos' : 'todos',
        dias_semana: '',
        door: '',
        perfil_visita: 'todos',
        marcajes: 'todos',
        sala: '',
        carrera: '',
        facultad: '',
        cohorte: '',
        incluir_pausas_bano: true,
        desduplicar_rafagas: true,
      })
    } else if (newScope === 'anomalias') {
      onChangeFilters({
        alcance: 'anomalias',
        regimen_horario: 'fuera_horario,dias_cierre',
        direccion: modulo === 'biblioteca' ? 'solo_ingreso,solo_salida' : 'todos',
        dias_semana: '',
        door: '',
        perfil_visita: 'todos',
        marcajes: '5+',
        sala: '',
        carrera: '',
        facultad: '',
        cohorte: '',
        incluir_pausas_bano: false,
        desduplicar_rafagas: false,
      })
    } else {
      // 'todos': universo físico completo sin restricciones
      onChangeFilters({
        alcance: 'todos',
        regimen_horario: 'todos',
        direccion: 'todos',
        dias_semana: '',
        door: '',
        perfil_visita: 'todos',
        marcajes: 'todos',
        sala: '',
        carrera: '',
        facultad: '',
        cohorte: '',
        incluir_pausas_bano: true,
        desduplicar_rafagas: true,
      })
    }
  }

  // Modificación reactiva individual de filtros manteniendo coherencia
  const updateFilter = <K extends keyof DataFilters>(key: K, val: DataFilters[K]) => {
    if (onChangeFilters) {
      const nextFilters: DataFilters = {
        ...filters,
        [key]: val,
      }

      // Si el usuario modifica manualmente dirección o régimen mientras estaba en conformes,
      // conmutamos alcance a 'todos' para que los registros solicitados (ej. sin salida o nocturnos) no sean excluidos
      if (currentScope === 'conformes') {
        if (key === 'direccion' && val !== 'completos' && val !== 'todos') {
          nextFilters.alcance = 'todos'
        }
        if (
          key === 'regimen_horario' &&
          typeof val === 'string' &&
          (val.includes('fuera_horario') || val.includes('dias_cierre'))
        ) {
          nextFilters.alcance = 'todos'
        }
      }

      // Si estaba en anomalías y el usuario activa 'completos' o 'dentro_horario':
      if (currentScope === 'anomalias') {
        if (key === 'direccion' && typeof val === 'string' && val.includes('completos')) {
          nextFilters.alcance = 'todos'
        }
        if (key === 'regimen_horario' && typeof val === 'string' && (val.includes('dentro_horario') || val.includes('24h_total'))) {
          nextFilters.alcance = 'todos'
        }
      }

      onChangeFilters(nextFilters)
    }
  }

  // Sincronizar automáticamente el régimen conforme si el rango de fechas cambia mientras se está en Datos Conformes
  useEffect(() => {
    if (currentScope !== 'conformes' || !onChangeFilters) return
    const active24h = specialSchedules.filter(
      h => (h.es_continuo_24h || h.tipo_horario === 'extendido_24h') && isScheduleActiveInDateRange(h)
    )
    const expectedRegimen = active24h.length > 0
      ? ['dentro_horario', ...active24h.map(h => `horario_${h.id}_delta`), '24h_delta'].join(',')
      : 'dentro_horario'

    const esRegimenConformeActual =
      filters.regimen_horario === 'dentro_horario' ||
      (filters.regimen_horario?.includes('dentro_horario') && (filters.regimen_horario?.includes('24h_delta') || filters.regimen_horario?.includes('horario_')))

    if (esRegimenConformeActual && filters.regimen_horario !== expectedRegimen) {
      updateFilter('regimen_horario', expectedRegimen)
    }
  }, [dateRange?.inicio, dateRange?.fin, specialSchedules, currentScope])

  const allBaseRegimenes = ['dentro_horario', 'fuera_horario', 'dias_cierre', 'paro_federado', 'paro_carrera']
  const allSpecialRegimenes = useMemo(() => {
    return specialSchedules.flatMap(h => [
      `horario_${h.id}_delta`,
      `horario_${h.id}_total`,
      '24h_delta',
      '24h_total',
    ])
  }, [specialSchedules])
  const allRegimenes = [...allBaseRegimenes, ...allSpecialRegimenes]

  const selectedRegimenes =
    filters.regimen_horario && filters.regimen_horario !== 'todos'
      ? filters.regimen_horario.split(',').map(r => r.trim())
      : []

  const toggleRegimen = (regimenId: string, specialH?: HorarioOperacion) => {
    const inRange = specialH ? isScheduleActiveInDateRange(specialH) : true
    let isCurrentlyChecked = false

    if (specialH) {
      if (regimenId.endsWith('_delta')) {
        isCurrentlyChecked =
          selectedRegimenes.length === 0 ||
          selectedRegimenes.includes(regimenId) ||
          (inRange && (selectedRegimenes.includes('24h_delta') || selectedRegimenes.includes('24h')))
      } else if (regimenId.endsWith('_total')) {
        isCurrentlyChecked =
          selectedRegimenes.length === 0 ||
          selectedRegimenes.includes(regimenId) ||
          (inRange && (selectedRegimenes.includes('24h_total') || selectedRegimenes.includes('24h')))
      } else {
        isCurrentlyChecked = selectedRegimenes.length === 0 || selectedRegimenes.includes(regimenId)
      }
    } else {
      isCurrentlyChecked = selectedRegimenes.length === 0 || selectedRegimenes.includes(regimenId)
    }

    const willBeChecked = !isCurrentlyChecked

    if (specialH && willBeChecked) {
      if (!inRange) {
        setPendingScheduleModal(specialH)
        return
      }
    }

    let next: string[]
    if (selectedRegimenes.length === 0) {
      next = allRegimenes.filter(r => r !== regimenId && r !== '24h_delta' && r !== '24h_total')
    } else if (isCurrentlyChecked) {
      next = selectedRegimenes.filter(r => {
        if (r === regimenId) return false
        if (regimenId.endsWith('_delta') && r === '24h_delta') return false
        if (regimenId.endsWith('_total') && (r === '24h_total' || r === '24h')) return false
        return true
      })
    } else {
      next = [...selectedRegimenes, regimenId]
    }

    updateFilter(
      'regimen_horario',
      next.length === 0 || next.length === allRegimenes.length ? 'todos' : next.join(',')
    )
  }

  const handleConfirmSchedule = () => {
    if (!pendingScheduleModal) return
    const h = pendingScheduleModal
    const iniStr = h.fecha_inicio ? h.fecha_inicio.slice(0, 10) : ''
    const finStr = h.fecha_fin ? h.fecha_fin.slice(0, 10) : ''
    const labelCampaña = getNombreCampaña(h)

    const newRange: DateRange = {
      inicio: iniStr,
      fin: finStr,
      label: `${labelCampaña} (${formatIsoDate(iniStr)} - ${formatIsoDate(finStr)})`,
    }

    if (onRangeChange) {
      onRangeChange(newRange)
    }
    const targetFilter = `horario_${h.id}_delta`
    const next =
      selectedRegimenes.length === 0
        ? ['dentro_horario', targetFilter, '24h_delta']
        : selectedRegimenes.includes(targetFilter)
        ? selectedRegimenes
        : [...selectedRegimenes, targetFilter, '24h_delta']

    updateFilter('regimen_horario', next.join(','))
    setPendingScheduleModal(null)
    setNoticeMessage(`Período de consulta actualizado: ${newRange.label}`)
    setTimeout(() => setNoticeMessage(null), 6000)
  }

  // --- 2. Flujo / Dirección (Casillas Multi-Selección) ---
  const FLUJO_OPTIONS_BIBLIOTECA = [
    {
      id: 'completos',
      label: 'Visita regular',
      tag: 'Ciclo completo',
      ejemplo: 'Entró 09:00, Salió 11:00',
    },
    {
      id: 'solo_ingreso',
      label: 'Marcó solo al entrar',
      tag: 'Sin salida',
      ejemplo: 'Entró 10:00, no marcó al salir',
    },
    {
      id: 'solo_salida',
      label: 'Marcó solo al salir',
      tag: 'Sin entrada',
      ejemplo: 'No marcó entrada, salió 13:00',
    },
  ]

  const FLUJO_OPTIONS_ESTACIONAMIENTO = [
    {
      id: 'solo_ingreso',
      label: 'Solo Entradas',
      tag: 'Ingreso',
      ejemplo: 'Vehículos entrando al campus',
    },
    {
      id: 'solo_salida',
      label: 'Solo Salidas',
      tag: 'Salida',
      ejemplo: 'Vehículos saliendo del campus',
    },
  ]

  const flujoOptions = modulo === 'biblioteca' ? FLUJO_OPTIONS_BIBLIOTECA : FLUJO_OPTIONS_ESTACIONAMIENTO
  const allFlujos = flujoOptions.map(o => o.id)

  const selectedFlujos =
    filters.direccion && filters.direccion !== 'todos'
      ? filters.direccion.split(',').map(f => f.trim().toLowerCase())
      : []

  const toggleFlujo = (flujoId: string) => {
    let next: string[]
    if (selectedFlujos.length === 0) {
      // Si todos estaban activos ('todos'), al hacer clic se desmarca este flujo y los demás permanecen activos
      next = allFlujos.filter(f => f !== flujoId)
    } else if (selectedFlujos.includes(flujoId)) {
      next = selectedFlujos.filter(f => f !== flujoId)
    } else {
      next = [...selectedFlujos, flujoId]
    }
    updateFilter(
      'direccion',
      next.length === 0 || next.length === allFlujos.length ? 'todos' : next.join(',')
    )
  }

  // --- 3. Días de Semana (Casillas) ---
  const selectedDias = filters.dias_semana
    ? filters.dias_semana.split(',').map(d => d.trim().toLowerCase())
    : []

  const toggleDia = (diaId: string) => {
    let next: string[]
    if (selectedDias.length === 0) {
      next = DIAS_OPTIONS.map(d => d.id).filter(id => id !== diaId)
    } else if (selectedDias.includes(diaId)) {
      next = selectedDias.filter(d => d !== diaId)
    } else {
      next = [...selectedDias, diaId]
    }
    updateFilter('dias_semana', next.length === 0 || next.length === 7 ? '' : next.join(','))
  }

  const setDiasPreset = (preset: 'todos' | 'habiles' | 'finde') => {
    if (preset === 'todos') {
      updateFilter('dias_semana', '')
    } else if (preset === 'habiles') {
      updateFilter('dias_semana', 'lunes,martes,miercoles,jueves,viernes')
    } else if (preset === 'finde') {
      updateFilter('dias_semana', 'sabado,domingo')
    }
  }

  // Clave normalizada de sala activa ('sala_1' | 'sala_2' | null)
  const activeSalaKey = React.useMemo(() => {
    if (!filters.sala || filters.sala === 'todos') return null
    const s = filters.sala.toLowerCase()
    if (s.includes('csf02') || s.includes('sala_1') || s === '1') return 'sala_1'
    if (s.includes('csf04') || s.includes('sala_2') || s === '2') return 'sala_2'
    return null
  }, [filters.sala])

  // --- 4. Torniquetes / Puertas (Casillas) ---
  const allBibDoorsItems = React.useMemo(() => {
    const s1Items = [
      {
        id: '2202',
        salaKey: 'sala_1',
        salaNombre: 'Sala 1 (CSF02)',
        name: 'Torniquete Principal (Sala 1)',
        hardware: 'IN: 2202 / OUT: 2184',
        code: 'CSF02_320 CTRA IN 02 / OUT 02',
        tipo: 'Principal',
      },
      {
        id: '2177',
        salaKey: 'sala_1',
        salaNombre: 'Sala 1 (CSF02)',
        name: 'Acceso Discapacitados (Sala 1)',
        hardware: 'IN: 2177 / OUT: 2170',
        code: 'CSF02_320 CTRA IN 01 / OUT 01',
        tipo: 'Universal',
      },
    ]

    const s2Items = [
      {
        id: '2592',
        salaKey: 'sala_2',
        salaNombre: 'Sala 2 (CSF04 Pecera)',
        name: 'Acceso Principal (Sala 2 Pecera)',
        hardware: 'IN: 2592 / OUT: 2587',
        code: 'CSF04_110 IN 01 / OUT',
        tipo: 'Principal',
      },
      {
        id: '3411',
        salaKey: 'sala_2',
        salaNombre: 'Sala 2 (CSF04 Pecera)',
        name: 'Acceso Discapacitados (Sala 2)',
        hardware: 'IN: 3411 / OUT: 3416',
        code: 'CSF04_110 IN 02_Door_1 / OUT 02',
        tipo: 'Universal',
      },
    ]

    return [...s1Items, ...s2Items]
  }, [])

  const s1DoorIds = React.useMemo(() => ['2202', '2177'], [])
  const s2DoorIds = React.useMemo(() => ['2592', '3411'], [])

  const allBibDoors = React.useMemo(() => allBibDoorsItems.map(d => d.id), [allBibDoorsItems])
  const allVehDoors = React.useMemo(() => ['CSF_ACCESO_NORTE', 'CSF_ACCESO_SUR', 'CHS_ACCESO_PRINCIPAL'], [])
  const allDoors = modulo === 'biblioteca' ? allBibDoors : allVehDoors

  // Puertas permitidas según la sala activa
  const allowedDoors = React.useMemo(() => {
    if (modulo !== 'biblioteca') return allDoors
    if (activeSalaKey === 'sala_1') return s1DoorIds
    if (activeSalaKey === 'sala_2') return s2DoorIds
    return allBibDoors
  }, [modulo, activeSalaKey, allDoors, s1DoorIds, s2DoorIds, allBibDoors])

  // Puertas actualmente seleccionadas
  const selectedDoors = React.useMemo(() => {
    if (modulo !== 'biblioteca') {
      return filters.door && filters.door !== 'todos'
        ? filters.door.split(',').map(d => d.trim().toLowerCase())
        : []
    }

    if (!filters.door || filters.door === 'todos') {
      return allowedDoors
    }

    const current = filters.door.split(',').map(d => d.trim().toLowerCase())
    if (activeSalaKey) {
      const valid = current.filter(d => allowedDoors.includes(d))
      return valid.length > 0 ? valid : allowedDoors
    }
    return current
  }, [modulo, filters.door, activeSalaKey, allowedDoors])

  const toggleDoor = (doorId: string) => {
    if (modulo === 'biblioteca' && activeSalaKey) {
      const item = allBibDoorsItems.find(d => d.id === doorId)
      if (item && item.salaKey !== activeSalaKey) return
    }

    let next: string[]
    if (selectedDoors.includes(doorId)) {
      next = selectedDoors.filter(d => d !== doorId)
    } else {
      next = [...selectedDoors, doorId]
    }

    if (next.length === 0) {
      next = allowedDoors
    }

    const isAll = next.length === allowedDoors.length && !activeSalaKey
    updateFilter('door', isAll ? '' : next.join(','))
  }

  const handleSelectSala = (salaCodigo: string) => {
    if (!onChangeFilters) return

    if (!salaCodigo || salaCodigo === 'todos') {
      onChangeFilters({
        ...filters,
        sala: '',
        door: '',
      })
      return
    }

    const sLow = salaCodigo.toLowerCase()
    const esSala1 = sLow.includes('csf02') || sLow.includes('sala_1') || sLow === '1'
    const esSala2 = sLow.includes('csf04') || sLow.includes('sala_2') || sLow === '2'

    const yaSeleccionada = Boolean(
      filters.sala && (
        (esSala1 && (filters.sala.toLowerCase().includes('csf02') || filters.sala.toLowerCase().includes('sala_1') || filters.sala === '1')) ||
        (esSala2 && (filters.sala.toLowerCase().includes('csf04') || filters.sala.toLowerCase().includes('sala_2') || filters.sala === '2'))
      )
    )

    if (yaSeleccionada) {
      onChangeFilters({
        ...filters,
        sala: '',
        door: '',
      })
    } else if (esSala1) {
      onChangeFilters({
        ...filters,
        sala: salaCodigo,
        door: '2202,2177',
      })
    } else if (esSala2) {
      onChangeFilters({
        ...filters,
        sala: salaCodigo,
        door: '2592,3411',
      })
    } else {
      onChangeFilters({
        ...filters,
        sala: salaCodigo,
        door: '',
      })
    }
  }

  // --- 5. Marcajes por Día (Casillas) ---
  const allMarcajes = ['1', '2', '3-4', '5+']
  const selectedMarcajes = filters.marcajes && filters.marcajes !== 'todos'
    ? filters.marcajes.split(',').map(m => m.trim())
    : []

  const toggleMarcaje = (mId: string) => {
    let next: string[]
    if (selectedMarcajes.length === 0) {
      next = allMarcajes.filter(m => m !== mId)
    } else if (selectedMarcajes.includes(mId)) {
      next = selectedMarcajes.filter(m => m !== mId)
    } else {
      next = [...selectedMarcajes, mId]
    }
    updateFilter('marcajes', next.length === 0 || next.length === allMarcajes.length ? 'todos' : next.join(','))
  }

  // --- 6. Perfil de Visita (Casillas) ---
  const allPerfiles = ['rebote', 'estandar', 'profundo']
  const selectedPerfiles = filters.perfil_visita && filters.perfil_visita !== 'todos'
    ? filters.perfil_visita.split(',').map(p => p.trim())
    : []

  const togglePerfil = (pId: string) => {
    let next: string[]
    if (selectedPerfiles.length === 0) {
      next = allPerfiles.filter(p => p !== pId)
    } else if (selectedPerfiles.includes(pId)) {
      next = selectedPerfiles.filter(p => p !== pId)
    } else {
      next = [...selectedPerfiles, pId]
    }
    updateFilter('perfil_visita', next.length === 0 || next.length === allPerfiles.length ? 'todos' : next.join(','))
  }

  // Contar filtros activos distintos del valor por defecto
  const activeCustomFiltersCount = [
    filters.regimen_horario && filters.regimen_horario !== 'todos',
    filters.direccion && filters.direccion !== 'todos',
    filters.dias_semana && filters.dias_semana !== '',
    filters.door && filters.door !== '' && filters.door !== 'todos',
    filters.perfil_visita && filters.perfil_visita !== 'todos',
    filters.marcajes && filters.marcajes !== 'todos',
    filters.sala && filters.sala !== '' && filters.sala !== 'todos',
    filters.facultad && filters.facultad !== '' && filters.facultad !== 'todos',
    filters.carrera && filters.carrera !== '' && filters.carrera !== 'todos',
    modulo === 'biblioteca' && filters.incluir_pausas_bano === false,
    modulo === 'biblioteca' && filters.desduplicar_rafagas === false,
  ].filter(Boolean).length

  // Estados de coincidencia exacta con los presets estándar
  const isConformesPreset =
    currentScope === 'conformes' &&
    (filters.regimen_horario === 'dentro_horario' ||
      (filters.regimen_horario?.includes('dentro_horario') &&
       (filters.regimen_horario?.includes('24h_delta') || filters.regimen_horario?.includes('horario_')))) &&
    (modulo === 'biblioteca' ? filters.direccion === 'completos' : (filters.direccion === 'todos' || !filters.direccion)) &&
    (filters.marcajes === 'todos' || filters.marcajes === '1,2,3-4' || !filters.marcajes) &&
    filters.incluir_pausas_bano !== false &&
    filters.desduplicar_rafagas !== false &&
    !filters.dias_semana &&
    !filters.door &&
    !filters.sala &&
    !filters.facultad &&
    !filters.carrera

  const isAnomaliasPreset =
    currentScope === 'anomalias' &&
    (filters.regimen_horario === 'fuera_horario' || filters.regimen_horario === 'fuera_horario,dias_cierre') &&
    (modulo === 'biblioteca' ? filters.direccion === 'solo_ingreso,solo_salida' : (filters.direccion === 'todos' || !filters.direccion)) &&
    filters.marcajes === '5+' &&
    !filters.dias_semana &&
    !filters.door &&
    !filters.sala &&
    !filters.facultad &&
    !filters.carrera

  const isTodosPreset =
    currentScope === 'todos' &&
    (filters.regimen_horario === 'todos' || !filters.regimen_horario) &&
    (filters.direccion === 'todos' || !filters.direccion) &&
    (filters.marcajes === 'todos' || !filters.marcajes) &&
    !filters.dias_semana &&
    !filters.door &&
    !filters.sala &&
    !filters.facultad &&
    !filters.carrera

  const isCustomized = !isConformesPreset && !isAnomaliasPreset && !isTodosPreset

  const [panelFiltrosAbierto, setPanelFiltrosAbierto] = useState<boolean>(true)

  const alternarPanelFiltros = () => {
    setPanelFiltrosAbierto(prev => !prev)
  }

  const resumenFiltrosActivos = React.useMemo(() => {
    const chips: { clave: string; etiqueta: string; valor: string }[] = []

    if (filters.facultad) {
      chips.push({ clave: 'facultad', etiqueta: 'Facultad', valor: filters.facultad })
    }
    if (filters.carrera) {
      chips.push({ clave: 'carrera', etiqueta: 'Carrera', valor: filters.carrera })
    }
    if (filters.cohorte) {
      chips.push({ clave: 'cohorte', etiqueta: 'Cohorte', valor: String(filters.cohorte) })
    }

    const textoHorario =
      selectedRegimenes.length === 0
        ? 'Todos'
        : selectedRegimenes.length === 1 && selectedRegimenes[0] === 'dentro_horario'
        ? 'Oficial'
        : `${selectedRegimenes.length} activos`
    chips.push({ clave: 'horario', etiqueta: 'Horario', valor: textoHorario })

    const textoFlujo =
      selectedFlujos.length === 0
        ? 'Todos'
        : selectedFlujos.length === 1 && selectedFlujos[0] === 'completos'
        ? 'Visita regular'
        : `${selectedFlujos.length} activos`
    chips.push({ clave: 'flujo', etiqueta: 'Flujo', valor: textoFlujo })

    const textoDias =
      selectedDias.length === 0
        ? 'Lun–Dom'
        : selectedDias.length === 5 && !selectedDias.includes('sabado') && !selectedDias.includes('domingo')
        ? 'Lun–Vie'
        : selectedDias.length === 2 && selectedDias.includes('sabado') && selectedDias.includes('domingo')
        ? 'Finde'
        : `${selectedDias.length} días`
    chips.push({ clave: 'dias', etiqueta: 'Días', valor: textoDias })

    const textoMarcajes =
      selectedMarcajes.length === 0 ? 'Todos' : `${selectedMarcajes.join(', ')}`
    chips.push({ clave: 'marcajes', etiqueta: 'Marcajes', valor: textoMarcajes })

    const textoPerfil =
      selectedPerfiles.length === 0 ? 'Todos' : `${selectedPerfiles.length} activos`
    chips.push({ clave: 'perfil', etiqueta: 'Perfil', valor: textoPerfil })

    return chips
  }, [
    filters.facultad,
    filters.carrera,
    filters.cohorte,
    selectedRegimenes,
    selectedFlujos,
    selectedDias,
    selectedMarcajes,
    selectedPerfiles,
  ])

  const handleResetFilters = () => {
    handleScopeChange('conformes')
  }

  return (
    <div className="w-full space-y-3">
      {/* Barra Principal de Selección y Controles */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 bg-white p-2.5 px-3.5 rounded-2xl border border-slate-200/90 shadow-2xs">
        {/* Botones de Alcance Base y Conteo de Registros Seleccionados */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex flex-wrap items-center gap-1.5 bg-slate-100/90 p-1 rounded-xl border border-slate-200">
            <button
              type="button"
              onClick={() => handleScopeChange('conformes')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                currentScope === 'conformes'
                  ? 'bg-white text-emerald-800 shadow-xs border border-emerald-200 font-bold'
                  : 'text-slate-600 hover:text-slate-900 border border-transparent'
              }`}
              title="Aplica el preset de calidad oficial: Horario Oficial + Visitas completas + Marcajes < 5"
            >
              <ShieldCheck size={14} className={currentScope === 'conformes' ? 'text-emerald-600' : 'text-slate-400'} />
              <span>Datos Conformes</span>
            </button>

            <button
              type="button"
              onClick={() => handleScopeChange('todos')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                currentScope === 'todos'
                  ? 'bg-white text-uct-blue-primary shadow-xs border border-blue-200 font-bold'
                  : 'text-slate-600 hover:text-slate-900 border border-transparent'
              }`}
              title="Aplica el preset del universo físico completo (100% registros)"
            >
              <Database size={14} className={currentScope === 'todos' ? 'text-uct-blue-primary' : 'text-slate-400'} />
              <span>Todos los Registros</span>
            </button>

            <button
              type="button"
              onClick={() => handleScopeChange('anomalias')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                currentScope === 'anomalias'
                  ? 'bg-white text-amber-800 shadow-xs border border-amber-300 font-bold'
                  : 'text-slate-600 hover:text-slate-900 border border-transparent'
              }`}
              title="Aplica el preset de auditoría de fallas: Sin salida/entrada + Fuera de horario + Marcaje 5+"
            >
              <AlertTriangle size={14} className={currentScope === 'anomalias' ? 'text-amber-600' : 'text-slate-400'} />
              <span>Solo Anomalías</span>
            </button>
          </div>

          {/* Cantidad de datos seleccionados con los filtros aplicados */}
          {totalCount !== undefined && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-700 shadow-2xs">
              <span className="text-slate-500 font-medium">Registros seleccionados:</span>
              <span className="font-bold text-uct-blue-primary font-mono bg-blue-50/80 px-2 py-0.5 rounded-md border border-blue-100">
                {totalCount.toLocaleString('es-CL')}
              </span>
            </div>
          )}

          {isCustomized && (
            <span
              className="text-[10px] text-blue-700 bg-blue-50 px-2.5 py-1 rounded-xl border border-blue-200/80 font-semibold shadow-2xs"
              title="Has modificado manualmente opciones respecto al preset predeterminado"
            >
              Filtros adaptados
            </span>
          )}
        </div>

        {/* Acciones del Extremo Derecho: Limpiar Filtros, Exportación/Visibilidad y Botón Ocultar/Mostrar Filtros */}
        <div className="flex flex-wrap items-center gap-2">
          {activeCustomFiltersCount > 0 && (
            <button
              type="button"
              onClick={handleResetFilters}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-rose-600 hover:text-rose-700 bg-rose-50/70 hover:bg-rose-100/70 border border-rose-200 transition cursor-pointer rounded-xl font-medium"
              title="Restablecer filtros a valores predeterminados"
            >
              <RotateCcw size={12} />
              <span>Limpiar filtros ({activeCustomFiltersCount})</span>
            </button>
          )}

          {actionRight}

          <button
            type="button"
            onClick={alternarPanelFiltros}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer shadow-2xs ${
              panelFiltrosAbierto
                ? 'bg-slate-100 hover:bg-slate-200/80 text-slate-700 border-slate-300'
                : 'bg-uct-blue-primary hover:bg-uct-blue-secondary text-white border-uct-blue-primary'
            }`}
            title={panelFiltrosAbierto ? 'Ocultar el panel de filtros para ampliar el área de gráficos' : 'Mostrar todos los filtros avanzados'}
          >
            <SlidersHorizontal size={13} />
            <span>{panelFiltrosAbierto ? 'Ocultar Filtros' : 'Mostrar Filtros'}</span>
            {panelFiltrosAbierto ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {/* Vista Compacta de Resumen (cuando panelFiltrosAbierto === false) */}
      {!panelFiltrosAbierto && (
        <div className="flex flex-wrap items-center justify-between gap-2.5 px-3.5 py-2 bg-white/95 rounded-xl border border-slate-200/90 shadow-2xs text-xs">
          <div className="flex flex-wrap items-center gap-2">
            {modulo === 'biblioteca' && (
              <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200">
                <button
                  type="button"
                  onClick={() => handleSelectSala('')}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition cursor-pointer ${
                    !filters.sala || filters.sala === 'todos'
                      ? 'bg-uct-blue-primary text-white shadow-2xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Todas las Salas (350)
                </button>
                {salasBiblioteca.map((s, idx) => {
                  const isSelected = Boolean(
                    filters.sala && (
                      filters.sala === s.codigo ||
                      filters.sala === String(s.id) ||
                      (s.codigo?.includes('CSF02') && (filters.sala.toLowerCase().includes('csf02') || filters.sala.toLowerCase().includes('sala_1') || filters.sala === '1')) ||
                      (s.codigo?.includes('CSF04') && (filters.sala.toLowerCase().includes('csf04') || filters.sala.toLowerCase().includes('sala_2') || filters.sala === '2'))
                    )
                  )
                  const etiquetaCorta = s.codigo?.includes('CSF02')
                    ? `Sala 1 (${s.capacidad_asientos})`
                    : s.codigo?.includes('CSF04')
                    ? `Sala 2 Pecera (${s.capacidad_asientos})`
                    : `Sala ${idx + 1} (${s.capacidad_asientos})`
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => handleSelectSala(s.codigo)}
                      className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition cursor-pointer ${
                        isSelected
                          ? 'bg-uct-blue-primary text-white shadow-2xs'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      {etiquetaCorta}
                    </button>
                  )
                })}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-1.5">
              {resumenFiltrosActivos.map(chip => (
                <span
                  key={chip.clave}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-slate-50 border border-slate-200 text-[11px] text-slate-600"
                >
                  <span className="font-semibold text-slate-500">{chip.etiqueta}:</span>
                  <span className="font-bold text-slate-800">{chip.valor}</span>
                </span>
              ))}
            </div>
          </div>

          <button
            type="button"
            onClick={alternarPanelFiltros}
            className="text-[11px] font-semibold text-uct-blue-primary hover:underline flex items-center gap-1 cursor-pointer shrink-0"
          >
            <span>Desplegar filtros</span>
            <ChevronDown size={13} />
          </button>
        </div>
      )}

      {/* Cuerpo Desplegable Completo (cuando panelFiltrosAbierto === true) */}
      {panelFiltrosAbierto && (
        <div className="space-y-3">
          {/* Selector de Salas Dinámicas y Filtros Curriculares (Ley 21.719) */}
          {modulo === 'biblioteca' && (
            <div className="p-4 bg-gradient-to-r from-slate-50 via-white to-blue-50/40 rounded-2xl border border-slate-200/90 shadow-2xs space-y-3.5">
              <div className="flex flex-wrap items-center justify-between gap-2.5">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-uct-blue-primary/10 flex items-center justify-center text-uct-blue-primary">
                    <Building2 size={15} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-800">
                        Distribución por Sala Física (Campus San Francisco)
                      </span>
                      <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-semibold border border-slate-200">
                        {salasBiblioteca.length > 0 ? `${salasBiblioteca.length} salas registradas` : '2 salas'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 text-[11px] text-emerald-800 bg-emerald-50/90 px-2.5 py-1 rounded-xl border border-emerald-200">
                  <ShieldCheck size={14} className="text-emerald-600 shrink-0" />
                  <span className="font-semibold">Ley 21.719:</span>
                  <span className="text-emerald-700">Métricas disociadas y anonimizadas</span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {/* Botón: Todas las Salas */}
                {(() => {
                  const activoGlobal = !filters.sala || filters.sala === 'todos'
                  return (
                    <button
                      type="button"
                      onClick={() => handleSelectSala('')}
                      className={`p-3 rounded-xl border text-left transition cursor-pointer flex flex-col justify-between gap-2 ${
                        activoGlobal
                          ? 'bg-uct-blue-primary text-white border-uct-blue-primary shadow-sm'
                          : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200/90 shadow-2xs'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-bold">Todas las Salas</span>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                          activoGlobal ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600'
                        }`}>
                          Global • 350 asientos
                        </span>
                      </div>
                      <div className="space-y-1">
                        <div className={`text-[10.5px] flex items-center justify-between ${
                          activoGlobal ? 'text-blue-100' : 'text-slate-500'
                        }`}>
                          <span>Capacidad agregada campus</span>
                          <span className="font-mono font-semibold">100%</span>
                        </div>
                        <div className={`w-full h-1.5 rounded-full overflow-hidden ${
                          activoGlobal ? 'bg-white/20' : 'bg-slate-100'
                        }`}>
                          <div
                            className={`h-full rounded-full ${activoGlobal ? 'bg-uct-gold-accent' : 'bg-uct-blue-primary'}`}
                            style={{ width: '100%' }}
                          />
                        </div>
                      </div>
                    </button>
                  )
                })()}

                {/* Salas dinámicas desde base de datos */}
                {salasBiblioteca.map((s) => {
                  const isSelected = Boolean(
                    filters.sala && (
                      filters.sala === s.codigo ||
                      filters.sala === String(s.id) ||
                      (s.codigo?.includes('CSF02') && (filters.sala.toLowerCase().includes('csf02') || filters.sala.toLowerCase().includes('sala_1') || filters.sala === '1')) ||
                      (s.codigo?.includes('CSF04') && (filters.sala.toLowerCase().includes('csf04') || filters.sala.toLowerCase().includes('sala_2') || filters.sala === '2'))
                    )
                  )
                  const porcentajeCapacidad = Math.min(100, Math.round(((s.capacidad_asientos || 125) / 350) * 100))
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => handleSelectSala(s.codigo)}
                      className={`p-3 rounded-xl border text-left transition cursor-pointer flex flex-col justify-between gap-2 ${
                        isSelected
                          ? 'bg-uct-blue-primary text-white border-uct-blue-primary shadow-sm'
                          : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200/90 shadow-2xs'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1.5">
                        <span className="text-xs font-bold truncate">{s.nombre}</span>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full shrink-0 font-semibold ${
                          isSelected ? 'bg-white/20 text-white' : 'bg-blue-50 text-uct-blue-primary'
                        }`}>
                          {s.capacidad_asientos} asientos
                        </span>
                      </div>
                      <div className="space-y-1">
                        <div className={`text-[10.5px] flex items-center justify-between gap-1 ${
                          isSelected ? 'text-blue-100' : 'text-slate-500'
                        }`}>
                          <span className="truncate">{s.piso}</span>
                          {(s.permite_horario_extendido || s.horario_extendido_examenes) ? (
                            <span className={`text-[9px] px-1.5 py-0.2 rounded font-semibold ${
                              isSelected ? 'bg-amber-400/30 text-amber-100' : 'bg-amber-100 text-amber-800'
                            }`}>
                              Exámenes 24h
                            </span>
                          ) : (
                            <span className="font-mono text-[10px]">{porcentajeCapacidad}% cap.</span>
                          )}
                        </div>
                        <div className={`w-full h-1.5 rounded-full overflow-hidden ${
                          isSelected ? 'bg-white/20' : 'bg-slate-100'
                        }`}>
                          <div
                            className={`h-full rounded-full ${isSelected ? 'bg-uct-gold-accent' : 'bg-uct-blue-primary/80'}`}
                            style={{ width: `${porcentajeCapacidad}%` }}
                          />
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>

          {/* Filtros Curriculares: Facultad, Carrera y Cohorte */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 border-t border-slate-200/80">
            {/* Selector de Facultad */}
            <div className="flex items-center gap-2 bg-white px-3 py-2 rounded-xl border border-slate-200">
              <School size={15} className="text-uct-blue-primary shrink-0" />
              <div className="flex-1 min-w-0">
                <label className="block text-[9.5px] text-slate-400 font-medium">Filtrar por Facultad</label>
                <select
                  value={filters.facultad || ''}
                  onChange={(e) => updateFilter('facultad', e.target.value)}
                  className="w-full text-xs font-semibold text-slate-800 bg-transparent border-none focus:outline-none focus:ring-0 p-0 cursor-pointer"
                >
                  <option value="">Todas las Facultades</option>
                  {(availableFilters?.facultades || []).map((fac) => (
                    <option key={fac} value={fac}>{fac}</option>
                  ))}
                </select>
              </div>
              {filters.facultad && (
                <button
                  type="button"
                  onClick={() => updateFilter('facultad', '')}
                  className="text-slate-400 hover:text-slate-600 p-1"
                  title="Quitar filtro de facultad"
                >
                  <X size={12} />
                </button>
              )}
            </div>

            {/* Selector de Carrera */}
            <div className="flex items-center gap-2 bg-white px-3 py-2 rounded-xl border border-slate-200">
              <GraduationCap size={15} className="text-uct-blue-primary shrink-0" />
              <div className="flex-1 min-w-0">
                <label className="block text-[9.5px] text-slate-400 font-medium">Filtrar por Carrera</label>
                <select
                  value={filters.carrera || ''}
                  onChange={(e) => updateFilter('carrera', e.target.value)}
                  className="w-full text-xs font-semibold text-slate-800 bg-transparent border-none focus:outline-none focus:ring-0 p-0 cursor-pointer"
                >
                  <option value="">Todas las Carreras</option>
                  {(availableFilters?.carreras || []).map((carr) => (
                    <option key={carr} value={carr}>{carr}</option>
                  ))}
                </select>
              </div>
              {filters.carrera && (
                <button
                  type="button"
                  onClick={() => updateFilter('carrera', '')}
                  className="text-slate-400 hover:text-slate-600 p-1"
                  title="Quitar filtro de carrera"
                >
                  <X size={12} />
                </button>
              )}
            </div>

            {/* Selector de Cohorte / Año de Ingreso */}
            <div className="flex items-center gap-2 bg-white px-3 py-2 rounded-xl border border-slate-200">
              <Calendar size={15} className="text-uct-blue-primary shrink-0" />
              <div className="flex-1 min-w-0">
                <label className="block text-[9.5px] text-slate-400 font-medium">Cohorte / Año Ingreso</label>
                <select
                  value={filters.cohorte || ''}
                  onChange={(e) => updateFilter('cohorte', e.target.value)}
                  className="w-full text-xs font-semibold text-slate-800 bg-transparent border-none focus:outline-none focus:ring-0 p-0 cursor-pointer"
                >
                  <option value="">Todas las Cohortes</option>
                  {(availableFilters?.cohortes || [2026, 2025, 2024, 2023, 2022, 2021, 2020]).map((coh) => (
                    <option key={coh} value={coh}>
                      {`Cohorte ${coh}` + (coh === 2026 ? ' (Novatos)' : '')}
                    </option>
                  ))}
                </select>
              </div>
              {filters.cohorte && (
                <button
                  type="button"
                  onClick={() => updateFilter('cohorte', '')}
                  className="text-slate-400 hover:text-slate-600 p-1"
                  title="Quitar filtro de cohorte"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Sección de Filtros a la Vista FIJA (Siempre visible) */}
      <div className="p-3.5 bg-slate-50/90 rounded-2xl border border-slate-200/90 shadow-2xs grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3 text-xs">
        
        {/* 1. Régimen de Horario Dinámico con Casillas Multi-Selección */}
        <div className="space-y-2 bg-white p-3 rounded-xl border border-slate-200/70 shadow-2xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between font-bold text-slate-700 mb-2">
              <div className="flex items-center gap-1.5">
                <Clock size={14} className="text-uct-blue-primary" />
                <span>Régimen Horario</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-slate-400 font-normal">
                  {selectedRegimenes.length === 0 ? 'Todos' : `${selectedRegimenes.length} activos`}
                </span>
                {selectedRegimenes.length > 0 && (
                  <button
                    type="button"
                    onClick={() => updateFilter('regimen_horario', 'todos')}
                    className="text-[9px] text-uct-blue-primary hover:underline cursor-pointer font-medium"
                    title="Restablecer a todos los horarios"
                  >
                    Todos
                  </button>
                )}
              </div>
            </div>

            <div className="space-y-1">
              {/* Opción 1: Horario Oficial */}
              {(() => {
                const isChecked = selectedRegimenes.length === 0 || selectedRegimenes.includes('dentro_horario')
                return (
                  <label
                    className={`flex items-start gap-1.5 p-1 rounded-md cursor-pointer transition select-none border ${
                      isChecked
                        ? 'bg-emerald-50/80 border-emerald-400/50 text-emerald-800 font-semibold shadow-2xs'
                        : 'bg-white/70 border-slate-200/60 hover:bg-slate-100 text-slate-700 opacity-70'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleRegimen('dentro_horario')}
                      className="mt-0.5 text-emerald-600 focus:ring-emerald-500 h-3.5 w-3.5 rounded border-slate-300 cursor-pointer shrink-0"
                    />
                    <div className="min-w-0 flex-1 leading-tight">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[10.5px] font-medium truncate">Horario Oficial</span>
                        <span
                          className={`text-[8.5px] px-1 py-0.2 rounded font-mono shrink-0 ${
                            isChecked
                              ? 'bg-emerald-600 text-white font-bold'
                              : 'bg-slate-100 text-slate-500'
                          }`}
                        >
                          Oficial
                        </span>
                      </div>
                      <div className="text-[9px] text-slate-400 font-normal truncate">
                        {modulo === 'biblioteca' ? 'Lun-Jue 08:30-20:30, Vie 19:30, Sáb 13:30 (Todo el año)' : 'Lun-Vie 07:00-22:00, Sáb 08:00-14:00'}
                      </div>
                    </div>
                  </label>
                )
              })()}

              {/* Períodos Especiales Dinámicos Activos en el Rango Consultado */}
              {specialSchedules
                .filter((h) => isScheduleActiveInDateRange(h))
                .flatMap((h) => {
                  const inRange = true
                  const items = []
                  const etiquetaPeriodo = h.descripcion
                    ? h.descripcion.replace(/Sala \d+ [^—–-]+ [—–-] /i, '').replace(/Campaña 24 Horas\s*[-—–]?\s*/i, '').trim()
                    : `${formatIsoDate(h.fecha_inicio)} - ${formatIsoDate(h.fecha_fin)}`

                  if (h.es_continuo_24h) {
                    // Opción A: Solo Extensión Nocturna / Delta (24h menos oficial)
                    const deltaKey = `horario_${h.id}_delta`
                    const isCheckedDelta =
                      selectedRegimenes.length === 0 ||
                      selectedRegimenes.includes(deltaKey) ||
                      selectedRegimenes.includes('24h_delta') ||
                      selectedRegimenes.includes('24h')

                    items.push(
                      <label
                        key={`${h.id}-delta`}
                        className={`flex items-start gap-1.5 p-1 rounded-md cursor-pointer transition select-none border ${
                          isCheckedDelta
                            ? 'bg-indigo-50/90 border-indigo-400/60 text-indigo-950 font-semibold shadow-2xs'
                            : 'bg-white/80 border-slate-200/60 hover:bg-slate-100 text-slate-700 opacity-70'
                        }`}
                        title={`Extensión nocturna (${etiquetaPeriodo}): 20:30 a 08:30 y domingos (${formatIsoDate(h.fecha_inicio)} al ${formatIsoDate(h.fecha_fin)})`}
                      >
                        <input
                          type="checkbox"
                          checked={isCheckedDelta}
                          onChange={() => toggleRegimen(deltaKey, h)}
                          className="mt-0.5 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5 rounded border-slate-300 cursor-pointer shrink-0"
                        />
                        <div className="min-w-0 flex-1 leading-tight">
                          <div className="flex items-center justify-between gap-1">
                            <span className="text-[10.5px] font-medium truncate" title={`Extensión Nocturna (${etiquetaPeriodo})`}>
                              Extensión Nocturna ({etiquetaPeriodo})
                            </span>
                            <span
                              className={`text-[8.5px] px-1 py-0.2 rounded font-mono shrink-0 ${
                                isCheckedDelta
                                  ? 'bg-indigo-600 text-white font-bold'
                                  : 'bg-indigo-100 text-indigo-700'
                              }`}
                            >
                              Delta 24h
                            </span>
                          </div>
                          <div className="text-[9px] text-slate-400 font-normal truncate mt-0.5">
                            Noches 20:30-08:30 y domingos ({formatIsoDate(h.fecha_inicio)} al {formatIsoDate(h.fecha_fin)})
                          </div>
                        </div>
                      </label>
                    )

                    // Opción B: Régimen 24 Horas Total
                    const totalKey = `horario_${h.id}_total`
                    const isCheckedTotal =
                      selectedRegimenes.length === 0 ||
                      selectedRegimenes.includes(totalKey) ||
                      selectedRegimenes.includes('24h_total') ||
                      selectedRegimenes.includes('24h')

                    items.push(
                      <label
                        key={`${h.id}-total`}
                        className={`flex items-start gap-1.5 p-1 rounded-md cursor-pointer transition select-none border ${
                          isCheckedTotal
                            ? 'bg-purple-50/90 border-purple-400/60 text-purple-950 font-semibold shadow-2xs'
                            : 'bg-white/80 border-slate-200/60 hover:bg-slate-100 text-slate-700 opacity-70'
                        }`}
                        title={`Campaña 24 Horas completa (diurno + nocturno): ${formatIsoDate(h.fecha_inicio)} al ${formatIsoDate(h.fecha_fin)}`}
                      >
                        <input
                          type="checkbox"
                          checked={isCheckedTotal}
                          onChange={() => toggleRegimen(totalKey, h)}
                          className="mt-0.5 text-purple-600 focus:ring-purple-500 h-3.5 w-3.5 rounded border-slate-300 cursor-pointer shrink-0"
                        />
                        <div className="min-w-0 flex-1 leading-tight">
                          <div className="flex items-center justify-between gap-1">
                            <span className="text-[10.5px] font-medium truncate" title={`Campaña 24h Total (${etiquetaPeriodo})`}>
                              Campaña 24h Total ({etiquetaPeriodo})
                            </span>
                            <span
                              className={`text-[8.5px] px-1 py-0.2 rounded font-mono shrink-0 ${
                                isCheckedTotal
                                  ? 'bg-purple-600 text-white font-bold'
                                  : 'bg-purple-100 text-purple-700'
                              }`}
                            >
                              24h Total
                            </span>
                          </div>
                          <div className="text-[9px] text-slate-400 font-normal truncate mt-0.5">
                            24 hrs continuas ({formatIsoDate(h.fecha_inicio)} al {formatIsoDate(h.fecha_fin)})
                          </div>
                        </div>
                      </label>
                    )
                  } else {
                  // Horarios Extendidos Especiales Parciales o Cambios Temporales por Sala
                  const deltaKey = `horario_${h.id}_delta`
                  const totalKey = `horario_${h.id}_total`
                  const isCheckedDelta = selectedRegimenes.length === 0 || selectedRegimenes.includes(deltaKey)
                  const isCheckedTotal = selectedRegimenes.length === 0 || selectedRegimenes.includes(totalKey)
                  const etiquetaSala =
                    h.subespacio === 'sala_1'
                      ? 'Sala 1'
                      : h.subespacio === 'sala_2'
                      ? 'Sala 2'
                      : h.subespacio && h.subespacio !== 'todos'
                      ? h.subespacio
                      : 'General'

                  if (h.tipo_horario !== 'historico_regular') {
                    items.push(
                      <label
                        key={`${h.id}-delta`}
                        onClick={(e) => {
                          if (!inRange && !isCheckedDelta) {
                            e.preventDefault()
                            toggleRegimen(deltaKey, h)
                          }
                        }}
                        className={`flex items-start gap-1.5 p-1 rounded-md cursor-pointer transition select-none border ${
                          isCheckedDelta
                            ? 'bg-indigo-50/90 border-indigo-400/60 text-indigo-950 font-semibold shadow-2xs'
                            : inRange
                            ? 'bg-white/80 border-slate-200/60 hover:bg-slate-100 text-slate-700 opacity-70'
                            : 'bg-slate-100/60 border-dashed border-slate-300/80 text-slate-500 hover:bg-slate-200/60'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isCheckedDelta}
                          onChange={() => toggleRegimen(deltaKey, h)}
                          className="mt-0.5 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5 rounded border-slate-300 cursor-pointer shrink-0"
                        />
                        <div className="min-w-0 flex-1 leading-tight">
                          <div className="flex items-center justify-between gap-1">
                            <span className="text-[10.5px] font-medium truncate">Extensión {h.descripcion}</span>
                            <span className="text-[8.5px] px-1 py-0.2 rounded font-mono bg-indigo-100 text-indigo-700 shrink-0">
                              {etiquetaSala} • Delta
                            </span>
                          </div>
                          <div className="text-[9px] text-slate-400 font-normal truncate">
                            Solo horas fuera de jornada habitual
                          </div>
                        </div>
                      </label>
                    )
                  }

                  items.push(
                    <label
                      key={`${h.id}-total`}
                      onClick={(e) => {
                        if (!inRange && !isCheckedTotal) {
                          e.preventDefault()
                          toggleRegimen(totalKey, h)
                        }
                      }}
                      className={`flex items-start gap-1.5 p-1 rounded-md cursor-pointer transition select-none border ${
                        isCheckedTotal
                          ? 'bg-purple-50/90 border-purple-400/60 text-purple-950 font-semibold shadow-2xs'
                          : inRange
                          ? 'bg-white/80 border-slate-200/60 hover:bg-slate-100 text-slate-700 opacity-70'
                          : 'bg-slate-100/60 border-dashed border-slate-300/80 text-slate-500 hover:bg-slate-200/60'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isCheckedTotal}
                        onChange={() => toggleRegimen(totalKey, h)}
                        className="mt-0.5 text-purple-600 focus:ring-purple-500 h-3.5 w-3.5 rounded border-slate-300 cursor-pointer shrink-0"
                      />
                      <div className="min-w-0 flex-1 leading-tight">
                        <div className="flex items-center justify-between gap-1">
                          <span className="text-[10.5px] font-medium truncate">{h.descripcion}</span>
                          <span className="text-[8.5px] px-1 py-0.2 rounded font-mono bg-purple-100 text-purple-700 shrink-0">
                            {etiquetaSala}
                          </span>
                        </div>
                        <div className="text-[9px] text-slate-400 font-normal truncate">
                          {h.hora_apertura} - {h.hora_cierre} ({formatIsoDate(h.fecha_inicio)} al {formatIsoDate(h.fecha_fin)})
                        </div>
                      </div>
                    </label>
                  )
                }

                return items
              })}

              {/* Opción 3: Fuera de Horario */}
              {(() => {
                const isChecked = selectedRegimenes.length === 0 || selectedRegimenes.includes('fuera_horario')
                return (
                  <label
                    className={`flex items-start gap-1.5 p-1 rounded-md cursor-pointer transition select-none border ${
                      isChecked
                        ? 'bg-amber-50/80 border-amber-400/50 text-amber-900 font-semibold shadow-2xs'
                        : 'bg-white/70 border-slate-200/60 hover:bg-slate-100 text-slate-700 opacity-70'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleRegimen('fuera_horario')}
                      className="mt-0.5 text-amber-600 focus:ring-amber-500 h-3.5 w-3.5 rounded border-slate-300 cursor-pointer shrink-0"
                    />
                    <div className="min-w-0 flex-1 leading-tight">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[10.5px] font-medium truncate">Fuera de Horario</span>
                        <span
                          className={`text-[8.5px] px-1 py-0.2 rounded font-mono shrink-0 ${
                            isChecked
                              ? 'bg-amber-600 text-white font-bold'
                              : 'bg-slate-100 text-slate-500'
                          }`}
                        >
                          Nocturno
                        </span>
                      </div>
                      <div className="text-[9px] text-slate-400 font-normal truncate">
                        Accesos con recinto cerrado
                      </div>
                    </div>
                  </label>
                )
              })()}

              {/* Opción 4: Días de Cierre y Feriados */}
              {(() => {
                const isChecked = selectedRegimenes.length === 0 || selectedRegimenes.includes('dias_cierre')
                return (
                  <label
                    className={`flex items-start gap-1.5 p-1 rounded-md cursor-pointer transition select-none border ${
                      isChecked
                        ? 'bg-rose-50/80 border-rose-400/50 text-rose-900 font-semibold shadow-2xs'
                        : 'bg-white/70 border-slate-200/60 hover:bg-slate-100 text-slate-700 opacity-70'
                    }`}
                    title="Accesos registrados en días festivos, recesos académicos o suspensiones del calendario oficial UCT"
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleRegimen('dias_cierre')}
                      className="mt-0.5 text-rose-600 focus:ring-rose-500 h-3.5 w-3.5 rounded border-slate-300 cursor-pointer shrink-0"
                    />
                    <div className="min-w-0 flex-1 leading-tight">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[10.5px] font-medium truncate">Días de Cierre y Feriados</span>
                        <span
                          className={`text-[8.5px] px-1 py-0.2 rounded font-mono shrink-0 ${
                            isChecked
                              ? 'bg-rose-600 text-white font-bold'
                              : 'bg-slate-100 text-slate-500'
                          }`}
                        >
                          Cierre UCT
                        </span>
                      </div>
                      <div className="text-[9px] text-slate-400 font-normal truncate">
                        Feriados oficiales y recesos
                      </div>
                    </div>
                  </label>
                )
              })()}

              {/* Opción 5: Paro Federado (FEUCT) */}
              {(() => {
                const isChecked = selectedRegimenes.length === 0 || selectedRegimenes.includes('paro_federado')
                return (
                  <label
                    className={`flex items-start gap-1.5 p-1 rounded-md cursor-pointer transition select-none border ${
                      isChecked
                        ? 'bg-red-50/80 border-red-400/50 text-red-950 font-semibold shadow-2xs'
                        : 'bg-white/70 border-slate-200/60 hover:bg-slate-100 text-slate-700 opacity-70'
                    }`}
                    title="Accesos durante días de paro general estudiantil federado (FEUCT) o tomas de campus"
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleRegimen('paro_federado')}
                      className="mt-0.5 text-red-600 focus:ring-red-500 h-3.5 w-3.5 rounded border-slate-300 cursor-pointer shrink-0"
                    />
                    <div className="min-w-0 flex-1 leading-tight">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[10.5px] font-medium truncate">Paro Federado</span>
                        <span
                          className={`text-[8.5px] px-1 py-0.2 rounded font-mono shrink-0 ${
                            isChecked
                              ? 'bg-red-600 text-white font-bold'
                              : 'bg-slate-100 text-slate-500'
                          }`}
                        >
                          FEUCT
                        </span>
                      </div>
                      <div className="text-[9px] text-slate-400 font-normal truncate">
                        Movilización general
                      </div>
                    </div>
                  </label>
                )
              })()}

              {/* Opción 6: Paro por Carrera */}
              {(() => {
                const isChecked = selectedRegimenes.length === 0 || selectedRegimenes.includes('paro_carrera')
                return (
                  <label
                    className={`flex items-start gap-1.5 p-1 rounded-md cursor-pointer transition select-none border ${
                      isChecked
                        ? 'bg-yellow-50/80 border-yellow-400/50 text-yellow-950 font-semibold shadow-2xs'
                        : 'bg-white/70 border-slate-200/60 hover:bg-slate-100 text-slate-700 opacity-70'
                    }`}
                    title="Accesos durante días de paro parcial por carrera o facultad"
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleRegimen('paro_carrera')}
                      className="mt-0.5 text-yellow-600 focus:ring-yellow-500 h-3.5 w-3.5 rounded border-slate-300 cursor-pointer shrink-0"
                    />
                    <div className="min-w-0 flex-1 leading-tight">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[10.5px] font-medium truncate">Paro por Carrera</span>
                        <span
                          className={`text-[8.5px] px-1 py-0.2 rounded font-mono shrink-0 ${
                            isChecked
                              ? 'bg-yellow-600 text-white font-bold'
                              : 'bg-slate-100 text-slate-500'
                          }`}
                        >
                          Facultad
                        </span>
                      </div>
                      <div className="text-[9px] text-slate-400 font-normal truncate">
                        Afectación sectorizada
                      </div>
                    </div>
                  </label>
                )
              })()}
            </div>
          </div>

          <p className="text-[10px] text-slate-400 mt-1.5 border-t border-slate-100 pt-1 leading-snug">
            {selectedRegimenes.length === 0
              ? 'Todos los horarios activos'
              : `${selectedRegimenes.length} de ${allRegimenes.length} horarios activos`}
          </p>
        </div>

        {/* 2. Flujo / Dirección con Casillas Multi-Selección */}
        <div className="space-y-2 bg-white p-3 rounded-xl border border-slate-200/70 shadow-2xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between font-bold text-slate-700 mb-2">
              <div className="flex items-center gap-1.5">
                <ArrowUpDown size={14} className="text-uct-blue-primary" />
                <span>Flujo / Dirección</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-slate-400 font-normal">
                  {selectedFlujos.length === 0 ? 'Todos' : `${selectedFlujos.length} activos`}
                </span>
                {selectedFlujos.length > 0 && (
                  <button
                    type="button"
                    onClick={() => updateFilter('direccion', 'todos')}
                    className="text-[9px] text-uct-blue-primary hover:underline cursor-pointer font-medium"
                    title="Restablecer a todos los flujos"
                  >
                    Todos
                  </button>
                )}
              </div>
            </div>

            <div className="space-y-1">
              {flujoOptions.map((opt) => {
                const isChecked = selectedFlujos.length === 0 || selectedFlujos.includes(opt.id)
                return (
                  <label
                    key={opt.id}
                    className={`flex items-start gap-1.5 p-1 rounded-md cursor-pointer transition select-none border ${
                      isChecked
                        ? 'bg-blue-50/80 border-uct-blue-primary/40 text-uct-blue-primary font-semibold shadow-2xs'
                        : 'bg-white/70 border-slate-200/60 hover:bg-slate-100 text-slate-700 opacity-70'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleFlujo(opt.id)}
                      className="mt-0.5 text-uct-blue-primary focus:ring-uct-blue-primary h-3.5 w-3.5 rounded border-slate-300 cursor-pointer shrink-0"
                    />
                    <div className="min-w-0 flex-1 leading-tight">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[10.5px] font-medium truncate">{opt.label}</span>
                        <span
                          className={`text-[8.5px] px-1 py-0.2 rounded font-mono shrink-0 ${
                            isChecked
                              ? 'bg-uct-blue-primary text-white font-bold'
                              : 'bg-slate-100 text-slate-500'
                          }`}
                        >
                          {opt.tag}
                        </span>
                      </div>
                      <div className="text-[9px] text-slate-400 font-normal truncate" title={opt.ejemplo}>
                        {opt.ejemplo}
                      </div>
                    </div>
                  </label>
                )
              })}
            </div>
          </div>

          <p className="text-[10px] text-slate-400 mt-1.5 border-t border-slate-100 pt-1 leading-snug">
            {selectedFlujos.length === 0
              ? 'Todos los flujos activos'
              : `${selectedFlujos.length} de ${allFlujos.length} flujos activos`}
          </p>
        </div>

        {/* 3. Días de la Semana con Casillas de Selección */}
        <div className="space-y-2 bg-white p-3 rounded-xl border border-slate-200/70 shadow-2xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between font-bold text-slate-700 mb-2">
              <div className="flex items-center gap-1.5">
                <Calendar size={14} className="text-uct-blue-primary" />
                <span>Días de Semana</span>
              </div>
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => setDiasPreset('habiles')}
                  className="text-[9px] text-uct-blue-primary hover:underline cursor-pointer font-medium"
                  title="Lunes a Viernes"
                >
                  Hábiles
                </button>
                <span className="text-[9px] text-slate-300">|</span>
                <button
                  type="button"
                  onClick={() => setDiasPreset('finde')}
                  className="text-[9px] text-uct-blue-primary hover:underline cursor-pointer font-medium"
                  title="Sábado y Domingo"
                >
                  Finde
                </button>
                <span className="text-[9px] text-slate-300">|</span>
                <button
                  type="button"
                  onClick={() => setDiasPreset('todos')}
                  className="text-[9px] text-slate-500 hover:underline cursor-pointer"
                >
                  Todos
                </button>
              </div>
            </div>

            <div className="grid grid-cols-4 gap-1.5">
              {DIAS_OPTIONS.map(d => {
                const isChecked = selectedDias.length === 0 || selectedDias.includes(d.id)
                return (
                  <label
                    key={d.id}
                    className="flex items-center gap-1 cursor-pointer select-none text-[10px] font-medium text-slate-700 hover:text-slate-900"
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleDia(d.id)}
                      className="rounded text-uct-blue-primary focus:ring-uct-blue-primary h-3 w-3 border-slate-300 cursor-pointer"
                    />
                    <span>{d.label}</span>
                  </label>
                )
              })}
            </div>
          </div>

          <p className="text-[10px] text-slate-400 mt-2 border-t border-slate-100 pt-1.5">
            {selectedDias.length === 0 ? 'Todos los días' : `${selectedDias.length} días activos`}
          </p>
        </div>

        {/* 4. Torniquete / Punto de Acceso con Casillas de Selección */}
        <div className="space-y-2 bg-white p-3 rounded-xl border border-slate-200/70 shadow-2xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between font-bold text-slate-700 mb-2">
              <div className="flex items-center gap-1.5">
                <DoorClosed size={14} className="text-uct-blue-primary" />
                <span>{modulo === 'biblioteca' ? 'Torniquetes y Accesos' : 'Cámaras ANPR'}</span>
              </div>
              <span className="text-[10px] text-slate-400 font-normal">
                {modulo === 'biblioteca' && activeSalaKey
                  ? `${selectedDoors.length} activos (${activeSalaKey === 'sala_1' ? 'Sala 1' : 'Sala 2'})`
                  : selectedDoors.length === 0
                  ? 'Todos'
                  : `${selectedDoors.length} activos`}
              </span>
            </div>

            <div className="space-y-1.5 max-h-[190px] overflow-y-auto pr-1">
              {modulo === 'biblioteca' ? (
                allBibDoorsItems.map(t => {
                  const isBlocked = activeSalaKey !== null && t.salaKey !== activeSalaKey
                  const isChecked = !isBlocked && selectedDoors.includes(t.id)

                  return (
                    <label
                      key={t.id}
                      className={`flex items-start gap-1.5 select-none text-[11px] font-medium transition-all ${
                        isBlocked
                          ? 'opacity-40 cursor-not-allowed bg-slate-50/70 p-1.5 rounded-lg border border-slate-200/60'
                          : 'cursor-pointer text-slate-700 hover:text-slate-900 p-1.5 rounded-lg hover:bg-slate-50'
                      }`}
                      title={
                        isBlocked
                          ? `Bloqueado: pertenece a ${t.salaNombre}. Actualmente está filtrada la ${activeSalaKey === 'sala_1' ? 'Sala 1' : 'Sala 2'}`
                          : t.code
                      }
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        disabled={isBlocked}
                        onChange={() => {
                          if (!isBlocked) toggleDoor(t.id)
                        }}
                        className={`rounded h-3.5 w-3.5 mt-0.5 shrink-0 ${
                          isBlocked
                            ? 'bg-slate-200 border-slate-300 text-slate-400 cursor-not-allowed'
                            : 'text-uct-blue-primary focus:ring-uct-blue-primary border-slate-300 cursor-pointer'
                        }`}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-1">
                          <span className={`block leading-tight font-semibold truncate ${
                            isBlocked ? 'text-slate-400 line-through' : 'text-slate-800'
                          }`}>
                            {t.name}
                          </span>
                          <div className="flex items-center gap-1 shrink-0">
                            {isBlocked ? (
                              <span className="text-[7.5px] px-1 py-0.2 rounded bg-slate-200 text-slate-600 font-bold">
                                Bloqueado
                              </span>
                            ) : (
                              <span className={`text-[8px] px-1 rounded font-medium ${
                                t.tipo === 'Universal' ? 'bg-amber-100 text-amber-800' : 'bg-blue-100 text-uct-blue-primary'
                              }`}>
                                {t.tipo}
                              </span>
                            )}
                          </div>
                        </div>
                        <span className="text-[9.5px] text-slate-400 block leading-tight font-mono">{t.hardware}</span>
                      </div>
                    </label>
                  )
                })
              ) : (
                [
                  { id: 'CSF_ACCESO_NORTE', label: 'Acceso Norte' },
                  { id: 'CSF_ACCESO_SUR', label: 'Acceso Sur' },
                  { id: 'CHS_ACCESO_PRINCIPAL', label: 'San Juan' },
                ].map(c => {
                  const isChecked = selectedDoors.length === 0 || selectedDoors.includes(c.id)
                  return (
                    <label
                      key={c.id}
                      className="flex items-center gap-1.5 cursor-pointer select-none text-[10px] font-medium text-slate-700 hover:text-slate-900 col-span-2"
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleDoor(c.id)}
                        className="rounded text-uct-blue-primary focus:ring-uct-blue-primary h-3.5 w-3.5 border-slate-300 cursor-pointer"
                      />
                      <span>{c.label}</span>
                    </label>
                  )
                })
              )}
            </div>
          </div>

          {modulo === 'biblioteca' && activeSalaKey ? (
            <p className="text-[9.5px] text-amber-700 bg-amber-50 px-2 py-1 rounded-md border border-amber-200 mt-2">
              Torniquetes de {activeSalaKey === 'sala_1' ? 'Sala 2' : 'Sala 1'} bloqueados por selección de sala
            </p>
          ) : (
            <p className="text-[10px] text-slate-400 mt-2 border-t border-slate-100 pt-1.5">
              Filtrar flujo por punto de acceso
            </p>
          )}
        </div>

        {/* 5. Marcajes por Día con Casillas de Selección */}
        <div className="space-y-2 bg-white p-3 rounded-xl border border-slate-200/70 shadow-2xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between font-bold text-slate-700 mb-2">
              <div className="flex items-center gap-1.5">
                <UserCheck size={14} className="text-uct-blue-primary" />
                <span>Marcajes por Día</span>
              </div>
              <span className="text-[10px] text-slate-400 font-normal">
                {selectedMarcajes.length === 0 ? 'Todos' : `${selectedMarcajes.length} activos`}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-1.5">
              {[
                { id: '1', label: '1 marcaje' },
                { id: '2', label: '2 marcajes' },
                { id: '3-4', label: '3-4 marc.' },
                { id: '5+', label: modulo === 'biblioteca' ? '5+ reingresos' : '5+ excesivo' },
              ].map(m => {
                const isChecked = selectedMarcajes.length === 0 || selectedMarcajes.includes(m.id)
                return (
                  <label
                    key={m.id}
                    className="flex items-center gap-1.5 cursor-pointer select-none text-[11px] font-medium text-slate-700 hover:text-slate-900"
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleMarcaje(m.id)}
                      className="rounded text-uct-blue-primary focus:ring-uct-blue-primary h-3.5 w-3.5 border-slate-300 cursor-pointer"
                    />
                    <span>{m.label}</span>
                  </label>
                )
              })}
            </div>

            {modulo === 'biblioteca' && (
              <div className="mt-2.5 pt-2 border-t border-slate-100 space-y-1.5 bg-slate-50/70 p-2 rounded-lg border border-slate-200/60">
                <span className="text-[9.5px] font-bold text-slate-600 uppercase tracking-wider block">
                  Tratamiento Marcajes ≥ 5
                </span>

                <label className="flex items-start gap-1.5 cursor-pointer select-none text-[10.5px] font-medium text-slate-700 hover:text-slate-900 leading-tight">
                  <input
                    type="checkbox"
                    checked={filters.incluir_pausas_bano !== false}
                    onChange={() => updateFilter('incluir_pausas_bano', !(filters.incluir_pausas_bano !== false))}
                    className="rounded text-emerald-600 focus:ring-emerald-500 h-3.5 w-3.5 border-slate-300 cursor-pointer mt-0.5 shrink-0"
                  />
                  <div>
                    <span className="font-semibold text-slate-800">Salidas baño / pausa (3–15 min)</span>
                    <span className="block text-[9.5px] text-emerald-700 font-normal">Admite 6.722 eventos conformes</span>
                  </div>
                </label>

                <label className="flex items-start gap-1.5 cursor-pointer select-none text-[10.5px] font-medium text-slate-700 hover:text-slate-900 leading-tight">
                  <input
                    type="checkbox"
                    checked={filters.desduplicar_rafagas !== false}
                    onChange={() => updateFilter('desduplicar_rafagas', !(filters.desduplicar_rafagas !== false))}
                    className="rounded text-uct-blue-primary focus:ring-uct-blue-primary h-3.5 w-3.5 border-slate-300 cursor-pointer mt-0.5 shrink-0"
                  />
                  <div>
                    <span className="font-semibold text-slate-800">Desduplicar ráfagas sensor (&lt;1 min)</span>
                    <span className="block text-[9.5px] text-slate-500 font-normal">Filtra toques mecánicos repetidos</span>
                  </div>
                </label>
              </div>
            )}
          </div>

          <p className="text-[10px] text-slate-400 mt-2 border-t border-slate-100 pt-1.5">
            {modulo === 'biblioteca'
              ? 'Control de rebote, pausas cortas y multirreingreso'
              : 'Auditar rebote o marcajes múltiples'}
          </p>
        </div>

        {/* 6. Perfil de Visita con Casillas de Selección */}
        <div className="space-y-2 bg-white p-3 rounded-xl border border-slate-200/70 shadow-2xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between font-bold text-slate-700 mb-2">
              <div className="flex items-center gap-1.5">
                <Clock size={14} className="text-uct-blue-primary" />
                <span>Perfil de Visita</span>
              </div>
              <span className="text-[10px] text-slate-400 font-normal">
                {selectedPerfiles.length === 0 ? 'Todos' : `${selectedPerfiles.length} activos`}
              </span>
            </div>

            <div className="space-y-1.5">
              {[
                { id: 'rebote', label: 'Rebote (<15 min)' },
                { id: 'estandar', label: 'Estándar (15–120 min)' },
                { id: 'profundo', label: 'Profundo (>120 min)' },
              ].map(p => {
                const isChecked = selectedPerfiles.length === 0 || selectedPerfiles.includes(p.id)
                return (
                  <label
                    key={p.id}
                    className="flex items-center gap-2 cursor-pointer select-none text-[11px] font-medium text-slate-700 hover:text-slate-900"
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => togglePerfil(p.id)}
                      className="rounded text-uct-blue-primary focus:ring-uct-blue-primary h-3.5 w-3.5 border-slate-300 cursor-pointer"
                    />
                    <span>{p.label}</span>
                  </label>
                )
              })}
            </div>
          </div>

          <p className="text-[10px] text-slate-400 mt-2 border-t border-slate-100 pt-1.5">
            Segmentación por tiempo de estadía
          </p>
        </div>

      </div>
      </div>
      )}

      {/* Notificación Contextual de Cambio de Período */}
      {noticeMessage && (
        <div className="flex items-center justify-between p-2.5 px-3.5 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 animate-in fade-in slide-in-from-top-1 duration-200 shadow-2xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={15} className="text-emerald-600 shrink-0" />
            <span className="font-medium">{noticeMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setNoticeMessage(null)}
            className="text-emerald-600 hover:text-emerald-800 p-0.5 rounded cursor-pointer"
          >
            <X size={13} />
          </button>
        </div>
      )}

      {/* Modal de Confirmación de Cambio de Período */}
      {pendingScheduleModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4 animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl max-w-md w-full p-5 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div className="w-10 h-10 rounded-xl bg-uct-blue-primary/10 flex items-center justify-center text-uct-blue-primary shrink-0">
                <Calendar size={20} />
              </div>
              <div className="flex-1">
                <h4 className="text-sm font-bold text-slate-800">
                  Ajustar Período de Consulta
                </h4>
                <p className="text-xs text-slate-500 mt-0.5">
                  Cambio automático de rango de fechas
                </p>
              </div>
              <button
                type="button"
                onClick={() => setPendingScheduleModal(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg hover:bg-slate-100 transition cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <div className="p-3 bg-blue-50/70 border border-blue-200/80 rounded-xl text-xs space-y-1.5 text-slate-700">
              <p>
                El régimen <span className="font-bold text-uct-blue-primary">{pendingScheduleModal.descripcion}</span> rige exclusivamente entre el <span className="font-semibold">{formatIsoDate(pendingScheduleModal.fecha_inicio)}</span> y el <span className="font-semibold">{formatIsoDate(pendingScheduleModal.fecha_fin)}</span>.
              </p>
              <p className="text-slate-500 text-[11px]">
                El rango actual seleccionado ({dateRange?.label || 'personalizado'}) no intersecta con esta vigencia. Para analizarlo, se actualizará el período de consulta a dicho rango.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setPendingScheduleModal(null)}
                className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg font-medium transition cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleConfirmSchedule}
                className="px-3.5 py-1.5 text-xs bg-uct-blue-primary hover:bg-uct-blue-secondary text-white font-semibold rounded-lg shadow-xs hover:shadow transition cursor-pointer flex items-center gap-1.5"
              >
                <CheckCircle2 size={13} />
                <span>Cambiar Período y Consultar</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ScopeSelector
