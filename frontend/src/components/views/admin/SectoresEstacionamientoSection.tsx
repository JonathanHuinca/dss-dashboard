import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Car,
  Save,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  ShieldCheck,
  Building,
} from 'lucide-react'
import {
  obtenerSectoresEstacionamientoAdmin,
  actualizarCapacidadSectorAdmin,
  SectorEstacionamientoAdmin,
} from '../../../api/client'
import { useAuth } from '../../../context/AuthContext'

export const SectoresEstacionamientoSection: React.FC = () => {
  const { isSuperAdmin } = useAuth()
  const queryClient = useQueryClient()
  const [capacidadesEdit, setCapacidadesEdit] = useState<Record<string, number>>({})
  const [mensajeExito, setMensajeExito] = useState<string | null>(null)
  const [mensajeError, setMensajeError] = useState<string | null>(null)

  const {
    data: sectores = [],
    isLoading,
    refetch,
  } = useQuery<SectorEstacionamientoAdmin[]>({
    queryKey: ['admin-sectores-estacionamiento'],
    queryFn: obtenerSectoresEstacionamientoAdmin,
  })

  const updateMutation = useMutation({
    mutationFn: ({ codigo, capacidad }: { codigo: string; capacidad: number }) =>
      actualizarCapacidadSectorAdmin(codigo, capacidad),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['admin-sectores-estacionamiento'] })
      queryClient.invalidateQueries({ queryKey: ['parking-occupancy'] })
      queryClient.invalidateQueries({ queryKey: ['vehicle-kpis'] })
      queryClient.invalidateQueries({ queryKey: ['admin-smart-campus-estado'] })
      queryClient.invalidateQueries({ queryKey: ['admin-espacios'] })
      queryClient.invalidateQueries({ queryKey: ['date-bounds'] })
      setMensajeExito(`Capacidad del sector ${res.codigo} actualizada a ${res.capacidad_max} plazas. Aforo total sincronizado.`)
      setTimeout(() => setMensajeExito(null), 4000)
      refetch()
    },
    onError: (err: any) => {
      setMensajeError(err?.response?.data?.detail || 'Error al actualizar capacidad del sector.')
      setTimeout(() => setMensajeError(null), 5000)
    },
  })

  const handleCapacidadChange = (codigo: string, valor: string) => {
    const num = parseInt(valor, 10)
    setCapacidadesEdit((prev) => ({
      ...prev,
      [codigo]: isNaN(num) ? 0 : Math.max(1, num),
    }))
  }

  const handleGuardar = (sector: SectorEstacionamientoAdmin) => {
    const nuevaCapacidad = capacidadesEdit[sector.codigo] ?? sector.capacidad_max
    updateMutation.mutate({ codigo: sector.codigo, capacidad: nuevaCapacidad })
  }

  const capacidadTotal = sectores.reduce((acc, s) => {
    const editada = capacidadesEdit[s.codigo]
    return acc + (editada !== undefined ? editada : s.capacidad_max)
  }, 0)

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-600">
            <Car size={16} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-800">
                Configuración de Capacidad por Sector de Estacionamiento
              </h3>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                Módulo Estacionamiento · ID: 2
              </span>
            </div>
            <p className="text-[11px] text-slate-500">
              Aforos operativos máximos calibrados para los 3 accesos vehiculares ANPR institucionales. Sincroniza automáticamente la capacidad máxima del recinto.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700">
          <span>Capacidad Total Campus:</span>
          <span className="font-bold text-emerald-600">{capacidadTotal} plazas</span>
        </div>
      </div>

      {mensajeExito && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 flex items-center gap-2">
          <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
          <span>{mensajeExito}</span>
        </div>
      )}

      {mensajeError && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-800 flex items-center gap-2">
          <AlertTriangle size={15} className="text-red-500 shrink-0" />
          <span>{mensajeError}</span>
        </div>
      )}

      {isLoading ? (
        <div className="p-6 text-center text-xs text-slate-400">Cargando sectores vehiculares...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {sectores.map((sector) => {
            const valorActual = capacidadesEdit[sector.codigo] ?? sector.capacidad_max
            const haCambiado = valorActual !== sector.capacidad_max

            return (
              <div
                key={sector.codigo}
                className="p-4 rounded-xl border border-slate-200/90 bg-slate-50/50 flex flex-col justify-between space-y-3"
              >
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold text-slate-800">{sector.codigo}</span>
                    <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                      Activo
                    </span>
                  </div>
                  <h4 className="text-xs font-semibold text-slate-700">{sector.nombre}</h4>
                  <div className="text-[10px] text-slate-500 mt-1 space-y-0.5">
                    <p>Entrada: <span className="font-mono text-slate-700">{sector.camaras_entrada}</span></p>
                    <p>Salida: <span className="font-mono text-slate-700">{sector.camaras_salida}</span></p>
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-200/60 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <label className="text-[11px] font-medium text-slate-600">Plazas:</label>
                    <input
                      type="number"
                      min={1}
                      max={2000}
                      value={valorActual}
                      disabled={!isSuperAdmin}
                      onChange={(e) => handleCapacidadChange(sector.codigo, e.target.value)}
                      className="w-20 px-2 py-1 text-xs font-bold text-center bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-uct-blue-primary"
                    />
                  </div>
                  {isSuperAdmin && (
                    <button
                      type="button"
                      onClick={() => handleGuardar(sector)}
                      disabled={!haCambiado || updateMutation.isPending}
                      className={`px-2.5 py-1 rounded-lg text-xs font-bold transition flex items-center gap-1 cursor-pointer ${
                        haCambiado
                          ? 'bg-uct-blue-primary hover:bg-uct-blue-hover text-white shadow-2xs'
                          : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                      }`}
                      title="Guardar nueva capacidad"
                    >
                      <Save size={12} />
                      <span>Guardar</span>
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

