import React, { useState, useEffect, useMemo } from 'react'
import {
  Clock,
  X,
  Save,
  AlertCircle,
  Sparkles,
  Moon,
  Plus,
  Trash2,
  Check,
  Calendar,
} from 'lucide-react'
import {
  HorarioOperacion,
  HorarioOperacionCreate,
  DiaHorario,
} from '../../../api/client'

export const DIAS_KEYS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'] as const
export type DiaKey = typeof DIAS_KEYS[number]

export const DIAS_LABELS: Record<DiaKey, string> = {
  lunes: 'Lunes',
  martes: 'Martes',
  miercoles: 'Miércoles',
  jueves: 'Jueves',
  viernes: 'Viernes',
  sabado: 'Sábado',
  domingo: 'Domingo',
}

export const DIAS_CORTOS: Record<DiaKey, string> = {
  lunes: 'Lun',
  martes: 'Mar',
  miercoles: 'Mié',
  jueves: 'Jue',
  viernes: 'Vie',
  sabado: 'Sáb',
  domingo: 'Dom',
}

export interface GrupoHorarioUI {
  id: string
  dias: DiaKey[]
  abierto: boolean
  apertura: string
  cierre: string
  cierre_dia_siguiente: boolean
}

const formatearFechaISO = (date: Date): string => {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const obtenerFechaHoyISO = (): string => {
  return formatearFechaISO(new Date())
}

const obtenerFechaFinSugeridaISO = (diasAdelante: number = 26): string => {
  const d = new Date()
  d.setDate(d.getDate() + diasAdelante)
  return formatearFechaISO(d)
}

export const obtenerEtiquetaDias = (dias: DiaKey[]): string => {
  if (dias.length === 0) return 'Sin días seleccionados'
  if (dias.length === 7) return 'Lunes a Domingo (Toda la semana)'

  const ordenados = DIAS_KEYS.filter((d) => dias.includes(d))
  const keysStr = ordenados.join(',')

  if (keysStr === 'lunes,martes,miercoles,jueves') return 'Lunes a Jueves'
  if (keysStr === 'lunes,martes,miercoles,jueves,viernes') return 'Lunes a Viernes'
  if (keysStr === 'sabado,domingo') return 'Fin de Semana (Sábado y Domingo)'
  if (keysStr === 'sabado') return 'Sábado'
  if (keysStr === 'domingo') return 'Domingo'
  if (keysStr === 'viernes') return 'Viernes'

  return ordenados.map((d) => DIAS_CORTOS[d]).join(', ')
}

export const obtenerSubtituloDias = (dias: DiaKey[]): string => {
  const keysStr = DIAS_KEYS.filter((d) => dias.includes(d)).join(',')
  if (keysStr === 'lunes,martes,miercoles,jueves') return 'Lun, Mar, Mié, Jue'
  if (keysStr === 'viernes') return 'Jornada de cierre semanal'
  if (keysStr === 'sabado') return 'Atención de fin de semana'
  if (keysStr === 'domingo') return 'Domingo institucional'
  if (keysStr === 'lunes,martes,miercoles,jueves,viernes') return 'Jornada regular de lunes a viernes'
  if (keysStr === 'sabado,domingo') return 'Fin de semana institucional'
  return dias.map((d) => DIAS_CORTOS[d]).join(', ')
}

export const sincronizarDiasState = (gruposActuales: GrupoHorarioUI[]): Record<string, DiaHorario> => {
  const result: Record<string, DiaHorario> = {}
  DIAS_KEYS.forEach((d) => {
    const grupo = gruposActuales.find((g) => g.dias.includes(d))
    if (grupo) {
      result[d] = {
        abierto: grupo.abierto,
        apertura: grupo.apertura || '08:30',
        cierre: grupo.cierre || '20:30',
        cierre_dia_siguiente: Boolean(grupo.cierre_dia_siguiente),
      }
    } else {
      result[d] = {
        abierto: false,
        apertura: '00:00',
        cierre: '00:00',
        cierre_dia_siguiente: false,
      }
    }
  })
  return result
}

export const convertirDiasStateAGrupos = (dias: Record<string, DiaHorario>): GrupoHorarioUI[] => {
  const grupos: GrupoHorarioUI[] = []
  const asignados = new Set<DiaKey>()

  DIAS_KEYS.forEach((dia, index) => {
    if (asignados.has(dia)) return
    const config = dias[dia] || { abierto: false, apertura: '08:30', cierre: '20:30', cierre_dia_siguiente: false }

    const grupoExistente = grupos.find(
      (g) =>
        g.abierto === config.abierto &&
        g.apertura === config.apertura &&
        g.cierre === config.cierre &&
        Boolean(g.cierre_dia_siguiente) === Boolean(config.cierre_dia_siguiente)
    )

    if (grupoExistente) {
      grupoExistente.dias.push(dia)
      asignados.add(dia)
    } else {
      const nuevoGrupo: GrupoHorarioUI = {
        id: `grupo_${Date.now()}_${index}`,
        dias: [dia],
        abierto: config.abierto,
        apertura: config.apertura || (config.abierto ? '08:30' : '09:00'),
        cierre: config.cierre || (config.abierto ? '20:30' : '14:00'),
        cierre_dia_siguiente: Boolean(config.cierre_dia_siguiente),
      }
      grupos.push(nuevoGrupo)
      asignados.add(dia)
    }
  })

  return grupos
}

const GRUPOS_DEFAULT_BIBLIOTECA: GrupoHorarioUI[] = [
  {
    id: 'grp_lun_jue',
    dias: ['lunes', 'martes', 'miercoles', 'jueves'],
    abierto: true,
    apertura: '08:30',
    cierre: '20:30',
    cierre_dia_siguiente: false,
  },
  {
    id: 'grp_vie',
    dias: ['viernes'],
    abierto: true,
    apertura: '08:30',
    cierre: '19:30',
    cierre_dia_siguiente: false,
  },
  {
    id: 'grp_sab',
    dias: ['sabado'],
    abierto: true,
    apertura: '10:30',
    cierre: '13:30',
    cierre_dia_siguiente: false,
  },
  {
    id: 'grp_dom',
    dias: ['domingo'],
    abierto: false,
    apertura: '09:00',
    cierre: '14:00',
    cierre_dia_siguiente: false,
  },
]

const GRUPOS_DEFAULT_ESTACIONAMIENTO: GrupoHorarioUI[] = [
  {
    id: 'grp_lun_vie',
    dias: ['lunes', 'martes', 'miercoles', 'jueves', 'viernes'],
    abierto: true,
    apertura: '07:00',
    cierre: '22:00',
    cierre_dia_siguiente: false,
  },
  {
    id: 'grp_sab',
    dias: ['sabado'],
    abierto: true,
    apertura: '08:00',
    cierre: '14:00',
    cierre_dia_siguiente: false,
  },
  {
    id: 'grp_dom',
    dias: ['domingo'],
    abierto: false,
    apertura: '08:00',
    cierre: '14:00',
    cierre_dia_siguiente: false,
  },
]

interface Props {
  isOpen: boolean
  onClose: () => void
  editingItem: HorarioOperacion | null
  selectedEspacio: number
  selectedAnio: number
  onSave: (data: HorarioOperacionCreate) => void
  isPending: boolean
  errorMsg: string | null
}

export const ModalHorarioOperacion: React.FC<Props> = ({
  isOpen,
  onClose,
  editingItem,
  selectedEspacio,
  selectedAnio,
  onSave,
  isPending,
  errorMsg,
}) => {
  const [formData, setFormData] = useState<HorarioOperacionCreate>({
    espacio_id: selectedEspacio,
    anio: selectedAnio,
    descripcion: '',
    tipo_horario: 'regular',
    fecha_inicio: obtenerFechaHoyISO(),
    fecha_fin: obtenerFechaFinSugeridaISO(26),
    hora_apertura: '08:30',
    hora_cierre: '20:30',
    cierre_dia_siguiente: false,
    es_continuo_24h: false,
    configuracion_dias: null,
    subespacio: 'todos',
    activo: true,
  })

  const [grupos, setGrupos] = useState<GrupoHorarioUI[]>(GRUPOS_DEFAULT_BIBLIOTECA)
  const [isExceptionRange, setIsExceptionRange] = useState(false)
  const [expandedGroupDays, setExpandedGroupDays] = useState<string | null>(null)

  useEffect(() => {
    if (editingItem) {
      setFormData({
        espacio_id: editingItem.espacio_id,
        anio: editingItem.anio,
        descripcion: editingItem.descripcion,
        tipo_horario: editingItem.tipo_horario || 'regular',
        fecha_inicio: editingItem.fecha_inicio ? String(editingItem.fecha_inicio).slice(0, 10) : obtenerFechaHoyISO(),
        fecha_fin: editingItem.fecha_fin ? String(editingItem.fecha_fin).slice(0, 10) : obtenerFechaFinSugeridaISO(26),
        hora_apertura: editingItem.hora_apertura,
        hora_cierre: editingItem.hora_cierre,
        cierre_dia_siguiente: editingItem.cierre_dia_siguiente,
        es_continuo_24h: editingItem.es_continuo_24h,
        configuracion_dias: editingItem.configuracion_dias,
        subespacio: editingItem.subespacio || 'todos',
        activo: editingItem.activo,
      })
      setIsExceptionRange(Boolean(editingItem.fecha_inicio && editingItem.fecha_fin))
      if (editingItem.configuracion_dias) {
        setGrupos(convertirDiasStateAGrupos(editingItem.configuracion_dias))
      } else {
        const defaults = selectedEspacio === 1 ? GRUPOS_DEFAULT_BIBLIOTECA : GRUPOS_DEFAULT_ESTACIONAMIENTO
        setGrupos(defaults)
      }
    } else {
      const defaults = selectedEspacio === 1 ? GRUPOS_DEFAULT_BIBLIOTECA : GRUPOS_DEFAULT_ESTACIONAMIENTO
      setGrupos(defaults)
      setFormData({
        espacio_id: selectedEspacio,
        anio: selectedAnio,
        descripcion: '',
        tipo_horario: 'regular',
        fecha_inicio: obtenerFechaHoyISO(),
        fecha_fin: obtenerFechaFinSugeridaISO(26),
        hora_apertura: selectedEspacio === 1 ? '08:30' : '07:00',
        hora_cierre: selectedEspacio === 1 ? '20:30' : '22:00',
        cierre_dia_siguiente: false,
        es_continuo_24h: false,
        configuracion_dias: null,
        subespacio: 'todos',
        activo: true,
      })
      setIsExceptionRange(false)
    }
  }, [editingItem, selectedEspacio, selectedAnio, isOpen])

  const diasAsignados = useMemo(() => {
    return new Set(grupos.flatMap((g) => g.dias))
  }, [grupos])

  const diasNoAsignados = useMemo(() => {
    return DIAS_KEYS.filter((d) => !diasAsignados.has(d))
  }, [diasAsignados])

  if (!isOpen) return null

  const handleApplyPreset = (
    preset:
      | 'biblioteca_oficial'
      | 'sala1_regular'
      | 'examenes_24h'
      | 'estacionamiento_oficial'
      | 'estacionamiento_csf11'
      | 'estacionamiento_chs01'
  ) => {
    if (preset === 'biblioteca_oficial') {
      const gruposBib: GrupoHorarioUI[] = [
        {
          id: 'g_lun_jue',
          dias: ['lunes', 'martes', 'miercoles', 'jueves'],
          abierto: true,
          apertura: '08:30',
          cierre: '20:30',
          cierre_dia_siguiente: false,
        },
        {
          id: 'g_vie',
          dias: ['viernes'],
          abierto: true,
          apertura: '08:30',
          cierre: '19:30',
          cierre_dia_siguiente: false,
        },
        {
          id: 'g_sab',
          dias: ['sabado'],
          abierto: true,
          apertura: '10:30',
          cierre: '13:30',
          cierre_dia_siguiente: false,
        },
        {
          id: 'g_dom',
          dias: ['domingo'],
          abierto: false,
          apertura: '09:00',
          cierre: '14:00',
          cierre_dia_siguiente: false,
        },
      ]
      setFormData((prev) => ({
        ...prev,
        descripcion: 'Horario Oficial Biblioteca CSF (Lunes a Sábado)',
        tipo_horario: 'regular',
        subespacio: 'todos',
        fecha_inicio: null,
        fecha_fin: null,
        hora_apertura: '08:30',
        hora_cierre: '20:30',
        es_continuo_24h: false,
        cierre_dia_siguiente: false,
      }))
      setGrupos(gruposBib)
      setIsExceptionRange(false)
    } else if (preset === 'sala1_regular') {
      const gruposS1: GrupoHorarioUI[] = [
        {
          id: 'g_lun_jue',
          dias: ['lunes', 'martes', 'miercoles', 'jueves'],
          abierto: true,
          apertura: '08:30',
          cierre: '20:00',
          cierre_dia_siguiente: false,
        },
        {
          id: 'g_vie',
          dias: ['viernes'],
          abierto: true,
          apertura: '08:30',
          cierre: '19:00',
          cierre_dia_siguiente: false,
        },
        {
          id: 'g_sab',
          dias: ['sabado'],
          abierto: true,
          apertura: '10:00',
          cierre: '13:00',
          cierre_dia_siguiente: false,
        },
        {
          id: 'g_dom',
          dias: ['domingo'],
          abierto: false,
          apertura: '09:00',
          cierre: '14:00',
          cierre_dia_siguiente: false,
        },
      ]
      setFormData((prev) => ({
        ...prev,
        descripcion: 'Horario Sala 1: CSF02 (2° Piso)',
        tipo_horario: 'regular',
        subespacio: 'sala_1',
        fecha_inicio: null,
        fecha_fin: null,
        hora_apertura: '08:30',
        hora_cierre: '20:00',
        es_continuo_24h: false,
        cierre_dia_siguiente: false,
      }))
      setGrupos(gruposS1)
      setIsExceptionRange(false)
    } else if (preset === 'examenes_24h') {
      const grupos24h: GrupoHorarioUI[] = [
        {
          id: 'g_lun_jue',
          dias: ['lunes', 'martes', 'miercoles', 'jueves'],
          abierto: true,
          apertura: '08:30',
          cierre: '07:00',
          cierre_dia_siguiente: true,
        },
        {
          id: 'g_vie',
          dias: ['viernes'],
          abierto: true,
          apertura: '08:30',
          cierre: '06:00',
          cierre_dia_siguiente: true,
        },
        {
          id: 'g_sab',
          dias: ['sabado'],
          abierto: true,
          apertura: '10:30',
          cierre: '15:00',
          cierre_dia_siguiente: false,
        },
        {
          id: 'g_dom',
          dias: ['domingo'],
          abierto: false,
          apertura: '10:00',
          cierre: '14:00',
          cierre_dia_siguiente: false,
        },
      ]
      setFormData((prev) => ({
        ...prev,
        descripcion: 'Sala 2 Pecera — Campaña 24 Horas Exámenes',
        tipo_horario: 'extendido_24h',
        subespacio: 'sala_2',
        fecha_inicio: obtenerFechaHoyISO(),
        fecha_fin: obtenerFechaFinSugeridaISO(26),
        hora_apertura: '08:30',
        hora_cierre: '07:00',
        es_continuo_24h: true,
        cierre_dia_siguiente: true,
      }))
      setGrupos(grupos24h)
      setIsExceptionRange(true)
    } else if (preset === 'estacionamiento_oficial') {
      const gruposEst: GrupoHorarioUI[] = [
        {
          id: 'g_lun_vie',
          dias: ['lunes', 'martes', 'miercoles', 'jueves', 'viernes'],
          abierto: true,
          apertura: '07:00',
          cierre: '22:00',
          cierre_dia_siguiente: false,
        },
        {
          id: 'g_sab',
          dias: ['sabado'],
          abierto: true,
          apertura: '08:00',
          cierre: '14:00',
          cierre_dia_siguiente: false,
        },
        {
          id: 'g_dom',
          dias: ['domingo'],
          abierto: false,
          apertura: '08:00',
          cierre: '14:00',
          cierre_dia_siguiente: false,
        },
      ]
      setFormData((prev) => ({
        ...prev,
        descripcion: 'Horario Operativo Estacionamiento CSF (General)',
        tipo_horario: 'regular',
        subespacio: 'todos',
        fecha_inicio: null,
        fecha_fin: null,
        hora_apertura: '07:00',
        hora_cierre: '22:00',
        es_continuo_24h: false,
        cierre_dia_siguiente: false,
      }))
      setGrupos(gruposEst)
      setIsExceptionRange(false)
    } else if (preset === 'estacionamiento_csf11') {
      const gruposCsf11: GrupoHorarioUI[] = [
        {
          id: 'g_lun_jue',
          dias: ['lunes', 'martes', 'miercoles', 'jueves'],
          abierto: true,
          apertura: '07:30',
          cierre: '20:30',
          cierre_dia_siguiente: false,
        },
        {
          id: 'g_vie',
          dias: ['viernes'],
          abierto: true,
          apertura: '07:30',
          cierre: '20:00',
          cierre_dia_siguiente: false,
        },
        {
          id: 'g_sab',
          dias: ['sabado'],
          abierto: true,
          apertura: '08:00',
          cierre: '13:30',
          cierre_dia_siguiente: false,
        },
        {
          id: 'g_dom',
          dias: ['domingo'],
          abierto: false,
          apertura: '08:00',
          cierre: '13:30',
          cierre_dia_siguiente: false,
        },
      ]
      setFormData((prev) => ({
        ...prev,
        descripcion: 'Horario Sector CSF11 — Edificio 11',
        tipo_horario: 'regular',
        subespacio: 'CSF11',
        fecha_inicio: null,
        fecha_fin: null,
        hora_apertura: '07:30',
        hora_cierre: '20:30',
        es_continuo_24h: false,
        cierre_dia_siguiente: false,
      }))
      setGrupos(gruposCsf11)
      setIsExceptionRange(false)
    } else if (preset === 'estacionamiento_chs01') {
      const gruposChs01: GrupoHorarioUI[] = [
        {
          id: 'g_todos',
          dias: ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'],
          abierto: true,
          apertura: '06:30',
          cierre: '23:30',
          cierre_dia_siguiente: false,
        },
      ]
      setFormData((prev) => ({
        ...prev,
        descripcion: 'Sector CHS01 Hospital de Simulación — Turno Clínico Extendido',
        tipo_horario: 'regular',
        subespacio: 'CHS01',
        fecha_inicio: null,
        fecha_fin: null,
        hora_apertura: '06:30',
        hora_cierre: '23:30',
        es_continuo_24h: false,
        cierre_dia_siguiente: false,
      }))
      setGrupos(gruposChs01)
      setIsExceptionRange(false)
    }
  }

  const handleToggleDiaInGrupo = (grupoId: string, dia: DiaKey) => {
    setGrupos((prev) =>
      prev.map((g) => {
        if (g.id === grupoId) {
          if (g.dias.includes(dia)) {
            return { ...g, dias: g.dias.filter((d) => d !== dia) }
          } else {
            return { ...g, dias: [...g.dias, dia] }
          }
        } else {
          if (g.dias.includes(dia)) {
            return { ...g, dias: g.dias.filter((d) => d !== dia) }
          }
          return g
        }
      })
    )
  }

  const handleUpdateGrupo = (grupoId: string, updates: Partial<GrupoHorarioUI>) => {
    setGrupos((prev) =>
      prev.map((g) => (g.id === grupoId ? { ...g, ...updates } : g))
    )
  }

  const handleAddGrupo = () => {
    const unassigned = diasNoAsignados
    const nuevo: GrupoHorarioUI = {
      id: `grupo_${Date.now()}`,
      dias: unassigned.length > 0 ? unassigned : [],
      abierto: true,
      apertura: '08:30',
      cierre: '20:30',
      cierre_dia_siguiente: false,
    }
    setGrupos((prev) => [...prev, nuevo])
  }

  const handleRemoveGrupo = (grupoId: string) => {
    if (grupos.length <= 1) return
    setGrupos((prev) => prev.filter((g) => g.id !== grupoId))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const diasConfig = sincronizarDiasState(grupos)
    const primerGrupoAbierto = grupos.find((g) => g.abierto && g.dias.length > 0) || grupos[0]

    const payload: HorarioOperacionCreate = {
      ...formData,
      hora_apertura: primerGrupoAbierto?.apertura || '08:30',
      hora_cierre: primerGrupoAbierto?.cierre || '20:30',
      cierre_dia_siguiente: Boolean(primerGrupoAbierto?.cierre_dia_siguiente),
      fecha_inicio: isExceptionRange && formData.fecha_inicio ? formData.fecha_inicio : null,
      fecha_fin: isExceptionRange && formData.fecha_fin ? formData.fecha_fin : null,
      configuracion_dias: diasConfig,
    }
    onSave(payload)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-2xl w-full my-8 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock size={18} className="text-uct-blue-primary" />
            <h3 className="text-sm font-bold text-slate-900">
              {editingItem ? 'Editar Horario / Período' : 'Nuevo Horario o Período Operativo'}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-600 rounded-lg transition cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4 max-h-[82vh] overflow-y-auto">
          {errorMsg && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-700 flex items-center gap-2">
              <AlertCircle size={15} />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Plantillas Rápidas */}
          <div className="p-3 bg-blue-50/60 rounded-xl border border-blue-100">
            <span className="text-[11px] font-bold text-uct-blue-primary uppercase tracking-wider block mb-2 flex items-center gap-1.5">
              <Sparkles size={13} />
              <span>Plantillas Rápidas Institucionales</span>
            </span>
            <div className="flex flex-wrap gap-2">
              {selectedEspacio === 1 ? (
                <>
                  <button
                    type="button"
                    onClick={() => handleApplyPreset('biblioteca_oficial')}
                    className="px-2.5 py-1 bg-white hover:bg-blue-50 border border-blue-200 rounded-lg text-xs font-medium text-slate-700 transition cursor-pointer shadow-2xs"
                  >
                    Regular Biblioteca UCT (General)
                  </button>
                  <button
                    type="button"
                    onClick={() => handleApplyPreset('sala1_regular')}
                    className="px-2.5 py-1 bg-white hover:bg-blue-50 border border-blue-200 rounded-lg text-xs font-medium text-slate-700 transition cursor-pointer shadow-2xs"
                  >
                    Sala 1 CSF02 Regular (08:30 - 20:00)
                  </button>
                  <button
                    type="button"
                    onClick={() => handleApplyPreset('examenes_24h')}
                    className="px-2.5 py-1 bg-white hover:bg-purple-50 border border-purple-200 rounded-lg text-xs font-semibold text-purple-800 transition cursor-pointer shadow-2xs"
                  >
                    Campaña 24 Horas Exámenes Sala 2 Pecera
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => handleApplyPreset('estacionamiento_oficial')}
                    className="px-2.5 py-1 bg-white hover:bg-emerald-50 border border-emerald-200 rounded-lg text-xs font-medium text-slate-700 transition cursor-pointer shadow-2xs"
                  >
                    Estacionamiento CSF (General 07:00 a 22:00)
                  </button>
                  <button
                    type="button"
                    onClick={() => handleApplyPreset('estacionamiento_csf11')}
                    className="px-2.5 py-1 bg-white hover:bg-blue-50 border border-blue-200 rounded-lg text-xs font-medium text-slate-700 transition cursor-pointer shadow-2xs"
                  >
                    Sector CSF11 Edificio 11
                  </button>
                  <button
                    type="button"
                    onClick={() => handleApplyPreset('estacionamiento_chs01')}
                    className="px-2.5 py-1 bg-white hover:bg-teal-50 border border-teal-200 rounded-lg text-xs font-medium text-teal-800 transition cursor-pointer shadow-2xs"
                  >
                    Sector CHS01 Hospital Simulación (Turno Clínico)
                  </button>
                </>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Descripción de la Regla</label>
              <input
                type="text"
                required
                placeholder="Ej. Horario Campaña Exámenes 24 Horas"
                value={formData.descripcion}
                onChange={(e) => setFormData((prev) => ({ ...prev, descripcion: e.target.value }))}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-uct-blue-primary/20 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                {selectedEspacio === 1 ? 'Sala o Espacio de Biblioteca' : 'Sector de Estacionamiento'}
              </label>
              <select
                value={formData.subespacio || 'todos'}
                onChange={(e) => setFormData((prev) => ({ ...prev, subespacio: e.target.value }))}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-uct-blue-primary/20 focus:outline-none"
              >
                {selectedEspacio === 1 ? (
                  <>
                    <option value="todos">Todas las Salas (General)</option>
                    <option value="sala_1">Sala 1: CSF02 (2° Piso)</option>
                    <option value="sala_2">Sala 2: CSF04 Pecera (1° Piso)</option>
                  </>
                ) : (
                  <>
                    <option value="todos">Todos los Sectores (General)</option>
                    <option value="CSF11">Sector CSF11 — Edificio 11</option>
                    <option value="CSF21">Sector CSF21 — Edificio 21</option>
                    <option value="CHS01">Sector CHS01 — Hospital de Simulación</option>
                  </>
                )}
              </select>
            </div>
          </div>

          {editingItem && editingItem.tipo_horario === 'regular' && (
            <div className="p-3 bg-amber-50/80 border border-amber-200 rounded-xl text-[11px] text-amber-900">
              <strong>Trazabilidad histórica activa:</strong> Si modifica las horas o días de este horario habitual, el sistema conservará automáticamente un registro histórico cerrado con el horario que regía en fechas anteriores, aplicando el nuevo horario desde hoy en adelante para no distorsionar métricas ni modelos predictivos.
            </div>
          )}

          {/* Modalidad de Vigencia */}
          <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-bold text-slate-800">Modalidad de Vigencia</span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    setIsExceptionRange(false)
                    setFormData((prev) => ({
                      ...prev,
                      tipo_horario: 'regular',
                      es_continuo_24h: false,
                    }))
                  }}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition cursor-pointer ${
                    !isExceptionRange
                      ? 'bg-uct-blue-primary text-white shadow-2xs'
                      : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  Horario Habitual Permanente
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsExceptionRange(true)
                    setFormData((prev) => ({
                      ...prev,
                      tipo_horario: 'extendido_24h',
                      es_continuo_24h: true,
                      fecha_inicio: prev.fecha_inicio ? String(prev.fecha_inicio).slice(0, 10) : obtenerFechaHoyISO(),
                      fecha_fin: prev.fecha_fin ? String(prev.fecha_fin).slice(0, 10) : obtenerFechaFinSugeridaISO(26),
                    }))
                  }}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition cursor-pointer ${
                    isExceptionRange
                      ? 'bg-purple-700 text-white shadow-2xs'
                      : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  Campaña 24 Horas / Régimen Exámenes
                </button>
              </div>
            </div>

            {isExceptionRange && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-slate-200/80">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1 flex items-center gap-1">
                    <Calendar size={12} className="text-purple-700" />
                    <span>Fecha de Inicio</span>
                  </label>
                  <input
                    type="date"
                    required={isExceptionRange}
                    value={formData.fecha_inicio ? String(formData.fecha_inicio).slice(0, 10) : obtenerFechaHoyISO()}
                    onChange={(e) => setFormData((prev) => ({ ...prev, fecha_inicio: e.target.value }))}
                    className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-medium text-slate-800"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1 flex items-center gap-1">
                    <Calendar size={12} className="text-purple-700" />
                    <span>Fecha de Término</span>
                  </label>
                  <input
                    type="date"
                    required={isExceptionRange}
                    value={formData.fecha_fin ? String(formData.fecha_fin).slice(0, 10) : obtenerFechaFinSugeridaISO(26)}
                    onChange={(e) => setFormData((prev) => ({ ...prev, fecha_fin: e.target.value }))}
                    className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-medium text-slate-800"
                  />
                </div>
                <div className="flex flex-col justify-end">
                  <div className="p-2 bg-purple-50 border border-purple-200 rounded-lg text-[11px] text-purple-900 font-medium">
                    <span className="font-bold flex items-center gap-1 text-purple-950">
                      <Moon size={12} className="text-purple-700" /> Campaña 24 Horas Activa
                    </span>
                    <span className="text-[10px] text-purple-800 block mt-0.5 leading-tight">
                      Habilita la comparativa nocturna (Delta 24h) y activa el turno extendido en Prophet.
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Configuración Dinámica de Horarios por Grupos de Días */}
          <div className="space-y-3 pt-2 border-t border-slate-100">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-bold text-slate-800 block">
                  Reglas de Horario por Días de la Semana
                </span>
                <span className="text-[11px] text-slate-500 block">
                  Selecciona libremente qué días aplican a cada horario. Puedes añadir domingos con horario o definir si cierran.
                </span>
              </div>
              <button
                type="button"
                onClick={handleAddGrupo}
                className="flex items-center gap-1 px-2.5 py-1.5 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-lg text-xs font-bold text-uct-blue-primary transition cursor-pointer"
              >
                <Plus size={13} />
                <span>Agregar Grupo</span>
              </button>
            </div>

            {/* Nota Informativa sobre Cierre al Día Siguiente */}
            <div className="p-2.5 bg-purple-50/90 border border-purple-200/90 rounded-xl text-xs text-purple-900 flex items-start gap-2">
              <Moon size={15} className="text-purple-700 shrink-0 mt-0.5" />
              <p className="text-[11px] leading-relaxed text-purple-900">
                <strong>¿Qué significa «Cierra día sig.»?</strong> Márcalo cuando la jornada cruce la medianoche (ej. abre a las 08:30 y cierra a las 06:00 o 07:00 AM del día siguiente). Esto valida los accesos de madrugada en la analítica sin generar falsas intrusiones fuera de horario.
              </p>
            </div>

            {/* Lista Dinámica de Grupos (Diseño Limpio por Bloques Operativos) */}
            <div className="space-y-2.5">
              {grupos.map((grupo) => {
                const tituloGrupo = obtenerEtiquetaDias(grupo.dias)
                const subtituloGrupo = obtenerSubtituloDias(grupo.dias)
                const isExpanded = expandedGroupDays === grupo.id

                return (
                  <div
                    key={grupo.id}
                    className={`p-3.5 rounded-xl border transition ${
                      grupo.abierto
                        ? 'bg-white border-slate-200 shadow-2xs'
                        : 'bg-slate-50/80 border-slate-200 text-slate-600'
                    }`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      {/* Izquierda: Badge de Estado + Nombre del Período / Subtítulo */}
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={() => handleUpdateGrupo(grupo.id, { abierto: !grupo.abierto })}
                          className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase transition cursor-pointer tracking-wider ${
                            grupo.abierto
                              ? 'bg-emerald-100 text-emerald-800 border border-emerald-300 hover:bg-emerald-200'
                              : 'bg-rose-100 text-rose-800 border border-rose-300 hover:bg-rose-200'
                          }`}
                        >
                          {grupo.abierto ? 'Abierto' : 'Cerrado'}
                        </button>

                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-slate-900">{tituloGrupo}</span>
                            <button
                              type="button"
                              onClick={() => setExpandedGroupDays(isExpanded ? null : grupo.id)}
                              className="text-[10px] text-slate-400 hover:text-uct-blue-primary transition cursor-pointer underline"
                              title="Personalizar días de este bloque"
                            >
                              {isExpanded ? 'Ocultar días' : 'Editar días'}
                            </button>
                            {grupos.length > 1 && (
                              <button
                                type="button"
                                title="Eliminar este bloque"
                                onClick={() => handleRemoveGrupo(grupo.id)}
                                className="p-0.5 text-slate-300 hover:text-rose-600 transition cursor-pointer"
                              >
                                <Trash2 size={12} />
                              </button>
                            )}
                          </div>
                          <span className="text-[11px] text-slate-500 block">
                            {subtituloGrupo}
                          </span>
                        </div>
                      </div>

                      {/* Derecha: Horarios o Estado Cerrado */}
                      {grupo.abierto ? (
                        <div className="flex flex-wrap items-center gap-3 text-xs">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[11px] text-slate-500 font-semibold">De:</span>
                            <input
                              type="time"
                              value={grupo.apertura}
                              onChange={(e) => handleUpdateGrupo(grupo.id, { apertura: e.target.value })}
                              className="px-2.5 py-1 bg-white border border-slate-200 rounded-lg text-xs font-medium text-slate-800 focus:ring-2 focus:ring-uct-blue-primary/20 focus:outline-none"
                              required={grupo.abierto}
                            />
                          </div>

                          <div className="flex items-center gap-1.5">
                            <span className="text-[11px] text-slate-500 font-semibold">Hasta:</span>
                            <input
                              type="time"
                              value={grupo.cierre}
                              onChange={(e) => handleUpdateGrupo(grupo.id, { cierre: e.target.value })}
                              className="px-2.5 py-1 bg-white border border-slate-200 rounded-lg text-xs font-medium text-slate-800 focus:ring-2 focus:ring-uct-blue-primary/20 focus:outline-none"
                              required={grupo.abierto}
                            />
                          </div>

                          <label className="flex items-center gap-1.5 cursor-pointer px-2 py-1 rounded-lg hover:bg-slate-50 text-xs font-medium text-slate-700 transition">
                            <input
                              type="checkbox"
                              checked={Boolean(grupo.cierre_dia_siguiente)}
                              onChange={(e) => handleUpdateGrupo(grupo.id, { cierre_dia_siguiente: e.target.checked })}
                              className="rounded border-slate-300 text-purple-600 focus:ring-purple-200"
                            />
                            <span>Cierra día sig.</span>
                          </label>
                        </div>
                      ) : (
                        <div className="flex items-center gap-3 text-xs">
                          <span className="italic text-slate-400 text-xs">
                            Sin atención / Cerrado todo el día
                          </span>
                          <button
                            type="button"
                            onClick={() => handleUpdateGrupo(grupo.id, { abierto: true })}
                            className="text-xs font-semibold text-uct-blue-primary hover:underline cursor-pointer"
                          >
                            + Habilitar horario
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Selector desplegable de días (solo si el usuario pulsa 'Editar días') */}
                    {isExpanded && (
                      <div className="pt-3 mt-3 border-t border-slate-100 animate-in fade-in duration-150">
                        <div className="text-[10px] font-semibold text-slate-500 mb-1.5 uppercase tracking-wider">
                          Días asignados a este horario (haz clic para activar o transferir):
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {DIAS_KEYS.map((dia) => {
                            const estaEnEsteGrupo = grupo.dias.includes(dia)
                            const estaEnOtroGrupo = !estaEnEsteGrupo && diasAsignados.has(dia)
                            const estaSinAsignar = !estaEnEsteGrupo && !estaEnOtroGrupo

                            return (
                              <button
                                key={dia}
                                type="button"
                                onClick={() => handleToggleDiaInGrupo(grupo.id, dia)}
                                className={`px-2.5 py-1 rounded-lg text-xs font-bold transition cursor-pointer flex items-center gap-1 ${
                                  estaEnEsteGrupo
                                    ? 'bg-uct-blue-primary text-white shadow-2xs'
                                    : estaSinAsignar
                                    ? 'bg-amber-50 text-amber-800 border border-dashed border-amber-400 hover:bg-amber-100'
                                    : 'bg-slate-100 text-slate-400 border border-slate-200 hover:text-slate-700 hover:border-slate-300'
                                }`}
                              >
                                {estaEnEsteGrupo && <Check size={12} strokeWidth={3} />}
                                {estaSinAsignar && <Plus size={11} />}
                                <span>{DIAS_LABELS[dia]}</span>
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Aviso de Días Pendientes por Asignar */}
            {diasNoAsignados.length > 0 && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 flex flex-wrap items-center justify-between gap-2">
                <span>
                  Días sin horario asignado:{' '}
                  <strong>{diasNoAsignados.map((d) => DIAS_LABELS[d]).join(', ')}</strong> (quedarán cerrados si no los asignas).
                </span>
                <button
                  type="button"
                  onClick={handleAddGrupo}
                  className="px-2.5 py-1 bg-amber-600 hover:bg-amber-700 text-white font-bold rounded-lg text-[11px] transition cursor-pointer shadow-2xs"
                >
                  Crear regla con estos días
                </button>
              </div>
            )}
          </div>

          <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100 transition cursor-pointer"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="flex items-center gap-2 px-4 py-2 bg-uct-blue-primary text-white rounded-xl text-xs font-semibold hover:bg-blue-700 transition shadow-xs cursor-pointer disabled:opacity-50"
            >
              <Save size={14} />
              <span>{editingItem ? 'Guardar Cambios' : 'Registrar Regla'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
