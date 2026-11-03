import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Clock,
  Plus,
  Trash2,
  Edit2,
  Building,
  Car,
  Calendar,
  Sparkles,
} from 'lucide-react'
import {
  fetchHorarios,
  createHorario,
  updateHorario,
  deleteHorario,
  HorarioOperacion,
  HorarioOperacionCreate,
} from '../../api/client'
import { CalendarioContingenciasSection } from './horarios/CalendarioContingenciasSection'
import {
  ModalHorarioOperacion,
  convertirDiasStateAGrupos,
  obtenerEtiquetaDias,
} from './horarios/ModalHorarioOperacion'

const formatIsoDate = (dStr?: string | null): string => {
  if (!dStr) return ''
  try {
    const [y, m, d] = String(dStr).slice(0, 10).split('-')
    if (!y || !m || !d) return String(dStr).slice(0, 10)
    return `${d}/${m}/${y}`
  } catch {
    return String(dStr)
  }
}

const obtenerResumenHorarios = (h: HorarioOperacion) => {
  let diasConfig = h.configuracion_dias
  if (typeof diasConfig === 'string') {
    try {
      diasConfig = JSON.parse(diasConfig)
    } catch {
      diasConfig = null
    }
  }

  if (diasConfig && typeof diasConfig === 'object' && Object.keys(diasConfig).length > 0) {
    const grupos = convertirDiasStateAGrupos(diasConfig)
    return grupos.map((g) => ({
      titulo: obtenerEtiquetaDias(g.dias),
      abierto: g.abierto,
      apertura: g.apertura,
      cierre: g.cierre,
      cierre_dia_siguiente: Boolean(g.cierre_dia_siguiente),
    }))
  }

  return [
    {
      titulo: 'Horario General',
      abierto: true,
      apertura: h.hora_apertura,
      cierre: h.hora_cierre,
      cierre_dia_siguiente: Boolean(h.cierre_dia_siguiente),
    },
  ]
}

export const HorariosSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [selectedEspacio, setSelectedEspacio] = useState<number>(1)
  const [selectedAnio, setSelectedAnio] = useState<number>(2026)
  const [selectedSubespacio, setSelectedSubespacio] = useState<string>('todos')

  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<HorarioOperacion | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const { data: horarios = [], isLoading } = useQuery({
    queryKey: ['horarios-operacion', selectedEspacio, selectedAnio, selectedSubespacio],
    queryFn: () =>
      fetchHorarios({
        espacio_id: selectedEspacio,
        anio: selectedAnio,
        subespacio: selectedSubespacio === 'todos' ? undefined : selectedSubespacio,
      }),
  })

  const invalidarConsultasHorariosYModelos = () => {
    queryClient.invalidateQueries({ queryKey: ['horarios-operacion'] })
    queryClient.invalidateQueries({ queryKey: ['horarios-operacion-scope'] })
    queryClient.invalidateQueries({ queryKey: ['hourly-flow'] })
    queryClient.invalidateQueries({ queryKey: ['vehicle-hourly-flow'] })
    queryClient.invalidateQueries({ queryKey: ['attendance-kpis'] })
    queryClient.invalidateQueries({ queryKey: ['vehicle-kpis'] })
    queryClient.invalidateQueries({ queryKey: ['forecast-attendance'] })
    queryClient.invalidateQueries({ queryKey: ['forecast-parking'] })
    queryClient.invalidateQueries({ queryKey: ['forecast-14days'] })
  }

  const createMutation = useMutation({
    mutationFn: (data: HorarioOperacionCreate) => createHorario(data),
    onSuccess: () => {
      invalidarConsultasHorariosYModelos()
      setIsModalOpen(false)
      setEditingItem(null)
      setFormError(null)
    },
    onError: (err: any) => {
      setFormError(err?.response?.data?.detail || 'Error al registrar horario de operación')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<HorarioOperacionCreate> }) =>
      updateHorario(id, data),
    onSuccess: () => {
      invalidarConsultasHorariosYModelos()
      setIsModalOpen(false)
      setEditingItem(null)
      setFormError(null)
    },
    onError: (err: any) => {
      setFormError(err?.response?.data?.detail || 'Error al actualizar horario')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteHorario(id),
    onSuccess: () => {
      invalidarConsultasHorariosYModelos()
    },
  })

  const handleOpenCreate = () => {
    setEditingItem(null)
    setFormError(null)
    setIsModalOpen(true)
  }

  const handleOpenEdit = (item: HorarioOperacion) => {
    setEditingItem(item)
    setFormError(null)
    setIsModalOpen(true)
  }

  const handleSaveModal = (data: HorarioOperacionCreate) => {
    if (editingItem) {
      updateMutation.mutate({ id: editingItem.id, data })
    } else {
      createMutation.mutate(data)
    }
  }

  return (
    <div className="space-y-6">
      {/* Selector de Espacio y Año */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200/90 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setSelectedEspacio(1)}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition cursor-pointer ${
              selectedEspacio === 1
                ? 'bg-uct-blue-primary text-white shadow-xs'
                : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
            }`}
          >
            <Building size={15} />
            <span>Biblioteca CSF</span>
          </button>
          <button
            type="button"
            onClick={() => setSelectedEspacio(2)}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition cursor-pointer ${
              selectedEspacio === 2
                ? 'bg-uct-blue-primary text-white shadow-xs'
                : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
            }`}
          >
            <Car size={15} />
            <span>Estacionamiento CSF</span>
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-slate-500">
            {selectedEspacio === 1 ? 'Sala:' : 'Sector:'}
          </span>
          <select
            value={selectedSubespacio}
            onChange={(e) => setSelectedSubespacio(e.target.value)}
            className="px-3 py-1.5 text-xs font-bold text-slate-700 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
          >
            {selectedEspacio === 1 ? (
              <>
                <option value="todos">Todas las Salas</option>
                <option value="sala_1">Sala 1: CSF02 (2° Piso)</option>
                <option value="sala_2">Sala 2: CSF04 Pecera (1° Piso)</option>
              </>
            ) : (
              <>
                <option value="todos">Todos los Sectores</option>
                <option value="CSF11">Sector CSF11 — Edificio 11</option>
                <option value="CSF21">Sector CSF21 — Edificio 21</option>
                <option value="CHS01">Sector CHS01 — Hospital Simulación</option>
              </>
            )}
          </select>

          <span className="text-xs font-semibold text-slate-500 ml-1">Año:</span>
          <select
            value={selectedAnio}
            onChange={(e) => setSelectedAnio(parseInt(e.target.value, 10))}
            className="px-3 py-1.5 text-xs font-bold text-slate-700 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none"
          >
            <option value={2025}>2025</option>
            <option value={2026}>2026</option>
            <option value={2027}>2027</option>
          </select>

          <button
            type="button"
            onClick={handleOpenCreate}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-uct-blue-primary hover:bg-uct-blue-hover text-white shadow-xs transition cursor-pointer ml-2"
          >
            <Plus size={14} />
            <span>Nueva Regla de Horario</span>
          </button>
        </div>
      </div>

      {/* Listado de Reglas de Horarios */}
      <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock size={16} className="text-uct-blue-primary" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
              Reglas de Horario Activas ({horarios.length})
            </h3>
          </div>
          <span className="text-[11px] text-slate-500">
            {selectedEspacio === 1 ? 'Biblioteca Campus San Francisco' : 'Estacionamiento Campus San Francisco'} — {selectedAnio}
          </span>
        </div>

        {isLoading ? (
          <div className="p-8 text-center text-xs text-slate-400">Cargando horarios de operación...</div>
        ) : horarios.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400">
            No se han configurado reglas de horario para este espacio en {selectedAnio}.
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {horarios.map((h) => {
              const subespacioLabel =
                h.subespacio === 'sala_1'
                  ? 'Sala 1 (CSF02 2° Piso)'
                  : h.subespacio === 'sala_2'
                  ? 'Sala 2 (CSF04 Pecera 1° Piso)'
                  : h.subespacio === 'CSF11'
                  ? 'Sector CSF11'
                  : h.subespacio === 'CSF21'
                  ? 'Sector CSF21'
                  : h.subespacio === 'CHS01'
                  ? 'Sector CHS01'
                  : 'Todas las Salas / Sectores'

              return (
                <div key={h.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 hover:bg-slate-50/50 transition">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-bold text-slate-900">{h.descripcion}</span>
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md border bg-slate-100 text-slate-800 border-slate-300">
                        {subespacioLabel}
                      </span>
                      <span
                        className={`text-[10px] font-semibold px-2 py-0.5 rounded-md border uppercase ${
                          h.es_continuo_24h || h.tipo_horario === 'extendido_24h'
                            ? 'bg-purple-50 text-purple-700 border-purple-200'
                            : h.tipo_horario === 'historico_regular'
                            ? 'bg-amber-50 text-amber-800 border-amber-200'
                            : 'bg-blue-50 text-blue-700 border-blue-200'
                        }`}
                      >
                        {h.es_continuo_24h || h.tipo_horario === 'extendido_24h'
                          ? 'Campaña 24 Horas'
                          : h.tipo_horario === 'historico_regular'
                          ? 'Histórico Cerrado'
                          : 'Horario Regular'}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-500 flex flex-wrap items-center gap-3">
                      <span>
                        Vigencia:{' '}
                        {h.fecha_inicio && h.fecha_fin
                          ? `${formatIsoDate(h.fecha_inicio)} al ${formatIsoDate(h.fecha_fin)}`
                          : h.fecha_inicio
                          ? `Vigente desde el ${formatIsoDate(h.fecha_inicio)}`
                          : `Todo el año ${h.anio || selectedAnio} (Habitual Permanente)`}
                      </span>
                    </div>

                    {/* Resumen detallado de Horarios Establecidos */}
                    <div className="mt-2 pt-2 border-t border-slate-100 space-y-1">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                        Horarios Establecidos:
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {obtenerResumenHorarios(h).map((grp, i) => (
                          <span
                            key={i}
                            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border ${
                              grp.abierto
                                ? grp.cierre_dia_siguiente
                                  ? 'bg-purple-50 text-purple-900 border-purple-200'
                                  : 'bg-emerald-50 text-emerald-900 border-emerald-200'
                                : 'bg-slate-50 text-slate-500 border-slate-200'
                            }`}
                          >
                            <span className="font-bold text-slate-800">{grp.titulo}:</span>
                            {grp.abierto ? (
                              <span>
                                {grp.apertura} a {grp.cierre} h{' '}
                                {grp.cierre_dia_siguiente && (
                                  <span className="text-purple-700 font-semibold">(Día sig.)</span>
                                )}
                              </span>
                            ) : (
                              <span className="text-slate-400 italic">Cerrado</span>
                            )}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      type="button"
                      onClick={() => handleOpenEdit(h)}
                      className="p-1.5 text-slate-400 hover:text-uct-blue-primary hover:bg-blue-50 rounded-lg transition cursor-pointer"
                      title="Editar regla"
                    >
                      <Edit2 size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (confirm(`¿Eliminar la regla "${h.descripcion}"?`)) {
                          deleteMutation.mutate(h.id)
                        }
                      }}
                      className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition cursor-pointer"
                      title="Eliminar regla"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Calendario Académico Oficial y Contingencias */}
      <CalendarioContingenciasSection selectedAnio={selectedAnio} />

      {/* Modal Crear / Editar Horario */}
      <ModalHorarioOperacion
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        editingItem={editingItem}
        selectedEspacio={selectedEspacio}
        selectedAnio={selectedAnio}
        onSave={handleSaveModal}
        isPending={createMutation.isPending || updateMutation.isPending}
        errorMsg={formError}
      />
    </div>
  )
}
