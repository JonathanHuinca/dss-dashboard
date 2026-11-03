import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Users,
  Building,
  Car,
  Save,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  Info,
  ShieldCheck,
  DoorClosed,
  Layers,
} from 'lucide-react'
import {
  fetchEspacios,
  updateEspacioCapacidad,
  updateSalaCapacidad,
  EspacioInfo,
  SalaBibliotecaItem,
} from '../../api/client'
import { useAuth } from '../../context/AuthContext'
import { useSalasBiblioteca } from '../../hooks/useAttendance'
import { SectoresEstacionamientoSection } from './admin/SectoresEstacionamientoSection'

export const AforoSection: React.FC = () => {
  const { isSuperAdmin, hasDatasetAccess } = useAuth()
  const queryClient = useQueryClient()

  const [capacidadesEdit, setCapacidadesEdit] = useState<Record<number, number>>({})
  const [capacidadesSalasEdit, setCapacidadesSalasEdit] = useState<Record<number, number>>({})
  const [successMsg, setSuccessMsg] = useState<Record<number, string | null>>({})
  const [errorMsg, setErrorMsg] = useState<Record<number, string | null>>({})
  const [salaSuccessMsg, setSalaSuccessMsg] = useState<string | null>(null)
  const [salaErrorMsg, setSalaErrorMsg] = useState<string | null>(null)

  const { data: espacios = [], isLoading, isError, refetch } = useQuery<EspacioInfo[]>({
    queryKey: ['admin-espacios'],
    queryFn: fetchEspacios,
  })

  const { data: salasBiblioteca = [], refetch: refetchSalas } = useSalasBiblioteca(1)

  const updateMutation = useMutation({
    mutationFn: ({ espacioId, capacidad }: { espacioId: number; capacidad: number }) =>
      updateEspacioCapacidad(espacioId, capacidad),
    onSuccess: (updatedEspacio) => {
      queryClient.invalidateQueries({ queryKey: ['admin-espacios'] })
      queryClient.invalidateQueries({ queryKey: ['realtime-occupancy'] })
      queryClient.invalidateQueries({ queryKey: ['parking-occupancy'] })
      queryClient.invalidateQueries({ queryKey: ['attendance-kpis'] })
      queryClient.invalidateQueries({ queryKey: ['vehicle-kpis'] })
      queryClient.invalidateQueries({ queryKey: ['hourly-attendance'] })
      queryClient.invalidateQueries({ queryKey: ['hourly-flow'] })

      setSuccessMsg((prev) => ({
        ...prev,
        [updatedEspacio.id]: `Aforo máximo actualizado a ${updatedEspacio.capacidad_max} plazas/asientos`,
      }))
      setTimeout(() => {
        setSuccessMsg((prev) => ({ ...prev, [updatedEspacio.id]: null }))
      }, 4000)
    },
    onError: (err: any, variables) => {
      setErrorMsg((prev) => ({
        ...prev,
        [variables.espacioId]: err?.response?.data?.detail || 'Error al actualizar el aforo',
      }))
      setTimeout(() => {
        setErrorMsg((prev) => ({ ...prev, [variables.espacioId]: null }))
      }, 5000)
    },
  })

  const updateSalasMutation = useMutation({
    mutationFn: async (salasPayload: { id: number; capacidad: number }[]) => {
      const results = []
      for (const item of salasPayload) {
        const res = await updateSalaCapacidad(item.id, item.capacidad)
        results.push(res)
      }
      return results
    },
    onSuccess: (results) => {
      queryClient.invalidateQueries({ queryKey: ['admin-espacios'] })
      queryClient.invalidateQueries({ queryKey: ['salas-biblioteca'] })
      queryClient.invalidateQueries({ queryKey: ['realtime-occupancy'] })
      queryClient.invalidateQueries({ queryKey: ['attendance-kpis'] })
      queryClient.invalidateQueries({ queryKey: ['hourly-flow'] })
      queryClient.invalidateQueries({ queryKey: ['rooms-comparison'] })
      refetchSalas()
      refetch()

      const totalCap = results[results.length - 1]?.capacidad_total_espacio ?? 0
      setSalaSuccessMsg(`Aforo de salas actualizado con éxito. Capacidad total de biblioteca sincronizada: ${totalCap} asientos.`)
      setTimeout(() => setSalaSuccessMsg(null), 5000)
    },
    onError: (err: any) => {
      setSalaErrorMsg(err?.response?.data?.detail || 'Error al actualizar las capacidades de las salas')
      setTimeout(() => setSalaErrorMsg(null), 5000)
    },
  })

  // Filtrar espacios según permisos de dataset del usuario.
  // Nota: La gestión de aforos de Estacionamiento Campus San Francisco (ID: 2) se efectúa
  // de forma especializada por sector vehicular ANPR en la sección SectoresEstacionamientoSection.
  const espaciosVisibles = espacios.filter((e) => {
    if (e.id === 2 || e.tipo === 'estacionamiento') return false
    if (isSuperAdmin) return true
    if (e.tipo === 'biblioteca') return hasDatasetAccess('biblioteca')
    return false
  })

  const handleInputChange = (espacioId: number, value: number) => {
    setCapacidadesEdit((prev) => ({ ...prev, [espacioId]: value }))
  }

  const handleSave = (espacio: EspacioInfo) => {
    const val = capacidadesEdit[espacio.id] ?? espacio.capacidad_max
    if (val <= 0) {
      setErrorMsg((prev) => ({ ...prev, [espacio.id]: 'El aforo debe ser mayor a 0' }))
      return
    }
    updateMutation.mutate({ espacioId: espacio.id, capacidad: val })
  }

  const handlePreset = (espacio: EspacioInfo, delta: number) => {
    const current = capacidadesEdit[espacio.id] ?? espacio.capacidad_max
    const nextVal = Math.max(10, current + delta)
    handleInputChange(espacio.id, nextVal)
  }

  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center animate-pulse">
        <Users className="mx-auto text-slate-300 mb-3" size={36} />
        <p className="text-sm font-semibold text-slate-600">Cargando configuración de recintos...</p>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 text-center text-rose-800 space-y-3">
        <AlertTriangle className="mx-auto text-rose-600" size={32} />
        <p className="text-sm font-bold">No fue posible obtener los recintos y sus capacidades.</p>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 bg-rose-600 text-white text-xs font-semibold rounded-lg hover:bg-rose-700 transition-colors"
        >
          Reintentar
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Encabezado descriptivo */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-uct-blue-primary uppercase tracking-wider">
            <Users size={16} />
            <span>Control de Aforo y Capacidad Máxima</span>
          </div>
          <h2 className="text-xl font-bold text-slate-900 mt-1">
            Gestión de Aforo de Recintos
          </h2>
          <p className="text-xs text-slate-500 mt-0.5 max-w-2xl">
            Modifica la capacidad de ocupación en tiempo real. Este valor recalcula automáticamente los umbrales de alerta preventiva (70%), saturación crítica (85%) y la curva de concurrencia de cada módulo.
          </p>
        </div>

        <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600 shrink-0">
          <Info size={15} className="text-uct-blue-primary shrink-0" />
          <span>Persistido en SQL Server</span>
        </div>
      </div>

      {/* Grid de Recintos */}
      <div className="grid grid-cols-1 gap-6">
        {espaciosVisibles.map((espacio) => {
          const valorActual = capacidadesEdit[espacio.id] ?? espacio.capacidad_max
          const modificado = valorActual !== espacio.capacidad_max
          const isSaving = updateMutation.isPending && updateMutation.variables?.espacioId === espacio.id
          const isBib = espacio.tipo === 'biblioteca'
          const Icon = isBib ? Building : Car
          const unidad = isBib ? 'asientos / usuarios' : 'plazas vehiculares'

          const umbral70 = Math.round(valorActual * 0.70)
          const umbral85 = Math.round(valorActual * 0.85)

          return (
            <div
              key={espacio.id}
              className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 space-y-6 flex flex-col justify-between"
            >
              <div className="space-y-4">
                {/* Cabecera del Recinto */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-11 h-11 rounded-xl flex items-center justify-center border shadow-2xs ${
                        isBib
                          ? 'bg-blue-50 border-blue-200 text-blue-700'
                          : 'bg-emerald-50 border-emerald-200 text-emerald-700'
                      }`}
                    >
                      <Icon size={22} />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-slate-900">
                        {espacio.nombre}
                      </h3>
                      <p className="text-xs text-slate-500">
                        {espacio.campus} · Módulo {espacio.tipo.toUpperCase()}
                      </p>
                    </div>
                  </div>

                  <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                    ID: {espacio.id}
                  </span>
                </div>
              </div>

              {isBib ? (
                /* Vista Especializada para Biblioteca: Gestión Granular por Sala Física */
                <div className="space-y-5">
                  {/* Feedback Mensajes de Salas */}
                  {salaSuccessMsg && (
                    <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 flex items-center gap-2 animate-in fade-in">
                      <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
                      <span className="font-medium">{salaSuccessMsg}</span>
                    </div>
                  )}
                  {salaErrorMsg && (
                    <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 flex items-center gap-2 animate-in fade-in">
                      <AlertTriangle size={16} className="text-rose-600 shrink-0" />
                      <span className="font-medium">{salaErrorMsg}</span>
                    </div>
                  )}

                  {/* Lista de Salas Físicas */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5 uppercase tracking-wider">
                        <DoorClosed size={14} className="text-uct-blue-primary" />
                        <span>Capacidad por Sala Física:</span>
                      </span>
                      <span className="text-[11px] text-slate-500">
                        {salasBiblioteca.length} salas registradas en BD
                      </span>
                    </div>

                    <div className="space-y-3">
                      {salasBiblioteca.map((s) => {
                        const valSala = capacidadesSalasEdit[s.id] ?? s.capacidad_asientos
                        const salaModificada = valSala !== s.capacidad_asientos
                        const s70 = Math.round(valSala * 0.70)
                        const s85 = Math.round(valSala * 0.85)

                        return (
                          <div
                            key={s.id}
                            className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-2.5 transition-all"
                          >
                            <div className="flex items-center justify-between">
                              <div>
                                <span className="text-xs font-bold text-slate-900 block">{s.nombre}</span>
                                <span className="text-[10.5px] text-slate-500">
                                  {s.edificio} · {s.piso} · Código: <code>{s.codigo}</code>
                                </span>
                              </div>
                              <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-blue-100 text-uct-blue-primary">
                                {valSala} asientos
                              </span>
                            </div>

                            <div className="flex items-center gap-2">
                              <input
                                type="number"
                                min={10}
                                max={5000}
                                value={valSala}
                                onChange={(e) => {
                                  const n = parseInt(e.target.value) || 0
                                  setCapacidadesSalasEdit((prev) => ({ ...prev, [s.id]: n }))
                                }}
                                className="w-24 px-2.5 py-1 text-sm font-bold text-slate-900 bg-white border border-slate-300 rounded-lg text-center focus:ring-1 focus:ring-uct-blue-primary"
                              />

                              <div className="flex items-center gap-1">
                                {[-20, -10, +10, +20].map((d) => (
                                  <button
                                    key={d}
                                    type="button"
                                    onClick={() => {
                                      const next = Math.max(10, valSala + d)
                                      setCapacidadesSalasEdit((prev) => ({ ...prev, [s.id]: next }))
                                    }}
                                    className="px-1.5 py-1 text-[10.5px] font-semibold bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 rounded transition cursor-pointer"
                                  >
                                    {d > 0 ? `+${d}` : d}
                                  </button>
                                ))}
                              </div>

                              {salaModificada && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setCapacidadesSalasEdit((prev) => {
                                      const c = { ...prev }
                                      delete c[s.id]
                                      return c
                                    })
                                  }}
                                  title="Restablecer valor original de sala"
                                  className="p-1 text-slate-400 hover:text-slate-700 transition cursor-pointer ml-auto"
                                >
                                  <RotateCcw size={14} />
                                </button>
                              )}
                            </div>

                            {/* Mini umbrales de la sala */}
                            <div className="flex items-center gap-3 text-[10px] text-slate-500 pt-0.5">
                              <span>70% Preventivo: <strong className="text-emerald-700">{s70} as.</strong></span>
                              <span>85% Alerta: <strong className="text-amber-700">{s85} as.</strong></span>
                              <span>Límite: <strong className="text-slate-800">{valSala} as.</strong></span>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  {/* Confirmación de Aforo de Salas */}
                  {(() => {
                    const totalCalculado = salasBiblioteca.reduce(
                      (acc, s) => acc + (capacidadesSalasEdit[s.id] ?? s.capacidad_asientos),
                      0
                    )
                    const hayModificacionSalas = salasBiblioteca.some(
                      (s) => (capacidadesSalasEdit[s.id] ?? s.capacidad_asientos) !== s.capacidad_asientos
                    )

                    return (
                      <div className="pt-1">
                        <button
                          type="button"
                          disabled={updateSalasMutation.isPending || !hayModificacionSalas || totalCalculado <= 0}
                          onClick={() => {
                            const payload = salasBiblioteca.map((s) => ({
                              id: s.id,
                              capacidad: capacidadesSalasEdit[s.id] ?? s.capacidad_asientos,
                            }))
                            updateSalasMutation.mutate(payload)
                          }}
                          className={`w-full py-2.5 px-4 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-xs ${
                            hayModificacionSalas
                              ? 'bg-uct-blue-primary hover:bg-uct-blue-secondary text-white'
                              : 'bg-slate-200/80 text-slate-400 cursor-not-allowed'
                          }`}
                        >
                          <Save size={15} />
                          <span>
                            {updateSalasMutation.isPending
                              ? 'Guardando Aforo de Salas...'
                              : hayModificacionSalas
                              ? 'Confirmar y Guardar Aforo de Salas'
                              : 'Aforo de Salas Actualizado'}
                          </span>
                        </button>
                      </div>
                    )
                  })()}
                </div>
              ) : (
                /* Vista Estándar para Estacionamiento u otros espacios */
                <div className="space-y-4">
                  {/* Feedback Mensajes */}
                  {successMsg[espacio.id] && (
                    <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 flex items-center gap-2 animate-in fade-in">
                      <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
                      <span className="font-medium">{successMsg[espacio.id]}</span>
                    </div>
                  )}
                  {errorMsg[espacio.id] && (
                    <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 flex items-center gap-2 animate-in fade-in">
                      <AlertTriangle size={16} className="text-rose-600 shrink-0" />
                      <span className="font-medium">{errorMsg[espacio.id]}</span>
                    </div>
                  )}

                  {/* Input de Modificación */}
                  <div className="p-4 bg-slate-50/70 border border-slate-200 rounded-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-slate-700">
                        Capacidad Máxima ({unidad})
                      </label>
                      <span className="text-[11px] text-slate-500">
                        Actual en BD: <strong className="text-slate-800">{espacio.capacidad_max}</strong>
                      </span>
                    </div>

                    <div className="flex items-center gap-3">
                      <input
                        type="number"
                        min={1}
                        max={10000}
                        value={valorActual}
                        onChange={(e) => handleInputChange(espacio.id, parseInt(e.target.value) || 0)}
                        className="w-full px-3.5 py-2 text-lg font-bold text-slate-900 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/30 focus:border-uct-blue-primary text-center"
                      />

                      {modificado && (
                        <button
                          type="button"
                          onClick={() => handleInputChange(espacio.id, espacio.capacidad_max)}
                          title="Restablecer valor original"
                          className="p-2.5 text-slate-500 hover:text-slate-800 hover:bg-slate-200/60 rounded-xl transition-colors cursor-pointer"
                        >
                          <RotateCcw size={18} />
                        </button>
                      )}
                    </div>

                    {/* Botones de ajuste rápido */}
                    <div className="flex items-center justify-between gap-1.5 pt-1">
                      <span className="text-[10px] text-slate-400 font-medium">Ajuste rápido:</span>
                      <div className="flex items-center gap-1.5">
                        {[-50, -10, +10, +50].map((delta) => (
                          <button
                            key={delta}
                            type="button"
                            onClick={() => handlePreset(espacio, delta)}
                            className="px-2 py-0.5 text-[11px] font-semibold bg-white border border-slate-200 hover:border-slate-300 text-slate-700 rounded-md transition-colors cursor-pointer hover:bg-slate-100"
                          >
                            {delta > 0 ? `+${delta}` : delta}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Previsualización de Umbrales Calculados */}
                  <div className="space-y-2 pt-1">
                    <span className="text-[11px] font-bold text-slate-600 block uppercase tracking-wider">
                      Umbrales Operativos Calculados:
                    </span>
                    <div className="grid grid-cols-3 gap-2">
                      <div className="p-2.5 bg-emerald-50/70 border border-emerald-200/80 rounded-xl text-center">
                        <span className="text-[10px] text-emerald-700 font-semibold block">70% Preventivo</span>
                        <span className="text-sm font-bold text-emerald-900">{umbral70}</span>
                        <span className="text-[10px] text-emerald-600 block">ocupación</span>
                      </div>

                      <div className="p-2.5 bg-amber-50/70 border border-amber-200/80 rounded-xl text-center">
                        <span className="text-[10px] text-amber-700 font-semibold block">85% Alerta</span>
                        <span className="text-sm font-bold text-amber-900">{umbral85}</span>
                        <span className="text-[10px] text-amber-600 block">saturación</span>
                      </div>

                      <div className="p-2.5 bg-rose-50/70 border border-rose-200/80 rounded-xl text-center">
                        <span className="text-[10px] text-rose-700 font-semibold block">100% Límite</span>
                        <span className="text-sm font-bold text-rose-900">{valorActual}</span>
                        <span className="text-[10px] text-rose-600 block">capacidad</span>
                      </div>
                    </div>
                  </div>

                  {/* Botón de Guardado */}
                  <div className="pt-4 border-t border-slate-100">
                    <button
                      type="button"
                      disabled={isSaving || valorActual <= 0 || !modificado}
                      onClick={() => handleSave(espacio)}
                      className={`w-full py-2.5 px-4 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-xs ${
                        modificado
                          ? 'bg-uct-blue-primary hover:bg-uct-blue-secondary text-white'
                          : 'bg-slate-100 text-slate-400 cursor-not-allowed'
                      }`}
                    >
                      <Save size={15} />
                      <span>{isSaving ? 'Guardando Aforo...' : modificado ? 'Confirmar y Guardar Aforo' : 'Aforo Actualizado'}</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Configuración de Capacidad por Sector Vehicular ANPR (CSF11, CSF21, CHS01) */}
      <SectoresEstacionamientoSection />
    </div>
  )
}
