import React, { useState, useMemo, useCallback, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Table,
  Download,
  FileSpreadsheet,
  FileText,
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Database,
  Shield,
  Layers,
  ArrowUpDown,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Tag,
  X,
  RotateCcw,
  SlidersHorizontal,
} from 'lucide-react'
import {
  fetchRawAttendance,
  fetchRawVehicles,
  recordDownloadAudit,
  RawAttendanceItem,
  RawVehicleItem,
  DataFilters,
  api,
} from '../../api/client'
import { useDownloadProgress } from '../../context/DownloadProgressContext'
import { descargarBlob } from '../../utils/excelExport'
import { ExcelColumnHeader, SortConfig } from './ExcelColumnHeader'

// Helper para formatear puertas y torniquetes
const getDoorLabel = (doorVal?: string | null): string => {
  if (!doorVal || doorVal === 'None' || doorVal === 'nan' || doorVal === '') return '—'
  const val = String(doorVal).replace('.0', '').trim()
  if (val === '2177') return '2177 (T1 Sala 1)'
  if (val === '2170') return '2170 (T1 Sala 1)'
  if (val === '2202') return '2202 (T2 Sala 1)'
  if (val === '2184') return '2184 (T2 Sala 1)'
  return val
}

// Helper para extraer lista de categorías
const getCategories = (r: any): string[] => {
  if (!r?.categorias || r.categorias.length === 0) return ['Conforme']
  return r.categorias
}

// Títulos amigables para chips de filtros
const getColumnTitle = (key: string): string => {
  const titles: Record<string, string> = {
    time: 'Fecha y Hora',
    fecha: 'Fecha',
    hora: 'Hora',
    person_id_short: 'Identificador',
    patente_short: 'Patente',
    categorias: 'Categorías & Calidad',
    door_entrada: 'Torniquete Ent.',
    door_salida: 'Torniquete Sal.',
    primera_entrada: '1ª Entrada',
    ultima_salida: 'Última Salida',
    permanencia_min: 'Estadía',
    marcajes_totales: 'Marcajes',
    camara: 'Cámara ANPR',
    direccion: 'Dirección',
    tipo_vehiculo: 'Tipo Vehículo',
    marca: 'Marca',
    color: 'Color',
  }
  return titles[key] || key
}

interface Props {
  modulo: 'biblioteca' | 'estacionamiento'
  fechaInicio?: string
  fechaFin?: string
  labelPeriodo?: string
  appliedFilters?: DataFilters
}

export const RawDataTable: React.FC<Props> = ({
  modulo,
  fechaInicio,
  fechaFin,
  labelPeriodo,
  appliedFilters,
}) => {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [searchTerm, setSearchTerm] = useState('')
  const [filtroExtra, setFiltroExtra] = useState('') // Puerta o Cámara
  const [filtroDireccion, setFiltroDireccion] = useState('') // Ciclo de asistencia o dirección vehicular
  const [filtroCategoria, setFiltroCategoria] = useState('') // Categoría de calidad/anomalía
  const [filtroMarcajes, setFiltroMarcajes] = useState('') // 1, 2, 3-4, 5+
  const [horaMin, setHoraMin] = useState('') // HH:MM
  const [horaMax, setHoraMax] = useState('') // HH:MM
  const [fechaSubFiltroInicio, setFechaSubFiltroInicio] = useState('') // YYYY-MM-DD
  const [fechaSubFiltroFin, setFechaSubFiltroFin] = useState('') // YYYY-MM-DD
  const [isExportingPdf, setIsExportingPdf] = useState(false)
  const { ejecutarDescarga } = useDownloadProgress()

  // Estados para ordenamiento y filtros múltiples tipo Excel
  const [sortConfig, setSortConfig] = useState<SortConfig | null>(null)
  const [columnFilters, setColumnFilters] = useState<Record<string, string[] | null>>({})

  // Limpiar filtros y orden al alternar entre Biblioteca y Estacionamiento
  useEffect(() => {
    setSortConfig(null)
    setColumnFilters({})
    setFiltroDireccion('')
    setFiltroMarcajes('')
    setHoraMin('')
    setHoraMax('')
    setFechaSubFiltroInicio('')
    setFechaSubFiltroFin('')
  }, [modulo])

  // Limpiar todos los filtros Excel
  const handleClearAllColumnFilters = () => {
    setColumnFilters({})
    setSortConfig(null)
  }

  // Filtros combinados entre controles de tabla y selectores globales del dashboard
  const effectiveDoor = filtroExtra || appliedFilters?.door || undefined
  const effectiveRegimen = appliedFilters?.regimen_horario && appliedFilters.regimen_horario !== 'todos' ? appliedFilters.regimen_horario : undefined
  const effectiveDireccion = (filtroDireccion ? filtroDireccion : undefined) || (appliedFilters?.direccion && appliedFilters.direccion !== 'todos' ? appliedFilters.direccion : undefined)
  const effectiveDias = appliedFilters?.dias_semana || undefined
  const effectivePerfil = appliedFilters?.perfil_visita && appliedFilters.perfil_visita !== 'todos' ? appliedFilters.perfil_visita : undefined
  const effectiveMarcajes = (modulo === 'biblioteca' && filtroMarcajes ? filtroMarcajes : undefined) || (appliedFilters?.marcajes && appliedFilters.marcajes !== 'todos' ? appliedFilters.marcajes : undefined)
  const effectiveAlcance = appliedFilters?.alcance || 'todos'

  // Query para asistencia
  const attendanceQuery = useQuery({
    queryKey: [
      'raw-attendance',
      page,
      pageSize,
      fechaInicio,
      fechaFin,
      effectiveDoor,
      searchTerm,
      filtroCategoria,
      effectiveAlcance,
      effectiveRegimen,
      effectiveDireccion,
      effectiveDias,
      effectivePerfil,
      effectiveMarcajes,
      appliedFilters?.incluir_pausas_bano,
      appliedFilters?.desduplicar_rafagas,
    ],
    queryFn: () =>
      fetchRawAttendance({
        page,
        pageSize,
        fechaInicio,
        fechaFin,
        door: effectiveDoor,
        searchHash: searchTerm || undefined,
        categoria: filtroCategoria || undefined,
        alcance: effectiveAlcance,
        regimenHorario: effectiveRegimen,
        direccion: effectiveDireccion,
        diasSemana: effectiveDias,
        perfilVisita: effectivePerfil,
        marcajes: effectiveMarcajes,
        incluirPausasBano: appliedFilters?.incluir_pausas_bano,
        desduplicarRafagas: appliedFilters?.desduplicar_rafagas,
      }),
    enabled: modulo === 'biblioteca',
    staleTime: 60_000,
  })

  // Query para vehículos
  const vehicleQuery = useQuery({
    queryKey: [
      'raw-vehicles',
      page,
      pageSize,
      fechaInicio,
      fechaFin,
      effectiveDoor,
      effectiveDireccion,
      searchTerm,
      filtroCategoria,
      effectiveAlcance,
      effectiveRegimen,
      effectiveDias,
    ],
    queryFn: () =>
      fetchRawVehicles({
        page,
        pageSize,
        fechaInicio,
        fechaFin,
        camara: effectiveDoor,
        direccion: effectiveDireccion,
        searchHash: searchTerm || undefined,
        categoria: filtroCategoria || undefined,
        alcance: effectiveAlcance,
        regimenHorario: effectiveRegimen,
        diasSemana: effectiveDias,
        door: effectiveDoor,
      }),
    enabled: modulo === 'estacionamiento',
    staleTime: 60_000,
  })

  const isLoading = modulo === 'biblioteca' ? attendanceQuery.isLoading : vehicleQuery.isLoading
  const isFetching = modulo === 'biblioteca' ? attendanceQuery.isFetching : vehicleQuery.isFetching
  const refetch = modulo === 'biblioteca' ? attendanceQuery.refetch : vehicleQuery.refetch

  const total = modulo === 'biblioteca' ? attendanceQuery.data?.total ?? 0 : vehicleQuery.data?.total ?? 0
  const totalPages =
    modulo === 'biblioteca'
      ? attendanceQuery.data?.total_pages ?? 1
      : vehicleQuery.data?.total_pages ?? 1
  const attendanceItems = attendanceQuery.data?.items ?? []
  const vehicleItems = vehicleQuery.data?.items ?? []

  // Extracción de valores únicos y frecuencias para menús Excel
  const getColumnStats = useCallback(
    (
      key: string,
      extractor: (row: any) => string | string[],
      isArray = false
    ): { uniqueValues: string[]; valueCounts: Record<string, number> } => {
      const rawItems = modulo === 'biblioteca' ? attendanceItems : vehicleItems
      const counts: Record<string, number> = {}

      for (const item of rawItems) {
        const val = extractor(item)
        if (isArray && Array.isArray(val)) {
          for (const v of val) {
            const clean = String(v ?? '—').trim() || '—'
            counts[clean] = (counts[clean] || 0) + 1
          }
        } else {
          const clean = String(val ?? '—').trim() || '—'
          counts[clean] = (counts[clean] || 0) + 1
        }
      }

      const uniqueValues = Object.keys(counts).sort((a, b) =>
        a.localeCompare(b, 'es', { numeric: true, sensitivity: 'base' })
      )

      return { uniqueValues, valueCounts: counts }
    },
    [modulo, attendanceItems, vehicleItems]
  )

  // Diccionario de estadísticas por columna
  const columnStats: Record<string, { uniqueValues: string[]; valueCounts: Record<string, number> } | undefined> = useMemo(() => {
    if (modulo === 'biblioteca') {
      return {
        fecha: getColumnStats('fecha', (r: RawAttendanceItem) => (r.time ? r.time.slice(0, 10) : '—')),
        hora: getColumnStats('hora', (r: RawAttendanceItem) => (r.time && r.time.length >= 19 ? r.time.slice(11, 19) : '—')),
        person_id_short: getColumnStats('person_id_short', (r: RawAttendanceItem) => r.person_id_short),
        categorias: getColumnStats('categorias', (r: RawAttendanceItem) => getCategories(r), true),
        door_entrada: getColumnStats('door_entrada', (r: RawAttendanceItem) => getDoorLabel(r.door_entrada)),
        door_salida: getColumnStats('door_salida', (r: RawAttendanceItem) => getDoorLabel(r.door_salida)),
        primera_entrada: getColumnStats('primera_entrada', (r: RawAttendanceItem) => r.primera_entrada || '—'),
        ultima_salida: getColumnStats('ultima_salida', (r: RawAttendanceItem) => r.ultima_salida || '—'),
        permanencia_min: getColumnStats('permanencia_min', (r: RawAttendanceItem) =>
          r.permanencia_min > 0 ? `${r.permanencia_min} min` : '—'
        ),
        marcajes_totales: getColumnStats('marcajes_totales', (r: RawAttendanceItem) =>
          String(r.marcajes_totales ?? 0)
        ),
      }
    } else {
      return {
        fecha: getColumnStats('fecha', (r: RawVehicleItem) => (r.time ? r.time.slice(0, 10) : '—')),
        hora: getColumnStats('hora', (r: RawVehicleItem) => (r.time && r.time.length >= 19 ? r.time.slice(11, 19) : '—')),
        patente_short: getColumnStats('patente_short', (r: RawVehicleItem) => r.patente_short),
        categorias: getColumnStats('categorias', (r: RawVehicleItem) => getCategories(r), true),
        camara: getColumnStats('camara', (r: RawVehicleItem) => r.camara || '—'),
        direccion: getColumnStats('direccion', (r: RawVehicleItem) =>
          r.direccion ? r.direccion.toUpperCase() : '—'
        ),
        tipo_vehiculo: getColumnStats('tipo_vehiculo', (r: RawVehicleItem) => r.tipo_vehiculo || '—'),
        marca: getColumnStats('marca', (r: RawVehicleItem) => r.marca || '—'),
        color: getColumnStats('color', (r: RawVehicleItem) => r.color || '—'),
      }
    }
  }, [modulo, attendanceItems, vehicleItems, getColumnStats])

  // Lógica de múltiples filtros y ordenamiento en memoria
  const filteredAndSortedRows = useMemo(() => {
    const rawItems = modulo === 'biblioteca' ? attendanceItems : vehicleItems
    if (!rawItems || rawItems.length === 0) return []

    // 1. Filtrado lógico AND sobre todas las columnas con filtros activos
    let result = rawItems.filter((row: any) => {
      for (const [colKey, selected] of Object.entries(columnFilters)) {
        if (!selected || selected.length === 0) continue

        if (colKey === 'fecha') {
          const val = row.time ? row.time.slice(0, 10) : '—'
          if (!selected.includes(val)) return false
        } else if (colKey === 'hora') {
          const val = row.time && row.time.length >= 19 ? row.time.slice(11, 19) : '—'
          if (!selected.includes(val)) return false
        } else if (colKey === 'categorias') {
          const cats = getCategories(row)
          const matches = cats.some((c) => selected.includes(c))
          if (!matches) return false
        } else if (colKey === 'door_entrada') {
          const label = getDoorLabel(row.door_entrada)
          if (!selected.includes(label)) return false
        } else if (colKey === 'door_salida') {
          const label = getDoorLabel(row.door_salida)
          if (!selected.includes(label)) return false
        } else if (colKey === 'permanencia_min') {
          const label = row.permanencia_min > 0 ? `${row.permanencia_min} min` : '—'
          if (!selected.includes(label)) return false
        } else if (colKey === 'marcajes_totales') {
          const label = String(row.marcajes_totales ?? 0)
          if (!selected.includes(label)) return false
        } else if (colKey === 'direccion') {
          const label = row.direccion ? row.direccion.toUpperCase() : '—'
          if (!selected.includes(label)) return false
        } else {
          const val = String(row[colKey] ?? '—').trim() || '—'
          if (!selected.includes(val)) return false
        }
      }
      return true
    })

    // 2. Filtro horizontal de franja horaria (Hora Mínima / Máxima)
    if (horaMin || horaMax) {
      result = result.filter((row: any) => {
        if (!row.time || row.time.length < 16) return true
        const t = row.time.slice(11, 16)
        if (horaMin && t < horaMin) return false
        if (horaMax && t > horaMax) return false
        return true
      })
    }

    // 3. Filtro horizontal de sub-rango de fechas
    if (fechaSubFiltroInicio || fechaSubFiltroFin) {
      result = result.filter((row: any) => {
        if (!row.time || row.time.length < 10) return true
        const d = row.time.slice(0, 10)
        if (fechaSubFiltroInicio && d < fechaSubFiltroInicio) return false
        if (fechaSubFiltroFin && d > fechaSubFiltroFin) return false
        return true
      })
    }

    // 4. Ordenamiento si sortConfig está activo
    if (sortConfig) {
      const { key, direction } = sortConfig
      const mul = direction === 'asc' ? 1 : -1

      result = [...result].sort((a: any, b: any) => {
        if (key === 'time' || key === 'fecha') {
          const timeA = new Date(a.time).getTime() || 0
          const timeB = new Date(b.time).getTime() || 0
          return (timeA - timeB) * mul
        }
        if (key === 'hora') {
          const timeA = a.time && a.time.length >= 19 ? a.time.slice(11, 19) : ''
          const timeB = b.time && b.time.length >= 19 ? b.time.slice(11, 19) : ''
          return timeA.localeCompare(timeB) * mul
        }
        if (key === 'permanencia_min') {
          return ((a.permanencia_min || 0) - (b.permanencia_min || 0)) * mul
        }
        if (key === 'marcajes_totales') {
          return ((a.marcajes_totales || 0) - (b.marcajes_totales || 0)) * mul
        }
        if (key === 'categorias') {
          const strA = (getCategories(a) || []).join(', ')
          const strB = (getCategories(b) || []).join(', ')
          return strA.localeCompare(strB, 'es') * mul
        }
        if (key === 'door_entrada') {
          const valA = getDoorLabel(a.door_entrada)
          const valB = getDoorLabel(b.door_entrada)
          return valA.localeCompare(valB, 'es') * mul
        }
        if (key === 'door_salida') {
          const valA = getDoorLabel(a.door_salida)
          const valB = getDoorLabel(b.door_salida)
          return valA.localeCompare(valB, 'es') * mul
        }
        if (key === 'direccion') {
          const valA = a.direccion ? a.direccion.toUpperCase() : ''
          const valB = b.direccion ? b.direccion.toUpperCase() : ''
          return valA.localeCompare(valB, 'es') * mul
        }

        const strA = String(a[key] ?? '')
        const strB = String(b[key] ?? '')
        return strA.localeCompare(strB, 'es', { numeric: true, sensitivity: 'base' }) * mul
      })
    }

    return result
  }, [modulo, attendanceItems, vehicleItems, columnFilters, sortConfig])

  // Lista de filtros de columna activos
  const activeFilterKeys = useMemo(
    () =>
      Object.entries(columnFilters).filter(
        ([_, vals]) => vals !== null && vals.length > 0
      ),
    [columnFilters]
  )

  // Helper para renderizar badges de categorías
  const renderCategoryBadges = (categorias: string[] = []) => {
    if (!categorias || categorias.length === 0) {
      return (
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
          Conforme
        </span>
      )
    }

    return (
      <div className="flex flex-wrap gap-1">
        {categorias.map((cat, i) => {
          let badgeStyle = 'bg-slate-100 text-slate-700 border-slate-200'
          if (cat === 'Conforme') badgeStyle = 'bg-emerald-50 text-emerald-700 border-emerald-200'
          else if (cat === 'Fuera de Horario') badgeStyle = 'bg-purple-50 text-purple-700 border-purple-200'
          else if (cat === 'Sin Salida') badgeStyle = 'bg-amber-50 text-amber-700 border-amber-200'
          else if (cat === 'Sin Entrada') badgeStyle = 'bg-cyan-50 text-cyan-700 border-cyan-200 font-semibold'
          else if (cat === 'Hora Invertida') badgeStyle = 'bg-rose-50 text-rose-700 border-rose-200 font-bold'
          else if (cat === 'Sin Credencial') badgeStyle = 'bg-blue-50 text-blue-700 border-blue-200'
          else if (cat === 'Marcaje Excesivo') badgeStyle = 'bg-orange-50 text-orange-700 border-orange-200'
          else if (cat === 'Lectura Ilegible') badgeStyle = 'bg-red-50 text-red-700 border-red-200 font-bold'

          return (
            <span
              key={`${cat}-${i}`}
              className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold border ${badgeStyle}`}
            >
              {cat}
            </span>
          )
        })}
      </div>
    )
  }

  // Helper para renderizar badges de torniquetes / puertas físicas
  const renderDoorBadge = (doorVal?: string | null) => {
    if (!doorVal || doorVal === 'None' || doorVal === 'nan' || doorVal === '') return <span className="text-slate-400">—</span>
    const val = String(doorVal).replace('.0', '').trim()
    if (val === '2177') {
      return (
        <span className="inline-flex items-center gap-1 font-mono text-[11px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded border border-slate-200" title="CSF02_320IN01 — Torniquete 1 Sala 1">
          <span className="font-bold text-uct-blue-primary">2177</span>
          <span className="text-[9.5px] text-slate-500 font-sans font-medium">(T1 Sala 1)</span>
        </span>
      )
    }
    if (val === '2170') {
      return (
        <span className="inline-flex items-center gap-1 font-mono text-[11px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded border border-slate-200" title="CSF02_320OUT01 — Torniquete 1 Sala 1">
          <span className="font-bold text-amber-700">2170</span>
          <span className="text-[9.5px] text-slate-500 font-sans font-medium">(T1 Sala 1)</span>
        </span>
      )
    }
    if (val === '2202') {
      return (
        <span className="inline-flex items-center gap-1 font-mono text-[11px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded border border-slate-200" title="CSF02_320IN02 — Torniquete 2 Sala 1">
          <span className="font-bold text-uct-blue-primary">2202</span>
          <span className="text-[9.5px] text-slate-500 font-sans font-medium">(T2 Sala 1)</span>
        </span>
      )
    }
    if (val === '2184') {
      return (
        <span className="inline-flex items-center gap-1 font-mono text-[11px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded border border-slate-200" title="CSF02_320OUT02 — Torniquete 2 Sala 1">
          <span className="font-bold text-amber-700">2184</span>
          <span className="text-[9.5px] text-slate-500 font-sans font-medium">(T2 Sala 1)</span>
        </span>
      )
    }
    return <span className="font-mono text-xs text-slate-700">{val}</span>
  }

  // Descarga CSV directa (con 100% de datos filtrados) usando modal de progreso
  const handleExportCSV = async () => {
    const moduloNombre = modulo === 'biblioteca' ? 'Biblioteca Campus San Francisco' : 'Estacionamiento Campus San Francisco'
    const endpoint =
      modulo === 'biblioteca'
        ? '/attendance/export-raw-csv'
        : '/vehicles/export-raw-csv'

    const params: Record<string, any> = {}
    if (fechaInicio) params.fecha_inicio = fechaInicio
    if (fechaFin) params.fecha_fin = fechaFin
    if (searchTerm) params.search_hash = searchTerm
    if (filtroCategoria) params.categoria = filtroCategoria
    params.alcance = effectiveAlcance

    if (effectiveDoor) {
      if (modulo === 'biblioteca') params.door = effectiveDoor
      else params.camara = effectiveDoor
    }
    if (effectiveRegimen) params.regimen_horario = effectiveRegimen
    if (effectiveDireccion) params.direccion = effectiveDireccion
    if (effectiveDias) params.dias_semana = effectiveDias
    if (effectivePerfil) params.perfil_visita = effectivePerfil
    if (effectiveMarcajes) params.marcajes = effectiveMarcajes
    if (appliedFilters?.incluir_pausas_bano !== undefined) {
      params.incluir_pausas_bano = String(appliedFilters.incluir_pausas_bano)
    }
    if (appliedFilters?.desduplicar_rafagas !== undefined) {
      params.desduplicar_rafagas = String(appliedFilters.desduplicar_rafagas)
    }

    const filename = `Microdatos_${modulo === 'biblioteca' ? 'Biblioteca' : 'Estacionamiento'}_${new Date().toISOString().slice(0, 10)}.csv`

    await ejecutarDescarga({
      titulo: 'Exportación de Microdatos a CSV',
      subtitulo: `${moduloNombre} • Registros físicos y auditoría Ley 21.719`,
      tipo: 'csv',
      nombreArchivo: filename,
      tarea: async ({ setProgreso }) => {
        setProgreso(15, 'Consultando registros de auditoría en la base de datos...')

        try {
          await recordDownloadAudit({
            modulo,
            formato: 'csv',
            filtro_fecha_inicio: fechaInicio,
            filtro_fecha_fin: fechaFin,
            filtro_detalle: `CSV Completo. Categoría: ${filtroCategoria || 'todas'}, Puerta: ${effectiveDoor || 'todas'}`,
            total_registros: total,
          })
        } catch (e) {
          console.warn('No se pudo registrar la auditoría de descarga:', e)
        }

        setProgreso(45, 'Estructurando registros con delimitadores CSV y codificación UTF-8...')
        const response = await api.get(endpoint, {
          params,
          responseType: 'blob',
          timeout: 180_000,
        })

        setProgreso(85, 'Archivo generado. Guardando localmente...')
        descargarBlob(response.data, filename, '.csv')
        setProgreso(98, 'Descarga finalizada con éxito.')
        await new Promise(r => setTimeout(r, 300))
      },
    })
  }

  // Descarga PDF Resumido con auditoría y datos completos filtrados
  const handleExportPDF = async () => {
    const moduloNombre = modulo === 'biblioteca' ? 'Biblioteca Campus San Francisco' : 'Estacionamiento Campus San Francisco'
    const filename = `Reporte_Microdatos_${modulo === 'biblioteca' ? 'Biblioteca' : 'Estacionamiento'}_${new Date().toISOString().slice(0, 10)}.pdf`
    setIsExportingPdf(true)

    try {
      await ejecutarDescarga({
        titulo: 'Generación de Informe Ejecutivo PDF',
        subtitulo: `${moduloNombre} • Microdatos y auditoría`,
        tipo: 'pdf',
        nombreArchivo: filename,
        tarea: async ({ setProgreso }) => {
          setProgreso(20, 'Registrando evento de auditoría de descarga...')
          try {
            await recordDownloadAudit({
              modulo,
              formato: 'pdf',
              filtro_fecha_inicio: fechaInicio,
              filtro_fecha_fin: fechaFin,
              filtro_detalle: `PDF Completo. Categoría: ${filtroCategoria || 'todas'}, Puerta: ${effectiveDoor || 'todas'}, Horario: ${effectiveRegimen || 'todos'}, Flujo: ${effectiveDireccion || 'todos'}, Búsqueda: ${searchTerm || 'ninguna'}`,
              total_registros: total,
            })
          } catch (e) {
            console.warn('No se pudo registrar la auditoría:', e)
          }

          setProgreso(45, 'Recuperando lote de registros estructurados para el informe...')
          let exportItems: any[] = []
          if (modulo === 'biblioteca') {
            const fullRes = await fetchRawAttendance({
              page: 1,
              pageSize: 200,
              fechaInicio,
              fechaFin,
              door: effectiveDoor,
              searchHash: searchTerm || undefined,
              categoria: filtroCategoria || undefined,
              alcance: effectiveAlcance,
              regimenHorario: effectiveRegimen,
              direccion: effectiveDireccion,
              diasSemana: effectiveDias,
              perfilVisita: effectivePerfil,
              marcajes: effectiveMarcajes,
            })
            exportItems = fullRes.items || []
          } else {
            const fullRes = await fetchRawVehicles({
              page: 1,
              pageSize: 200,
              fechaInicio,
              fechaFin,
              camara: effectiveDoor,
              direccion: effectiveDireccion,
              searchHash: searchTerm || undefined,
              categoria: filtroCategoria || undefined,
              alcance: effectiveAlcance,
              regimenHorario: effectiveRegimen,
              diasSemana: effectiveDias,
              door: effectiveDoor,
            })
            exportItems = fullRes.items || []
          }

          setProgreso(75, 'Compilando documento con diseño institucional UCT...')
          const printWindow = window.open('', '_blank')
          if (!printWindow) {
            throw new Error('La ventana emergente para impresión fue bloqueada por el navegador. Habilite las ventanas emergentes.')
          }

          const title =
            modulo === 'biblioteca'
              ? 'Reporte Completo de Microdatos y Categorización — Biblioteca CSF'
              : 'Reporte Completo de Microdatos y Categorización — Estacionamiento CSF'

          const rowsHtml =
            modulo === 'biblioteca'
              ? exportItems
                  .map(
                    (r: RawAttendanceItem) => `
                <tr>
                  <td>${r.time ? r.time.slice(0, 10) : ''}</td>
                  <td>${r.time && r.time.length >= 19 ? r.time.slice(11, 19) : ''}</td>
                  <td><code>${r.person_id_short}</code></td>
                  <td>${r.door_entrada}</td>
                  <td>${r.door_salida}</td>
                  <td>${r.primera_entrada}${r.entrada_imputada ? ' (Imputada)' : ''}</td>
                  <td>${r.ultima_salida}${r.salida_imputada ? ' (Imputada)' : ''}</td>
                  <td>${r.permanencia_min} min</td>
                  <td>${r.marcajes_totales}</td>
                  <td><span class="badge-cat">${(r.categorias || []).join(', ')}</span></td>
                </tr>`
                  )
                  .join('')
              : exportItems
                  .map(
                    (r: RawVehicleItem) => `
                <tr>
                  <td>${r.time ? r.time.slice(0, 10) : ''}</td>
                  <td>${r.time && r.time.length >= 19 ? r.time.slice(11, 19) : ''}</td>
                  <td><code>${r.patente_short}</code></td>
                  <td>${r.camara}</td>
                  <td>${r.direccion.toUpperCase()}</td>
                  <td>${r.tipo_vehiculo}</td>
                  <td>${r.marca}</td>
                  <td>${r.calidad_lectura}</td>
                  <td><span class="badge-cat">${(r.categorias || []).join(', ')}</span></td>
                </tr>`
                  )
                  .join('')

          const headersHtml =
            modulo === 'biblioteca'
              ? `<th>Fecha</th><th>Hora</th><th>Identificador</th><th>Torniquete Ent.</th><th>Torniquete Sal.</th><th>1ª Entrada</th><th>Última Salida</th><th>Estadía</th><th>Marcajes</th><th>Integridad</th>`
              : `<th>Fecha</th><th>Hora</th><th>Patente</th><th>Cámara</th><th>Dirección</th><th>Tipo</th><th>Marca</th><th>Calidad</th><th>Integridad</th>`

          printWindow.document.write(`
            <!DOCTYPE html>
            <html>
              <head>
                <title>${title}</title>
                <style>
                  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 30px; color: #1e293b; }
                  .header { border-bottom: 2px solid #002B49; padding-bottom: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: flex-end; }
                  h1 { font-size: 18px; color: #002B49; margin: 0; }
                  .subtitle { font-size: 12px; color: #64748b; margin-top: 4px; }
                  .badge { background: #f1f5f9; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: bold; border: 1px solid #cbd5e1; }
                  .stats { display: flex; gap: 20px; margin-bottom: 20px; }
                  .stat-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 16px; }
                  .stat-label { font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 600; }
                  .stat-val { font-size: 16px; font-weight: bold; color: #002B49; margin-top: 2px; }
                  table { width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 15px; }
                  th { background: #002B49; color: white; text-align: left; padding: 7px 8px; font-weight: 600; }
                  td { padding: 6px 8px; border-bottom: 1px solid #e2e8f0; }
                  tr:nth-child(even) { background: #f8fafc; }
                  code { background: #f1f5f9; padding: 2px 4px; border-radius: 4px; font-family: monospace; font-size: 10px; }
                  .badge-cat { font-weight: 600; font-size: 10px; color: #0369a1; }
                  .footer { margin-top: 25px; font-size: 10px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 10px; }
                </style>
              </head>
              <body>
                <div class="header">
                  <div>
                    <h1>${title}</h1>
                    <div class="subtitle">Universidad Católica de Temuco — Campus San Francisco</div>
                  </div>
                  <div class="badge">Período: ${labelPeriodo || `${fechaInicio || ''} a ${fechaFin || ''}`}</div>
                </div>

                <div class="stats">
                  <div class="stat-box">
                    <div class="stat-label">Total Universo Filtrado</div>
                    <div class="stat-val">${total.toLocaleString('es-CL')}</div>
                  </div>
                  <div class="stat-box">
                    <div class="stat-label">Categoría Filtro</div>
                    <div class="stat-val">${filtroCategoria || 'Todas las categorías'}</div>
                  </div>
                  <div class="stat-box">
                    <div class="stat-label">Norma de Protección</div>
                    <div class="stat-val">Ley 21.719 (Seudonimizado)</div>
                  </div>
                </div>

                <table>
                  <thead>
                    <tr>${headersHtml}</tr>
                  </thead>
                  <tbody>
                    ${rowsHtml}
                  </tbody>
                </table>

                <div class="footer">
                  Reporte generado el ${new Date().toLocaleString('es-CL')} — Contiene ${exportItems.length} registros incluidos en el documento.
                </div>
                <script>
                  window.onload = function() { window.print(); }
                </script>
              </body>
            </html>
          `)
          printWindow.document.close()
          setProgreso(98, 'Documento preparado para guardado en PDF.')
          await new Promise(r => setTimeout(r, 300))
        },
      })
    } finally {
      setIsExportingPdf(false)
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden transition-all">
      {/* Barra Superior con Título y Botones de Exportación */}
      <div className="p-4 bg-slate-50/70 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-uct-blue-primary/10 flex items-center justify-center text-uct-blue-primary">
            <Database size={18} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-800 tracking-tight">
                Microdatos y Registros en Crudo — {modulo === 'biblioteca' ? 'Biblioteca' : 'Estacionamiento'}
              </h3>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-50 text-uct-blue-primary border border-blue-200 font-semibold flex items-center gap-1">
                <Shield size={10} />
                <span>Ley 21.719</span>
              </span>
            </div>
            <p className="text-[11px] text-slate-500">
              Todos los registros físicos ({labelPeriodo || 'Período Activo'}) con categorización de calidad y descalces de hardware
            </p>
          </div>
        </div>

        {/* Botones de Exportar */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleExportCSV}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200/80 transition-all cursor-pointer shadow-2xs"
            title="Descargar todos los registros filtrados en formato CSV con columnas de categorización"
          >
            <FileSpreadsheet size={14} />
            <span>Exportar CSV (100% Universo)</span>
          </button>

          {modulo !== 'biblioteca' && (
            <button
              type="button"
              onClick={handleExportPDF}
              disabled={isExportingPdf}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-uct-blue-primary text-white hover:bg-uct-blue-secondary border border-uct-blue-primary transition-all cursor-pointer shadow-2xs disabled:opacity-50"
              title="Descargar e imprimir reporte ejecutivo completo en PDF"
            >
              <FileText size={14} />
              <span>{isExportingPdf ? 'Generando PDF...' : 'Exportar PDF'}</span>
            </button>
          )}

          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-200/60 transition-colors cursor-pointer"
            title="Recargar microdatos"
          >
            <RefreshCw size={14} className={isFetching ? 'animate-spin text-uct-blue-primary' : ''} />
          </button>
        </div>
      </div>

      {/* Barra de Filtros Interactivos Locales */}
      <div className="p-3 bg-white border-b border-slate-100 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-2.5 flex-1">
          {/* Buscador de Identificador / Hash */}
          <div className="relative min-w-[180px]">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder={modulo === 'biblioteca' ? 'Buscar usuario (hash)...' : 'Buscar patente (hash)...'}
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value)
                setPage(1)
              }}
              className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-8 pr-2.5 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-uct-blue-primary transition-colors"
            />
          </div>

          {/* Filtro por Categoría de Integridad */}
          <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1">
            <Tag size={12} className="text-slate-400" />
            <span className="text-[11px] text-slate-500 font-semibold">Integridad:</span>
            <select
              value={filtroCategoria}
              onChange={(e) => {
                setFiltroCategoria(e.target.value)
                setPage(1)
              }}
              className="bg-transparent text-xs text-slate-800 font-semibold focus:outline-none cursor-pointer"
            >
              <option value="">Todas las Categorías</option>
              <option value="conforme">Solo Conformes</option>
              <option value="fuera_de_horario">Fuera de Horario</option>
              {modulo === 'biblioteca' ? (
                <>
                  <option value="sin_salida">Sin Salida (Imputada)</option>
                  <option value="sin_entrada">Sin Entrada (Imputada)</option>
                  <option value="hora_invertida">Hora Invertida (Hardware)</option>
                  <option value="sin_credencial">Sin Credencial (USR-e8f17a68)</option>
                  <option value="marcaje_excesivo">Marcaje Excesivo (5+)</option>
                </>
              ) : (
                <option value="lectura_fallida">Lectura Ilegible / Placa Desconocida</option>
              )}
              <option value="anomalias">Cualquier Anomalía</option>
            </select>
          </div>

          {/* Filtro por Torniquete / Cámara */}
          <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1">
            <Filter size={12} className="text-slate-400" />
            <span className="text-[11px] text-slate-500 font-semibold">
              {modulo === 'biblioteca' ? 'Torniquete:' : 'Cámara:'}
            </span>
            <input
              type="text"
              placeholder="Todos"
              value={filtroExtra}
              onChange={(e) => {
                setFiltroExtra(e.target.value)
                setPage(1)
              }}
              className="bg-transparent text-xs text-slate-800 focus:outline-none w-16"
            />
          </div>

          {/* Filtro por 1ª Entrada & Última Salida (Biblioteca) */}
          {modulo === 'biblioteca' && (
            <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1">
              <span className="text-[11px] text-slate-500 font-semibold">Ciclo:</span>
              <select
                value={filtroDireccion}
                onChange={(e) => {
                  setFiltroDireccion(e.target.value)
                  setPage(1)
                }}
                className="bg-transparent text-xs text-slate-800 font-medium focus:outline-none cursor-pointer"
              >
                <option value="">1ª Ent. / Últ. Salida: Todos</option>
                <option value="completos">Visita regular (Ambas registradas)</option>
                <option value="solo_ingreso">Solo 1ª Entrada (Sin Salida)</option>
                <option value="solo_salida">Solo Última Salida (Sin Entrada)</option>
              </select>
            </div>
          )}

          {/* Filtro por Marcajes (Biblioteca) */}
          {modulo === 'biblioteca' && (
            <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1">
              <span className="text-[11px] text-slate-500 font-semibold">Marcajes:</span>
              <select
                value={filtroMarcajes}
                onChange={(e) => {
                  setFiltroMarcajes(e.target.value)
                  setPage(1)
                }}
                className="bg-transparent text-xs text-slate-800 font-medium focus:outline-none cursor-pointer"
              >
                <option value="">Todos</option>
                <option value="1">1 marcaje</option>
                <option value="2">2 marcajes</option>
                <option value="3-4">3 a 4 marcajes</option>
                <option value="5+">5+ marcajes</option>
              </select>
            </div>
          )}

          {/* Filtro por Dirección (Solo Estacionamiento) */}
          {modulo === 'estacionamiento' && (
            <select
              value={filtroDireccion}
              onChange={(e) => {
                setFiltroDireccion(e.target.value)
                setPage(1)
              }}
              className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 focus:outline-none cursor-pointer"
            >
              <option value="">Todas las direcciones</option>
              <option value="entrada">Solo Entradas</option>
              <option value="salida">Solo Salidas</option>
            </select>
          )}

          {/* Registros por página */}
          <div className="flex items-center gap-1 text-[11px] text-slate-500 ml-auto">
            <span>Mostrar:</span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value))
                setPage(1)
              }}
              className="bg-slate-50 border border-slate-200 rounded-md px-1.5 py-1 text-xs text-slate-700 cursor-pointer"
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
          </div>
        </div>
      </div>

      {/* Barra Horizontal Interactiva de Rango Horario y Rango de Fechas */}
      <div className="px-3 py-2 bg-slate-50/70 border-b border-slate-200/90 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Selector de Rango Horario (Hora Desde - Hasta) */}
          <div className="flex items-center gap-1.5 bg-white border border-slate-200 rounded-lg px-2.5 py-1 shadow-2xs">
            <Clock size={12} className="text-uct-blue-primary" />
            <span className="text-[11px] font-semibold text-slate-600">Rango Horario:</span>
            <input
              type="time"
              value={horaMin}
              onChange={(e) => setHoraMin(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded px-1.5 py-0.5 text-xs text-slate-700 font-mono focus:outline-none"
              title="Hora mínima de marcaje"
            />
            <span className="text-slate-400 text-xs">—</span>
            <input
              type="time"
              value={horaMax}
              onChange={(e) => setHoraMax(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded px-1.5 py-0.5 text-xs text-slate-700 font-mono focus:outline-none"
              title="Hora máxima de marcaje"
            />
            {(horaMin || horaMax) && (
              <button
                type="button"
                onClick={() => {
                  setHoraMin('')
                  setHoraMax('')
                }}
                className="text-slate-400 hover:text-rose-600 p-0.5 rounded cursor-pointer"
                title="Quitar filtro de rango horario"
              >
                <X size={12} />
              </button>
            )}
          </div>

          {/* Presets Rápidos de Franja Horaria */}
          <div className="flex items-center gap-1 text-[11px]">
            <span className="text-slate-400 text-[10px] uppercase font-bold tracking-wider">Franjas:</span>
            <button
              type="button"
              onClick={() => { setHoraMin('08:30'); setHoraMax('13:30') }}
              className={`px-2 py-0.5 rounded border text-[11px] transition-colors cursor-pointer ${
                horaMin === '08:30' && horaMax === '13:30'
                  ? 'bg-uct-blue-primary text-white border-uct-blue-primary font-bold shadow-2xs'
                  : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-100'
              }`}
            >
              Mañana (08:30-13:30)
            </button>
            <button
              type="button"
              onClick={() => { setHoraMin('13:30'); setHoraMax('18:30') }}
              className={`px-2 py-0.5 rounded border text-[11px] transition-colors cursor-pointer ${
                horaMin === '13:30' && horaMax === '18:30'
                  ? 'bg-uct-blue-primary text-white border-uct-blue-primary font-bold shadow-2xs'
                  : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-100'
              }`}
            >
              Tarde (13:30-18:30)
            </button>
            <button
              type="button"
              onClick={() => { setHoraMin('18:30'); setHoraMax('21:00') }}
              className={`px-2 py-0.5 rounded border text-[11px] transition-colors cursor-pointer ${
                horaMin === '18:30' && horaMax === '21:00'
                  ? 'bg-uct-blue-primary text-white border-uct-blue-primary font-bold shadow-2xs'
                  : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-100'
              }`}
            >
              Vespertino (18:30-21:00)
            </button>
          </div>
        </div>

        {/* Sub-rango de Fecha Horizontal */}
        <div className="flex items-center gap-1.5 bg-white border border-slate-200 rounded-lg px-2.5 py-1 shadow-2xs">
          <span className="text-[11px] font-semibold text-slate-600">Sub-rango Fecha:</span>
          <input
            type="date"
            value={fechaSubFiltroInicio}
            onChange={(e) => setFechaSubFiltroInicio(e.target.value)}
            className="bg-slate-50 border border-slate-200 rounded px-1.5 py-0.5 text-xs text-slate-700 font-mono focus:outline-none"
            title="Fecha inicio"
          />
          <span className="text-slate-400 text-xs">—</span>
          <input
            type="date"
            value={fechaSubFiltroFin}
            onChange={(e) => setFechaSubFiltroFin(e.target.value)}
            className="bg-slate-50 border border-slate-200 rounded px-1.5 py-0.5 text-xs text-slate-700 font-mono focus:outline-none"
            title="Fecha fin"
          />
          {(fechaSubFiltroInicio || fechaSubFiltroFin) && (
            <button
              type="button"
              onClick={() => {
                setFechaSubFiltroInicio('')
                setFechaSubFiltroFin('')
              }}
              className="text-slate-400 hover:text-rose-600 p-0.5 rounded cursor-pointer"
              title="Quitar sub-rango de fecha"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Barra de Filtros Excel Activos */}
      {(activeFilterKeys.length > 0 || sortConfig !== null) && (
        <div className="px-3.5 py-2 bg-uct-blue-primary/5 border-b border-uct-blue-primary/10 flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold text-uct-blue-primary flex items-center gap-1 text-[11px]">
              <Filter size={12} />
              <span>Filtros Excel activos ({activeFilterKeys.length}):</span>
            </span>

            {activeFilterKeys.map(([colKey, vals]) => {
              const colTitle = getColumnTitle(colKey)
              return (
                <span
                  key={colKey}
                  className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-white border border-uct-blue-primary/20 text-slate-700 text-[11px] shadow-2xs"
                >
                  <span className="font-bold text-uct-blue-primary">{colTitle}:</span>
                  <span
                    className="max-w-[140px] truncate text-slate-600"
                    title={vals?.join(', ')}
                  >
                    {vals && vals.length === 1 ? vals[0] : `${vals?.length} valores`}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      setColumnFilters((prev) => {
                        const next = { ...prev }
                        delete next[colKey]
                        return next
                      })
                    }
                    className="text-slate-400 hover:text-rose-600 rounded p-0.5 hover:bg-slate-100 cursor-pointer"
                    title="Quitar filtro de esta columna"
                  >
                    <X size={11} />
                  </button>
                </span>
              )
            })}

            {sortConfig && (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-700 text-[11px] shadow-2xs">
                <span className="font-bold text-slate-800">Orden:</span>
                <span>{getColumnTitle(sortConfig.key)}</span>
                <span className="text-slate-500 font-mono text-[10px]">
                  ({sortConfig.direction === 'asc' ? 'Ascendente' : 'Descendente'})
                </span>
                <button
                  type="button"
                  onClick={() => setSortConfig(null)}
                  className="text-slate-400 hover:text-rose-600 rounded p-0.5 hover:bg-slate-100 cursor-pointer"
                  title="Quitar ordenamiento"
                >
                  <X size={11} />
                </button>
              </span>
            )}
          </div>

          <div className="flex items-center gap-2.5 ml-auto">
            <button
              type="button"
              onClick={handleClearAllColumnFilters}
              className="text-[11px] font-semibold text-uct-blue-primary hover:text-uct-blue-secondary hover:underline cursor-pointer flex items-center gap-1"
            >
              <RotateCcw size={11} />
              <span>Limpiar filtros Excel</span>
            </button>
          </div>
        </div>
      )}

      {/* Barra de Resumen y Paginación Superior — Ubicada ARRIBA de los datos */}
      <div className="p-3 bg-slate-50/80 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-600">
        <div className="flex flex-wrap items-center gap-2">
          <span>
            Mostrando <span className="font-bold text-slate-800">{filteredAndSortedRows.length}</span> registros en esta página (Total universo filtrado: <span className="font-bold text-slate-800">{total.toLocaleString('es-CL')}</span>)
          </span>
          {filtroCategoria && (
            <span className="ml-1 text-[11px] text-blue-700 bg-blue-50 px-2 py-0.5 rounded-md border border-blue-200 font-medium">
              Filtro: {filtroCategoria}
            </span>
          )}
          {activeFilterKeys.length > 0 && (
            <span className="ml-1 text-[11px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200 font-semibold">
              Filtros Excel: {activeFilterKeys.length} activos
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 ml-auto">
          <span>
            Página <span className="font-semibold">{page}</span> de <span className="font-semibold">{totalPages}</span>
          </span>

          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="p-1.5 rounded-md border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
              title="Página anterior"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="p-1.5 rounded-md border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
              title="Página siguiente"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Contenedor de la Tabla */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-slate-100/70 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[10px]">
              {modulo === 'biblioteca' ? (
                <>
                  <th className="py-2.5 px-3.5 whitespace-nowrap">
                    <ExcelColumnHeader
                      columnKey="fecha"
                      title="Fecha"
                      sortType="date"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.fecha?.uniqueValues || []}
                      valueCounts={columnStats.fecha?.valueCounts || {}}
                      selectedValues={columnFilters.fecha ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, fecha: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5 whitespace-nowrap">
                    <ExcelColumnHeader
                      columnKey="hora"
                      title="Hora"
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.hora?.uniqueValues || []}
                      valueCounts={columnStats.hora?.valueCounts || {}}
                      selectedValues={columnFilters.hora ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, hora: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5">
                    <ExcelColumnHeader
                      columnKey="person_id_short"
                      title="Identificador"
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.person_id_short?.uniqueValues || []}
                      valueCounts={columnStats.person_id_short?.valueCounts || {}}
                      selectedValues={columnFilters.person_id_short ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, person_id_short: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5 min-w-[170px]">
                    <ExcelColumnHeader
                      columnKey="categorias"
                      title="Categorías & Calidad"
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.categorias?.uniqueValues || []}
                      valueCounts={columnStats.categorias?.valueCounts || {}}
                      selectedValues={columnFilters.categorias ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, categorias: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5">
                    <ExcelColumnHeader
                      columnKey="door_entrada"
                      title="Torniquete Ent."
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.door_entrada?.uniqueValues || []}
                      valueCounts={columnStats.door_entrada?.valueCounts || {}}
                      selectedValues={columnFilters.door_entrada ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, door_entrada: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5">
                    <ExcelColumnHeader
                      columnKey="door_salida"
                      title="Torniquete Sal."
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.door_salida?.uniqueValues || []}
                      valueCounts={columnStats.door_salida?.valueCounts || {}}
                      selectedValues={columnFilters.door_salida ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, door_salida: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5">
                    <ExcelColumnHeader
                      columnKey="primera_entrada"
                      title="1ª Entrada"
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.primera_entrada?.uniqueValues || []}
                      valueCounts={columnStats.primera_entrada?.valueCounts || {}}
                      selectedValues={columnFilters.primera_entrada ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, primera_entrada: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5">
                    <ExcelColumnHeader
                      columnKey="ultima_salida"
                      title="Última Salida"
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.ultima_salida?.uniqueValues || []}
                      valueCounts={columnStats.ultima_salida?.valueCounts || {}}
                      selectedValues={columnFilters.ultima_salida ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, ultima_salida: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5">
                    <ExcelColumnHeader
                      columnKey="permanencia_min"
                      title="Estadía"
                      sortType="number"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.permanencia_min?.uniqueValues || []}
                      valueCounts={columnStats.permanencia_min?.valueCounts || {}}
                      selectedValues={columnFilters.permanencia_min ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, permanencia_min: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5 text-center">
                    <ExcelColumnHeader
                      columnKey="marcajes_totales"
                      title="Marcajes"
                      sortType="number"
                      align="center"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.marcajes_totales?.uniqueValues || []}
                      valueCounts={columnStats.marcajes_totales?.valueCounts || {}}
                      selectedValues={columnFilters.marcajes_totales ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, marcajes_totales: vals }))}
                    />
                  </th>
                </>
              ) : (
                <>
                  <th className="py-2.5 px-3.5 whitespace-nowrap">
                    <ExcelColumnHeader
                      columnKey="fecha"
                      title="Fecha"
                      sortType="date"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.fecha?.uniqueValues || []}
                      valueCounts={columnStats.fecha?.valueCounts || {}}
                      selectedValues={columnFilters.fecha ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, fecha: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5 whitespace-nowrap">
                    <ExcelColumnHeader
                      columnKey="hora"
                      title="Hora"
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.hora?.uniqueValues || []}
                      valueCounts={columnStats.hora?.valueCounts || {}}
                      selectedValues={columnFilters.hora ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, hora: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5">
                    <ExcelColumnHeader
                      columnKey="patente_short"
                      title="Patente"
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.patente_short?.uniqueValues || []}
                      valueCounts={columnStats.patente_short?.valueCounts || {}}
                      selectedValues={columnFilters.patente_short ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, patente_short: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5 min-w-[160px]">
                    <ExcelColumnHeader
                      columnKey="categorias"
                      title="Categorías & Calidad"
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.categorias?.uniqueValues || []}
                      valueCounts={columnStats.categorias?.valueCounts || {}}
                      selectedValues={columnFilters.categorias ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, categorias: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5">
                    <ExcelColumnHeader
                      columnKey="camara"
                      title="Cámara ANPR"
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.camara?.uniqueValues || []}
                      valueCounts={columnStats.camara?.valueCounts || {}}
                      selectedValues={columnFilters.camara ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, camara: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5">
                    <ExcelColumnHeader
                      columnKey="direccion"
                      title="Dirección"
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.direccion?.uniqueValues || []}
                      valueCounts={columnStats.direccion?.valueCounts || {}}
                      selectedValues={columnFilters.direccion ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, direccion: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5">
                    <ExcelColumnHeader
                      columnKey="tipo_vehiculo"
                      title="Tipo Vehículo"
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.tipo_vehiculo?.uniqueValues || []}
                      valueCounts={columnStats.tipo_vehiculo?.valueCounts || {}}
                      selectedValues={columnFilters.tipo_vehiculo ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, tipo_vehiculo: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5">
                    <ExcelColumnHeader
                      columnKey="marca"
                      title="Marca"
                      sortType="text"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.marca?.uniqueValues || []}
                      valueCounts={columnStats.marca?.valueCounts || {}}
                      selectedValues={columnFilters.marca ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, marca: vals }))}
                    />
                  </th>
                  <th className="py-2.5 px-3.5">
                    <ExcelColumnHeader
                      columnKey="color"
                      title="Color"
                      sortType="text"
                      align="left"
                      currentSort={sortConfig}
                      onSortChange={setSortConfig}
                      uniqueValues={columnStats.color?.uniqueValues || []}
                      valueCounts={columnStats.color?.valueCounts || {}}
                      selectedValues={columnFilters.color ?? null}
                      onFilterChange={(vals) => setColumnFilters((prev) => ({ ...prev, color: vals }))}
                    />
                  </th>
                </>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {isLoading ? (
              <tr>
                <td colSpan={modulo === 'biblioteca' ? 10 : 9} className="py-10 text-center text-slate-400">
                  <RefreshCw size={20} className="animate-spin inline-block mr-2 text-uct-blue-primary" />
                  Cargando microdatos...
                </td>
              </tr>
            ) : filteredAndSortedRows.length === 0 ? (
              <tr>
                <td colSpan={modulo === 'biblioteca' ? 10 : 9} className="py-10 text-center text-slate-400">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <p>No se encontraron registros que coincidan con los filtros seleccionados.</p>
                    {(activeFilterKeys.length > 0 || sortConfig !== null) && (
                      <button
                        type="button"
                        onClick={handleClearAllColumnFilters}
                        className="text-xs font-semibold text-uct-blue-primary hover:underline cursor-pointer flex items-center gap-1"
                      >
                        <RotateCcw size={12} />
                        <span>Restablecer filtros de columnas</span>
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ) : modulo === 'biblioteca' ? (
              (filteredAndSortedRows as RawAttendanceItem[]).map((r, idx) => (
                <tr key={`${r.time}-${idx}`} className="hover:bg-blue-50/40 transition-colors">
                  <td className="py-2.5 px-3.5 font-medium text-slate-800 whitespace-nowrap">
                    {r.time ? r.time.slice(0, 10) : '—'}
                  </td>
                  <td className="py-2.5 px-3.5 font-mono text-[11px] text-slate-600 whitespace-nowrap">
                    {r.time && r.time.length >= 19 ? r.time.slice(11, 19) : '—'}
                  </td>
                  <td className="py-2.5 px-3.5 whitespace-nowrap">
                    <span className="font-mono text-[11px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-600 border border-slate-200/60" title={r.person_id_hash}>
                      {r.person_id_short}
                    </span>
                  </td>
                  <td className="py-2.5 px-3.5 min-w-[170px]">
                    {renderCategoryBadges(r.categorias)}
                  </td>
                  <td className="py-2.5 px-3.5 whitespace-nowrap">{renderDoorBadge(r.door_entrada)}</td>
                  <td className="py-2.5 px-3.5 whitespace-nowrap">{renderDoorBadge(r.door_salida)}</td>
                  <td className="py-2.5 px-3.5 text-slate-600 whitespace-nowrap">
                    {r.entrada_imputada ? (
                      <span className="inline-flex items-center gap-1.5 text-[11px] font-mono text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200" title="Entrada estimada algorítmicamente (no registró marcaje físico de entrada)">
                        <span>{r.primera_entrada}</span>
                        <span className="text-[9px] font-sans font-bold text-amber-800 bg-amber-100/90 px-1 py-0.2 rounded uppercase tracking-wider">Imputada</span>
                      </span>
                    ) : (
                      r.primera_entrada
                    )}
                  </td>
                  <td className="py-2.5 px-3.5 text-slate-600 whitespace-nowrap">
                    {r.salida_imputada ? (
                      <span className="inline-flex items-center gap-1.5 text-[11px] font-mono text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200" title="Salida estimada algorítmicamente (no registró marcaje físico de salida en torniquete)">
                        <span>{r.ultima_salida}</span>
                        <span className="text-[9px] font-sans font-bold text-amber-800 bg-amber-100/90 px-1 py-0.2 rounded uppercase tracking-wider">Imputada</span>
                      </span>
                    ) : (
                      r.ultima_salida
                    )}
                  </td>
                  <td className="py-2.5 px-3.5 font-medium text-slate-800 whitespace-nowrap">
                    {r.permanencia_min > 0 ? `${r.permanencia_min} min` : '—'}
                  </td>
                  <td className="py-2.5 px-3.5 text-center">
                    <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-slate-100 text-[11px] font-bold text-slate-700">
                      {r.marcajes_totales}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              (filteredAndSortedRows as RawVehicleItem[]).map((r, idx) => (
                <tr key={`${r.time}-${idx}`} className="hover:bg-blue-50/40 transition-colors">
                  <td className="py-2.5 px-3.5 font-medium text-slate-800 whitespace-nowrap">
                    {r.time ? r.time.slice(0, 10) : '—'}
                  </td>
                  <td className="py-2.5 px-3.5 font-mono text-[11px] text-slate-600 whitespace-nowrap">
                    {r.time && r.time.length >= 19 ? r.time.slice(11, 19) : '—'}
                  </td>
                  <td className="py-2.5 px-3.5 whitespace-nowrap">
                    <span className="font-mono text-[11px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-600 border border-slate-200/60" title={r.patente_hash}>
                      {r.patente_short}
                    </span>
                  </td>
                  <td className="py-2.5 px-3.5 min-w-[160px]">
                    {renderCategoryBadges(r.categorias)}
                  </td>
                  <td className="py-2.5 px-3.5 text-slate-600">{r.camara}</td>
                  <td className="py-2.5 px-3.5 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        r.direccion === 'entrada'
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : 'bg-amber-50 text-amber-700 border border-amber-200'
                      }`}
                    >
                      {r.direccion.toUpperCase()}
                    </span>
                  </td>
                  <td className="py-2.5 px-3.5 text-slate-700">{r.tipo_vehiculo}</td>
                  <td className="py-2.5 px-3.5 text-slate-700">{r.marca}</td>
                  <td className="py-2.5 px-3.5 text-slate-600">{r.color}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Paginación Inferior */}
      <div className="p-3 bg-slate-50/70 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
        <div>
          <span>Mostrando </span>
          <span className="font-bold text-slate-800">{filteredAndSortedRows.length}</span> registros en esta página (Total universo filtrado: <span className="font-bold text-slate-800">{total.toLocaleString('es-CL')}</span>)
          {filtroCategoria && (
            <span className="ml-2 text-[11px] text-blue-700 bg-blue-50 px-2 py-0.5 rounded-md border border-blue-200 font-medium">
              Filtro: {filtroCategoria}
            </span>
          )}
          {activeFilterKeys.length > 0 && (
            <span className="ml-2 text-[11px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200 font-semibold">
              Filtros Excel: {activeFilterKeys.length} activos
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <span>
            Página <span className="font-semibold">{page}</span> de <span className="font-semibold">{totalPages}</span>
          </span>

          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="p-1.5 rounded-md border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="p-1.5 rounded-md border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
