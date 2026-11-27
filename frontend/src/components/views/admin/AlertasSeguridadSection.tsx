import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Bell, CheckCircle2, ShieldAlert, Trash2, Unlock, UserCheck } from 'lucide-react'
import {
  desbloquearUsuarioAdmin,
  eliminarNotificacionAdmin,
  listarNotificacionesAdmin,
  marcarNotificacionesAdminVistas,
  type NotificacionesAdminResponse,
} from '../../../api/administracion'
import { formatearFechaHoraChile } from '../../../utils/fechaChile'
import { useTemporizadorSeguro } from '../../../hooks/useTemporizadorSeguro'

const formatearFecha = (iso?: string | null): string =>
  formatearFechaHoraChile(iso, undefined, '—')

export const AlertasSeguridadSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [idsRecienVistos, setIdsRecienVistos] = useState<number[]>([])
  const [avisoMsg, setAvisoMsg] = useState<string | null>(null)
  const marcandoRef = useRef(false)
  const { programar } = useTemporizadorSeguro()

  const { data, isLoading } = useQuery<NotificacionesAdminResponse>({
    queryKey: ['admin-notificaciones'],
    queryFn: listarNotificacionesAdmin,
    refetchInterval: 30_000,
  })

  const items = useMemo(() => data?.items ?? [], [data?.items])

  // Al entrar o recibir alertas nuevas, se marcan como vistas para limpiar el círculo rojo
  useEffect(() => {
    const pendientes = items.filter((n) => !n.leida).map((n) => n.id)
    if (pendientes.length === 0 || marcandoRef.current) return

    setIdsRecienVistos((prev) => Array.from(new Set([...prev, ...pendientes])))
    marcandoRef.current = true
    marcarNotificacionesAdminVistas()
      .then(() => {
        queryClient.setQueryData<NotificacionesAdminResponse>(['admin-notificaciones'], (prev) => {
          if (!prev) return prev
          return {
            no_leidas: 0,
            items: prev.items.map((item) => ({
              ...item,
              leida: true,
              leida_en: item.leida_en ?? new Date().toISOString(),
            })),
          }
        })
      })
      .finally(() => {
        marcandoRef.current = false
      })
  }, [items, queryClient])

  const desbloquearMutation = useMutation({
    mutationFn: (userId: number) => desbloquearUsuarioAdmin(userId),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['admin-notificaciones'] })
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      setAvisoMsg(res.mensaje || 'Cuenta desbloqueada correctamente.')
      programar(() => setAvisoMsg(null), 5000)
    },
  })

  const eliminarMutation = useMutation({
    mutationFn: (id: number) => eliminarNotificacionAdmin(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-notificaciones'] })
    },
  })

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
        <div className="flex items-start gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-600 flex items-center justify-center shrink-0">
            <Bell size={22} />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900">Alertas de Seguridad y Bloqueos de Acceso</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Registro automático de cuentas bloqueadas tras 5 intentos fallidos consecutivos de contraseña. Al revisar esta vista, el indicador rojo desaparece automáticamente.
            </p>
          </div>
        </div>
      </div>

      {avisoMsg && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-2 text-xs font-semibold text-emerald-800">
          <CheckCircle2 size={16} className="shrink-0 text-emerald-600" />
          <span>{avisoMsg}</span>
        </div>
      )}

      {isLoading ? (
        <div className="py-10 text-center text-xs text-slate-400">Cargando alertas de seguridad...</div>
      ) : items.length === 0 ? (
        <div className="py-12 text-center space-y-2 border border-dashed border-slate-200 rounded-xl">
          <ShieldAlert size={28} className="mx-auto text-slate-300" />
          <p className="text-xs font-semibold text-slate-500">No se registran alertas de bloqueo de cuentas.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const esNueva = idsRecienVistos.includes(item.id)
            return (
              <div
                key={item.id}
                className={`p-4 rounded-xl border transition flex flex-col md:flex-row md:items-center justify-between gap-3 ${
                  esNueva ? 'bg-rose-50/70 border-rose-200' : 'bg-slate-50/60 border-slate-200'
                }`}
              >
                <div className="space-y-1.5 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <AlertTriangle size={15} className="text-rose-600 shrink-0" />
                    <span className="text-xs font-bold text-slate-900">{item.titulo}</span>
                    {esNueva && (
                      <span className="px-2 py-0.5 rounded-full bg-rose-600 text-white text-[10px] font-bold">
                        Nueva
                      </span>
                    )}
                    {item.cuenta_bloqueada_ahora ? (
                      <span className="px-2 py-0.5 rounded-md bg-rose-100 text-rose-800 text-[10px] font-bold border border-rose-200">
                        Cuenta bloqueada
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 text-[10px] font-semibold">
                        <UserCheck size={11} /> Desbloqueada / Expirada
                      </span>
                    )}
                  </div>

                  <p className="text-xs text-slate-700">{item.mensaje}</p>

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
                    <span>
                      Usuario: <strong className="text-slate-700">{item.usuario_afectado_nombre || '—'}</strong> ({item.usuario_afectado_email || '—'})
                    </span>
                    <span>Intentos fallidos: <strong>{item.intentos_fallidos}</strong></span>
                    {item.ip_origen && <span>IP origen: <span className="font-mono">{item.ip_origen}</span></span>}
                    <span>Fecha: {formatearFecha(item.creado_en)}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {item.cuenta_bloqueada_ahora && item.usuario_afectado_id && (
                    <button
                      type="button"
                      onClick={() => desbloquearMutation.mutate(item.usuario_afectado_id!)}
                      disabled={desbloquearMutation.isPending}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-uct-blue-primary hover:bg-uct-blue-hover text-white text-xs font-bold cursor-pointer disabled:opacity-50"
                    >
                      <Unlock size={13} />
                      <span>Desbloquear cuenta</span>
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => eliminarMutation.mutate(item.id)}
                    disabled={eliminarMutation.isPending}
                    className="p-2 rounded-lg border border-slate-200 hover:bg-rose-50 hover:border-rose-200 text-slate-500 hover:text-rose-600 cursor-pointer"
                    title="Eliminar registro de alerta"
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
  )
}
