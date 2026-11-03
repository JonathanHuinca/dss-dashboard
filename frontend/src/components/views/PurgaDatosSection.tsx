import React, { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Trash2,
  AlertTriangle,
  ShieldAlert,
  CheckCircle2,
  RefreshCw,
  Database,
  Building,
  Users,
  Car,
} from 'lucide-react'
import { purgarDatosAdmin, SolicitudPurgaDatos, RespuestaPurgaDatos } from '../../api/client'

export const PurgaDatosSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [alcance, setAlcance] = useState<SolicitudPurgaDatos['alcance']>('asistencia')
  const [espacioId, setEspacioId] = useState<number | undefined>(1)
  const [confirmacionTexto, setConfirmacionTexto] = useState('')
  const [resultado, setResultado] = useState<RespuestaPurgaDatos | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const purgaMutation = useMutation({
    mutationFn: (solicitud: SolicitudPurgaDatos) => purgarDatosAdmin(solicitud),
    onSuccess: (data) => {
      setResultado(data)
      setErrorMsg(null)
      setConfirmacionTexto('')
      queryClient.invalidateQueries({ queryKey: ['attendance'] })
      queryClient.invalidateQueries({ queryKey: ['kpis'] })
      queryClient.invalidateQueries({ queryKey: ['admin-ingest-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['espacios-config'] })
      queryClient.invalidateQueries({ queryKey: ['parking-kpis'] })
    },
    onError: (err: any) => {
      setErrorMsg(err.response?.data?.detail || 'Error al ejecutar la purga de datos.')
      setResultado(null)
    },
  })

  const ejecutarPurga = () => {
    if (confirmacionTexto.trim() !== 'CONFIRMAR_PURGA') {
      setErrorMsg("Debe escribir exactamente 'CONFIRMAR_PURGA' para autorizar el vaciado.")
      return
    }
    setErrorMsg(null)
    purgaMutation.mutate({
      alcance,
      espacio_id: alcance === 'todo' || alcance === 'institucional_estudiantes' ? undefined : espacioId,
      confirmacion: confirmacionTexto.trim(),
    })
  }

  const esConfirmacionValida = confirmacionTexto.trim() === 'CONFIRMAR_PURGA'

  return (
    <div className="space-y-6">
      {/* Banner de Advertencia Crítica */}
      <div className="bg-rose-50 border border-rose-200 rounded-2xl p-5 text-rose-900 shadow-xs">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-rose-100 flex items-center justify-center shrink-0 text-rose-700">
            <ShieldAlert size={22} />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold tracking-tight">Zona de Purga y Reseteo Administrativo</h3>
            <p className="text-xs text-rose-800 leading-relaxed">
              Esta operación elimina de forma permanente los registros en la base de datos institucional y reinicia contadores de aforo.
              Utilice esta herramienta para preparar el sistema antes de cargar el esquema institucional oficial o datasets definitivos.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Panel de Configuración de la Purga */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-6">
          <div>
            <h4 className="text-base font-bold text-slate-900">Seleccionar Alcance del Vaciado</h4>
            <p className="text-xs text-slate-500 mt-1">
              Escoja qué datos desea purgar de manera selectiva o global.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label
              className={`flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${
                alcance === 'asistencia'
                  ? 'border-rose-500 bg-rose-50/40 text-rose-950 font-semibold shadow-xs'
                  : 'border-slate-200 hover:border-slate-300 text-slate-700'
              }`}
            >
              <input
                type="radio"
                name="alcance"
                value="asistencia"
                checked={alcance === 'asistencia'}
                onChange={() => setAlcance('asistencia')}
                className="mt-1 text-rose-600 focus:ring-rose-500"
              />
              <div className="text-xs">
                <div className="flex items-center gap-1.5 font-bold">
                  <Building size={14} />
                  <span>Asistencia Biblioteca</span>
                </div>
                <p className="text-[11px] text-slate-500 mt-0.5 font-normal">
                  Eventos de marcajes de biblioteca, aforos actuales y rollups diarios calculados.
                </p>
              </div>
            </label>

            <label
              className={`flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${
                alcance === 'institucional_estudiantes'
                  ? 'border-rose-500 bg-rose-50/40 text-rose-950 font-semibold shadow-xs'
                  : 'border-slate-200 hover:border-slate-300 text-slate-700'
              }`}
            >
              <input
                type="radio"
                name="alcance"
                value="institucional_estudiantes"
                checked={alcance === 'institucional_estudiantes'}
                onChange={() => setAlcance('institucional_estudiantes')}
                className="mt-1 text-rose-600 focus:ring-rose-500"
              />
              <div className="text-xs">
                <div className="flex items-center gap-1.5 font-bold">
                  <Users size={14} />
                  <span>Catálogo Institucional UCT</span>
                </div>
                <p className="text-[11px] text-slate-500 mt-0.5 font-normal">
                  Tablas institucionales uct_* (11 tablas), estudiantes, carreras y dimensión curricular.
                </p>
              </div>
            </label>

            <label
              className={`flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${
                alcance === 'vehicular'
                  ? 'border-rose-500 bg-rose-50/40 text-rose-950 font-semibold shadow-xs'
                  : 'border-slate-200 hover:border-slate-300 text-slate-700'
              }`}
            >
              <input
                type="radio"
                name="alcance"
                value="vehicular"
                checked={alcance === 'vehicular'}
                onChange={() => setAlcance('vehicular')}
                className="mt-1 text-rose-600 focus:ring-rose-500"
              />
              <div className="text-xs">
                <div className="flex items-center gap-1.5 font-bold">
                  <Car size={14} />
                  <span>Control Vehicular</span>
                </div>
                <p className="text-[11px] text-slate-500 mt-0.5 font-normal">
                  Eventos ANPR, accesos de estacionamiento y ocupación en tiempo real.
                </p>
              </div>
            </label>

            <label
              className={`flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${
                alcance === 'todo'
                  ? 'border-rose-600 bg-rose-100/50 text-rose-950 font-semibold shadow-xs ring-1 ring-rose-500'
                  : 'border-slate-200 hover:border-slate-300 text-slate-700'
              }`}
            >
              <input
                type="radio"
                name="alcance"
                value="todo"
                checked={alcance === 'todo'}
                onChange={() => setAlcance('todo')}
                className="mt-1 text-rose-600 focus:ring-rose-500"
              />
              <div className="text-xs">
                <div className="flex items-center gap-1.5 font-bold text-rose-800">
                  <Database size={14} />
                  <span>Vaciado Completo (Todo)</span>
                </div>
                <p className="text-[11px] text-slate-500 mt-0.5 font-normal">
                  Elimina asistencias, vehículos, maestros institucionales UCT y trabajos de ingesta.
                </p>
              </div>
            </label>
          </div>

          {alcance === 'asistencia' && (
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700">Espacio Académico Objetivo</label>
              <select
                value={espacioId}
                onChange={(e) => setEspacioId(Number(e.target.value))}
                className="w-full text-xs rounded-xl border border-slate-300 bg-slate-50 px-3 py-2 text-slate-800 font-medium focus:ring-2 focus:ring-uct-blue-primary focus:bg-white"
              >
                <option value={1}>Biblioteca Campus San Francisco (ID: 1)</option>
              </select>
            </div>
          )}

          {/* Salvaguarda de Confirmación */}
          <div className="space-y-2 pt-2 border-t border-slate-100">
            <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
              <AlertTriangle size={14} className="text-amber-500" />
              <span>Para proceder, escriba exactamente:</span>
              <code className="bg-slate-100 px-2 py-0.5 rounded text-rose-600 font-mono text-xs select-all">
                CONFIRMAR_PURGA
              </code>
            </label>
            <input
              type="text"
              placeholder="CONFIRMAR_PURGA"
              value={confirmacionTexto}
              onChange={(e) => setConfirmacionTexto(e.target.value)}
              className="w-full text-xs font-mono tracking-wider rounded-xl border border-slate-300 px-3.5 py-2.5 focus:ring-2 focus:ring-rose-500 focus:border-rose-500"
            />
          </div>

          {errorMsg && (
            <div className="flex items-center gap-2 p-3 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-xl">
              <AlertTriangle size={16} className="shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              disabled={!esConfirmacionValida || purgaMutation.isPending}
              onClick={ejecutarPurga}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold transition-all shadow-xs ${
                esConfirmacionValida && !purgaMutation.isPending
                  ? 'bg-rose-600 hover:bg-rose-700 text-white cursor-pointer hover:shadow-md'
                  : 'bg-slate-200 text-slate-400 cursor-not-allowed'
              }`}
            >
              {purgaMutation.isPending ? (
                <>
                  <RefreshCw size={14} className="animate-spin" />
                  <span>Purgando registros...</span>
                </>
              ) : (
                <>
                  <Trash2 size={14} />
                  <span>Ejecutar Purga de Datos</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Panel de Resumen de Resultados */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs flex flex-col justify-between">
          <div>
            <h4 className="text-base font-bold text-slate-900">Estado de la Base de Datos</h4>
            <p className="text-xs text-slate-500 mt-1">
              Registro del último vaciado ejecutado en esta sesión.
            </p>

            {resultado ? (
              <div className="mt-5 space-y-4">
                <div className="flex items-center gap-2 text-emerald-700 bg-emerald-50 border border-emerald-200 p-3 rounded-xl text-xs font-semibold">
                  <CheckCircle2 size={16} className="shrink-0" />
                  <span>{resultado.mensaje}</span>
                </div>

                <div className="space-y-2">
                  <div className="text-xs font-bold text-slate-700">Registros Eliminados:</div>
                  <div className="bg-slate-50 rounded-xl p-3 border border-slate-200 divide-y divide-slate-200/60 text-xs font-mono">
                    {Object.entries(resultado.registros_eliminados).map(([tabla, cantidad]) => (
                      <div key={tabla} className="flex justify-between py-1.5 first:pt-0 last:pb-0">
                        <span className="text-slate-600">{tabla}:</span>
                        <span className="font-bold text-slate-900">{cantidad.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-8 text-center py-8 text-slate-400 space-y-2">
                <Database size={32} className="mx-auto text-slate-300" />
                <p className="text-xs">No se han ejecutado operaciones de purga en esta sesión.</p>
              </div>
            )}
          </div>

          <div className="mt-6 pt-4 border-t border-slate-100 text-[11px] text-slate-400">
            <span>Nota: Los aforos en tiempo real se restablecen automáticamente a 0 tras la purga de asistencia o vehicular.</span>
          </div>
        </div>
      </div>
    </div>
  )
}
