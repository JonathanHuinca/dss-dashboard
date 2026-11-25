import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Edit3,
  KeyRound,
  Mail,
  Plus,
  Power,
  Send,
  ShieldCheck,
  Trash2,
  X,
  XCircle,
} from 'lucide-react'
import {
  activarConfiguracionSMTP,
  activarCredencialIA,
  actualizarConfiguracionSMTP,
  actualizarCredencialIA,
  ConfiguracionSMTPCreatePayload,
  ConfiguracionSMTPItem,
  crearConfiguracionSMTP,
  crearCredencialIA,
  CredencialIACreatePayload,
  CredencialIAItem,
  eliminarConfiguracionSMTP,
  eliminarCredencialIA,
  listarConfiguracionesSMTP,
  listarCredencialesIA,
  obtenerCatalogoProveedoresIA,
  probarConfiguracionSMTP,
  probarCredencialIA,
  ProveedorCatalogoItem,
} from '../../../api/administracion'
import { api } from '../../../api/client'
import { formatearFechaHoraChile } from '../../../utils/fechaChile'

type TipoEliminacion =
  | { tipo: 'ia'; item: CredencialIAItem }
  | { tipo: 'smtp'; item: ConfiguracionSMTPItem }

const formatearFecha = (iso?: string | null): string =>
  formatearFechaHoraChile(iso, undefined, 'Sin pruebas')

export const IntegracionesSection: React.FC = () => {
  const queryClient = useQueryClient()

  // Estado global de notificaciones en pantalla
  const [avisoOk, setAvisoOk] = useState<string | null>(null)
  const [avisoError, setAvisoError] = useState<string | null>(null)

  const mostrarExito = (msg: string) => {
    setAvisoError(null)
    setAvisoOk(msg)
    setTimeout(() => setAvisoOk(null), 5000)
  }

  const mostrarError = (msg: string) => {
    setAvisoOk(null)
    setAvisoError(msg)
    setTimeout(() => setAvisoError(null), 6500)
  }

  // Consultas de catálogo, credenciales IA y perfiles SMTP
  const { data: catalogo = [] } = useQuery<ProveedorCatalogoItem[]>({
    queryKey: ['llm-catalog'],
    queryFn: obtenerCatalogoProveedoresIA,
  })

  const { data: dataIA, isLoading: cargandoIA } = useQuery({
    queryKey: ['llm-credentials'],
    queryFn: listarCredencialesIA,
  })

  const { data: dataSMTP, isLoading: cargandoSMTP } = useQuery({
    queryKey: ['smtp-configs'],
    queryFn: listarConfiguracionesSMTP,
  })

  const mapaProveedores = useMemo(() => {
    const mapa: Record<string, ProveedorCatalogoItem> = {}
    catalogo.forEach((p) => {
      mapa[p.id] = p
    })
    return mapa
  }, [catalogo])

  // Interruptor maestro del asistente IA
  const toggleIaMutation = useMutation({
    mutationFn: async () => (await api.post('/admin/config/toggle-ia')).data,
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['llm-credentials'] })
      queryClient.invalidateQueries({ queryKey: ['global-config'] })
      queryClient.invalidateQueries({ queryKey: ['ia-status'] })
      queryClient.invalidateQueries({ queryKey: ['assistant-status'] })
      mostrarExito(
        res.ia_asistente_activo
          ? 'Asistente de IA habilitado globalmente.'
          : 'Asistente de IA suspendido globalmente.'
      )
    },
    onError: (err: any) => mostrarError(err?.response?.data?.detail || 'Error al alternar el servicio de IA.'),
  })

  // ─── Estados de Modales IA ───────────────────────────────────────────────────
  const [modalIAOpen, setModalIAOpen] = useState(false)
  const [editandoIA, setEditandoIA] = useState<CredencialIAItem | null>(null)
  const [iaNombre, setIaNombre] = useState('')
  const [iaProvider, setIaProvider] = useState('gemini')
  const [iaModelo, setIaModelo] = useState('gemini-3.1-flash-lite')
  const [iaModeloCustom, setIaModeloCustom] = useState('')
  const [iaBaseUrl, setIaBaseUrl] = useState('')
  const [iaApiKey, setIaApiKey] = useState('')
  const [iaActivar, setIaActivar] = useState(true)
  const [iaFormError, setIaFormError] = useState<string | null>(null)

  const proveedorMetaActual = mapaProveedores[iaProvider]

  const abrirModalCrearIA = () => {
    const meta = mapaProveedores['gemini']
    setEditandoIA(null)
    setIaNombre('')
    setIaProvider('gemini')
    setIaModelo(meta?.modelos_sugeridos?.[0] || 'gemini-3.1-flash-lite')
    setIaModeloCustom('')
    setIaBaseUrl('')
    setIaApiKey('')
    setIaActivar(true)
    setIaFormError(null)
    setModalIAOpen(true)
  }

  const abrirModalEditarIA = (item: CredencialIAItem) => {
    const meta = mapaProveedores[item.provider_id]
    const enSugeridos = meta?.modelos_sugeridos?.includes(item.modelo)
    setEditandoIA(item)
    setIaNombre(item.nombre)
    setIaProvider(item.provider_id)
    setIaModelo(enSugeridos ? item.modelo : '__custom__')
    setIaModeloCustom(enSugeridos ? '' : item.modelo)
    setIaBaseUrl(item.base_url || meta?.default_base_url || '')
    setIaApiKey('')
    setIaActivar(item.es_activa)
    setIaFormError(null)
    setModalIAOpen(true)
  }

  const handleCambiarProveedorIA = (nuevoId: string) => {
    setIaProvider(nuevoId)
    const meta = mapaProveedores[nuevoId]
    if (meta?.modelos_sugeridos?.length) {
      setIaModelo(meta.modelos_sugeridos[0])
      setIaModeloCustom('')
    } else {
      setIaModelo('__custom__')
    }
    setIaBaseUrl(meta?.default_base_url || '')
  }

  const guardarIAMutation = useMutation({
    mutationFn: async () => {
      const modeloFinal = iaModelo === '__custom__' ? iaModeloCustom.trim() : iaModelo.trim()
      if (!modeloFinal) throw new Error('Debe indicar el identificador del modelo.')
      if (editandoIA) {
        return await actualizarCredencialIA(editandoIA.id, {
          nombre: iaNombre.trim(),
          provider_id: iaProvider,
          modelo: modeloFinal,
          base_url: iaBaseUrl.trim(),
          api_key: iaApiKey.trim() || undefined,
        })
      }
      const payload: CredencialIACreatePayload = {
        nombre: iaNombre.trim(),
        provider_id: iaProvider,
        modelo: modeloFinal,
        base_url: iaBaseUrl.trim() || null,
        api_key: iaApiKey.trim() || null,
        activar: iaActivar,
      }
      return await crearCredencialIA(payload)
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['llm-credentials'] })
      queryClient.invalidateQueries({ queryKey: ['global-config'] })
      setModalIAOpen(false)
      mostrarExito(`Credencial IA '${res.nombre}' guardada de forma cifrada.`)
    },
    onError: (err: any) => {
      setIaFormError(err?.response?.data?.detail || err?.message || 'No fue posible guardar la credencial.')
    },
  })

  const activarIAMutation = useMutation({
    mutationFn: (id: number) => activarCredencialIA(id),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['llm-credentials'] })
      queryClient.invalidateQueries({ queryKey: ['global-config'] })
      mostrarExito(`Proveedor activo actualizado a '${res.nombre}' (${res.provider_id} / ${res.modelo}).`)
    },
    onError: (err: any) => mostrarError(err?.response?.data?.detail || 'Error al activar el proveedor.'),
  })

  const probarIAMutation = useMutation({
    mutationFn: (id: number) => probarCredencialIA(id),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['llm-credentials'] })
      if (res.ok) {
        mostrarExito(`${res.mensaje} (${res.latencia_ms} ms)`)
      } else {
        mostrarError(res.mensaje)
      }
    },
    onError: (err: any) => mostrarError(err?.response?.data?.detail || 'Error ejecutando prueba de conexión IA.'),
  })

  // ─── Estados de Modales SMTP ─────────────────────────────────────────────────
  const [modalSMTPOpen, setModalSMTPOpen] = useState(false)
  const [editandoSMTP, setEditandoSMTP] = useState<ConfiguracionSMTPItem | null>(null)
  const [smtpNombre, setSmtpNombre] = useState('')
  const [smtpHost, setSmtpHost] = useState('')
  const [smtpPort, setSmtpPort] = useState(587)
  const [smtpSeguridad, setSmtpSeguridad] = useState<'starttls' | 'ssl' | 'ninguno'>('starttls')
  const [smtpUser, setSmtpUser] = useState('')
  const [smtpPassword, setSmtpPassword] = useState('')
  const [smtpFromEmail, setSmtpFromEmail] = useState('')
  const [smtpFromName, setSmtpFromName] = useState('Sistema DSS Campus San Francisco UCT')
  const [smtpActivar, setSmtpActivar] = useState(true)
  const [smtpFormError, setSmtpFormError] = useState<string | null>(null)

  const [smtpTestTarget, setSmtpTestTarget] = useState<ConfiguracionSMTPItem | null>(null)
  const [smtpTestEmail, setSmtpTestEmail] = useState('')

  const abrirModalCrearSMTP = () => {
    setEditandoSMTP(null)
    setSmtpNombre('')
    setSmtpHost('')
    setSmtpPort(587)
    setSmtpSeguridad('starttls')
    setSmtpUser('')
    setSmtpPassword('')
    setSmtpFromEmail('')
    setSmtpFromName('Sistema DSS Campus San Francisco UCT')
    setSmtpActivar(true)
    setSmtpFormError(null)
    setModalSMTPOpen(true)
  }

  const abrirModalEditarSMTP = (item: ConfiguracionSMTPItem) => {
    setEditandoSMTP(item)
    setSmtpNombre(item.nombre)
    setSmtpHost(item.host)
    setSmtpPort(item.port)
    setSmtpSeguridad(item.use_ssl ? 'ssl' : item.use_tls ? 'starttls' : 'ninguno')
    setSmtpUser(item.username)
    setSmtpPassword('')
    setSmtpFromEmail(item.from_email)
    setSmtpFromName(item.from_name)
    setSmtpActivar(item.es_activa)
    setSmtpFormError(null)
    setModalSMTPOpen(true)
  }

  const guardarSMTPMutation = useMutation({
    mutationFn: async () => {
      const use_tls = smtpSeguridad === 'starttls'
      const use_ssl = smtpSeguridad === 'ssl'
      if (editandoSMTP) {
        return await actualizarConfiguracionSMTP(editandoSMTP.id, {
          nombre: smtpNombre.trim(),
          host: smtpHost.trim(),
          port: Number(smtpPort),
          use_tls,
          use_ssl,
          username: smtpUser.trim(),
          from_email: smtpFromEmail.trim(),
          from_name: smtpFromName.trim(),
          password: smtpPassword.trim() || undefined,
        })
      }
      const payload: ConfiguracionSMTPCreatePayload = {
        nombre: smtpNombre.trim(),
        host: smtpHost.trim(),
        port: Number(smtpPort),
        use_tls,
        use_ssl,
        username: smtpUser.trim(),
        from_email: smtpFromEmail.trim(),
        from_name: smtpFromName.trim(),
        password: smtpPassword.trim(),
        activar: smtpActivar,
      }
      return await crearConfiguracionSMTP(payload)
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['smtp-configs'] })
      setModalSMTPOpen(false)
      mostrarExito(`Perfil SMTP '${res.nombre}' guardado de forma cifrada.`)
    },
    onError: (err: any) => {
      setSmtpFormError(err?.response?.data?.detail || err?.message || 'Error al guardar perfil SMTP.')
    },
  })

  const activarSMTPMutation = useMutation({
    mutationFn: (id: number) => activarConfiguracionSMTP(id),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['smtp-configs'] })
      mostrarExito(`Servidor SMTP activo cambiado a '${res.nombre}' (${res.host}:${res.port}).`)
    },
    onError: (err: any) => mostrarError(err?.response?.data?.detail || 'Error al activar perfil SMTP.'),
  })

  const probarSMTPMutation = useMutation({
    mutationFn: ({ id, email }: { id: number; email?: string }) => probarConfiguracionSMTP(id, email),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['smtp-configs'] })
      setSmtpTestTarget(null)
      if (res.ok) {
        mostrarExito(res.mensaje)
      } else {
        mostrarError(res.mensaje)
      }
    },
    onError: (err: any) => {
      setSmtpTestTarget(null)
      mostrarError(err?.response?.data?.detail || 'Error al ejecutar prueba SMTP.')
    },
  })

  // ─── Confirmación de Eliminación Definitiva ──────────────────────────────────
  const [itemAEliminar, setItemAEliminar] = useState<TipoEliminacion | null>(null)

  const eliminarMutation = useMutation({
    mutationFn: async (target: TipoEliminacion) => {
      if (target.tipo === 'ia') return await eliminarCredencialIA(target.item.id)
      return await eliminarConfiguracionSMTP(target.item.id)
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['llm-credentials'] })
      queryClient.invalidateQueries({ queryKey: ['smtp-configs'] })
      queryClient.invalidateQueries({ queryKey: ['global-config'] })
      setItemAEliminar(null)
      mostrarExito(res.mensaje || 'Registro eliminado definitivamente.')
    },
    onError: (err: any) => {
      setItemAEliminar(null)
      mostrarError(err?.response?.data?.detail || 'Error al eliminar el registro.')
    },
  })

  const iaActivaGlobal = dataIA?.ia_asistente_activo ?? true

  return (
    <div className="space-y-6">
      {/* Mensajes globales */}
      {avisoOk && (
        <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-2.5 text-xs font-semibold text-emerald-800">
          <CheckCircle2 size={16} className="shrink-0 text-emerald-600" />
          <span>{avisoOk}</span>
        </div>
      )}
      {avisoError && (
        <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl flex items-center gap-2.5 text-xs font-semibold text-rose-800">
          <AlertTriangle size={16} className="shrink-0 text-rose-600" />
          <span>{avisoError}</span>
        </div>
      )}

      {/* ─── SUBSECCIÓN 1: PROVEEDORES Y API KEYS DE IA ─────────────────────── */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 space-y-5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-100 pb-4">
          <div className="flex items-start gap-3.5">
            <div className="w-11 h-11 rounded-xl bg-uct-blue-primary/10 border border-uct-blue-primary/20 text-uct-blue-primary flex items-center justify-center shrink-0">
              <KeyRound size={22} />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-bold text-slate-900">Proveedores y API Keys de Inteligencia Artificial</h2>
                <span
                  className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${
                    iaActivaGlobal
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : 'bg-rose-50 text-rose-700 border-rose-200'
                  }`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${iaActivaGlobal ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                  {iaActivaGlobal ? 'Asistente Habilitado' : 'Asistente Suspendido'}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Administra credenciales cifradas con Fernet AES-128 para Gemini, OpenAI, Claude, DeepSeek, Groq, Ollama u otros compatibles. Las claves nunca se exponen después de guardarse.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={() => toggleIaMutation.mutate()}
              disabled={toggleIaMutation.isPending}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold border transition cursor-pointer ${
                iaActivaGlobal
                  ? 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100'
                  : 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
              }`}
            >
              <Power size={14} />
              <span>{iaActivaGlobal ? 'Suspender IA' : 'Habilitar IA'}</span>
            </button>

            <button
              type="button"
              onClick={abrirModalCrearIA}
              className="flex items-center gap-1.5 bg-uct-blue-primary hover:bg-uct-blue-hover text-white text-xs font-bold px-3.5 py-2 rounded-xl transition cursor-pointer shadow-xs"
            >
              <Plus size={15} />
              <span>Agregar API Key IA</span>
            </button>
          </div>
        </div>

        {/* Banner informativo de estado activo / fallback */}
        <div
          className={`rounded-xl p-3.5 border text-xs flex flex-wrap items-center justify-between gap-2 ${
            dataIA?.origen_activo === 'bd'
              ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
              : dataIA?.origen_activo === 'env'
              ? 'bg-amber-50 border-amber-200 text-amber-900'
              : 'bg-rose-50 border-rose-200 text-rose-900'
          }`}
        >
          <div className="flex items-center gap-2 font-medium">
            <Bot size={16} />
            {dataIA?.origen_activo === 'bd' ? (
              <span>
                Proveedor activo desde base de datos: <strong>{dataIA.proveedor_activo_resumen}</strong>
              </span>
            ) : dataIA?.origen_activo === 'env' ? (
              <span>
                Sin credencial activa en el panel. Operando con <strong>respaldo del archivo .env</strong> ({dataIA.proveedor_activo_resumen}).
              </span>
            ) : (
              <span>Sin proveedor de IA configurado. El asistente responderá solo en modo analítico local.</span>
            )}
          </div>
        </div>

        {/* Tabla de credenciales IA */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-600">
            <thead className="bg-slate-50 text-slate-700 font-bold border-y border-slate-200">
              <tr>
                <th className="py-2.5 px-3">Nombre</th>
                <th className="py-2.5 px-3">Proveedor</th>
                <th className="py-2.5 px-3">Modelo</th>
                <th className="py-2.5 px-3">API Key (Máscara)</th>
                <th className="py-2.5 px-3">Estado</th>
                <th className="py-2.5 px-3">Última Prueba</th>
                <th className="py-2.5 px-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cargandoIA ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-slate-400">
                    Cargando credenciales de IA...
                  </td>
                </tr>
              ) : !dataIA?.items?.length ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-slate-400">
                    No hay credenciales de IA registradas en base de datos.
                  </td>
                </tr>
              ) : (
                dataIA.items.map((item) => {
                  const nombreProv = mapaProveedores[item.provider_id]?.nombre || item.provider_id
                  const probando = probarIAMutation.isPending && probarIAMutation.variables === item.id
                  return (
                    <tr key={item.id} className="hover:bg-slate-50/70">
                      <td className="py-3 px-3 font-bold text-slate-900">{item.nombre}</td>
                      <td className="py-3 px-3">{nombreProv}</td>
                      <td className="py-3 px-3 font-mono text-[11px] text-slate-700">{item.modelo}</td>
                      <td className="py-3 px-3 font-mono text-[11px] text-slate-500">
                        {item.has_api_key ? item.key_hint : 'No requerida'}
                      </td>
                      <td className="py-3 px-3">
                        {item.es_activa ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 font-bold text-[11px]">
                            <CheckCircle2 size={12} /> Activa
                          </span>
                        ) : (
                          <span className="inline-flex px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 font-semibold text-[11px]">
                            Guardada
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-1.5">
                          {item.ultimo_test_ok === true && <CheckCircle2 size={13} className="text-emerald-600" />}
                          {item.ultimo_test_ok === false && <XCircle size={13} className="text-rose-600" />}
                          <span className="text-[11px] text-slate-500">{formatearFecha(item.ultimo_test_en)}</span>
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => probarIAMutation.mutate(item.id)}
                            disabled={probando}
                            className="px-2.5 py-1 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-700 font-semibold cursor-pointer disabled:opacity-50"
                            title="Probar conectividad real"
                          >
                            {probando ? 'Probando...' : 'Probar'}
                          </button>
                          {!item.es_activa && (
                            <button
                              type="button"
                              onClick={() => activarIAMutation.mutate(item.id)}
                              disabled={activarIAMutation.isPending}
                              className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold cursor-pointer disabled:opacity-50"
                            >
                              Activar
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => abrirModalEditarIA(item)}
                            className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-600 cursor-pointer"
                            title="Editar credencial"
                          >
                            <Edit3 size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={() => setItemAEliminar({ tipo: 'ia', item })}
                            className="p-1.5 rounded-lg border border-rose-200 hover:bg-rose-50 text-rose-600 cursor-pointer"
                            title="Eliminar definitivamente"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── SUBSECCIÓN 2: SERVIDOR DE CORREO SMTP ──────────────────────────── */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 space-y-5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-100 pb-4">
          <div className="flex items-start gap-3.5">
            <div className="w-11 h-11 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-700 flex items-center justify-center shrink-0">
              <Mail size={22} />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">Servidor de Correo Saliente (SMTP)</h2>
              <p className="text-xs text-slate-500 mt-1">
                Gestiona cuentas SMTP cifradas (personal o institucional UCT) para enlaces de activación, recuperación y despacho de reportes sin modificar el servidor.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={abrirModalCrearSMTP}
            className="flex items-center gap-1.5 bg-uct-blue-primary hover:bg-uct-blue-hover text-white text-xs font-bold px-3.5 py-2 rounded-xl transition cursor-pointer shadow-xs self-start lg:self-auto"
          >
            <Plus size={15} />
            <span>Agregar Perfil SMTP</span>
          </button>
        </div>

        {/* Aviso de origen SMTP activo */}
        <div
          className={`rounded-xl p-3.5 border text-xs flex items-center gap-2 font-medium ${
            dataSMTP?.origen_activo === 'bd'
              ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
              : dataSMTP?.origen_activo === 'env'
              ? 'bg-amber-50 border-amber-200 text-amber-900'
              : 'bg-rose-50 border-rose-200 text-rose-900'
          }`}
        >
          <ShieldCheck size={16} />
          {dataSMTP?.origen_activo === 'bd' ? (
            <span>Usando perfil SMTP configurado y cifrado en base de datos.</span>
          ) : dataSMTP?.origen_activo === 'env' ? (
            <span>
              Sin perfil SMTP activo en el panel. Operando con respaldo de <strong>.env</strong> ({dataSMTP.fallback_env_host} / {dataSMTP.fallback_env_user}).
            </span>
          ) : (
            <span>No hay servidor SMTP configurado. Los correos de activación y reportes no se enviarán.</span>
          )}
        </div>

        {/* Tabla de perfiles SMTP */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-600">
            <thead className="bg-slate-50 text-slate-700 font-bold border-y border-slate-200">
              <tr>
                <th className="py-2.5 px-3">Nombre</th>
                <th className="py-2.5 px-3">Servidor y Seguridad</th>
                <th className="py-2.5 px-3">Usuario / Remitente</th>
                <th className="py-2.5 px-3">Clave</th>
                <th className="py-2.5 px-3">Estado</th>
                <th className="py-2.5 px-3">Última Prueba</th>
                <th className="py-2.5 px-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cargandoSMTP ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-slate-400">
                    Cargando perfiles SMTP...
                  </td>
                </tr>
              ) : !dataSMTP?.items?.length ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-slate-400">
                    No hay perfiles SMTP registrados en base de datos.
                  </td>
                </tr>
              ) : (
                dataSMTP.items.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/70">
                    <td className="py-3 px-3 font-bold text-slate-900">{item.nombre}</td>
                    <td className="py-3 px-3 font-mono text-[11px]">
                      {item.host}:{item.port}{' '}
                      <span className="text-slate-400">
                        ({item.use_ssl ? 'SSL' : item.use_tls ? 'STARTTLS' : 'Plano'})
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      <div className="font-semibold text-slate-800">{item.from_email}</div>
                      <div className="text-[11px] text-slate-400">{item.username}</div>
                    </td>
                    <td className="py-3 px-3 font-mono text-[11px] text-slate-500">{item.password_hint}</td>
                    <td className="py-3 px-3">
                      {item.es_activa ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 font-bold text-[11px]">
                          <CheckCircle2 size={12} /> Activo
                        </span>
                      ) : (
                        <span className="inline-flex px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 font-semibold text-[11px]">
                          Guardado
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      <div className="flex items-center gap-1.5">
                        {item.ultimo_test_ok === true && <CheckCircle2 size={13} className="text-emerald-600" />}
                        {item.ultimo_test_ok === false && <XCircle size={13} className="text-rose-600" />}
                        <span className="text-[11px] text-slate-500">{formatearFecha(item.ultimo_test_en)}</span>
                      </div>
                    </td>
                    <td className="py-3 px-3">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => {
                            setSmtpTestTarget(item)
                            setSmtpTestEmail('')
                          }}
                          className="px-2.5 py-1 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-700 font-semibold cursor-pointer flex items-center gap-1"
                        >
                          <Send size={11} /> Probar
                        </button>
                        {!item.es_activa && (
                          <button
                            type="button"
                            onClick={() => activarSMTPMutation.mutate(item.id)}
                            disabled={activarSMTPMutation.isPending}
                            className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold cursor-pointer disabled:opacity-50"
                          >
                            Activar
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => abrirModalEditarSMTP(item)}
                          className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-600 cursor-pointer"
                          title="Editar perfil SMTP"
                        >
                          <Edit3 size={13} />
                        </button>
                        <button
                          type="button"
                          onClick={() => setItemAEliminar({ tipo: 'smtp', item })}
                          className="p-1.5 rounded-lg border border-rose-200 hover:bg-rose-50 text-rose-600 cursor-pointer"
                          title="Eliminar definitivamente"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── MODAL ALTA / EDICIÓN CREDENCIAL IA ──────────────────────────────── */}
      {modalIAOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-sm font-bold text-slate-900">
                {editandoIA ? 'Editar Credencial de IA' : 'Nueva Credencial de Proveedor IA'}
              </h3>
              <button type="button" onClick={() => setModalIAOpen(false)} className="text-slate-400 hover:text-slate-700 cursor-pointer">
                <X size={18} />
              </button>
            </div>

            {iaFormError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs font-semibold text-rose-700">
                {iaFormError}
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault()
                setIaFormError(null)
                guardarIAMutation.mutate()
              }}
              className="space-y-3.5 text-xs"
            >
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Nombre descriptivo</label>
                <input
                  type="text"
                  required
                  value={iaNombre}
                  onChange={(e) => setIaNombre(e.target.value)}
                  placeholder="Ej. Gemini UCT Principal o Claude Respaldo"
                  className="w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:border-uct-blue-primary"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Proveedor de IA</label>
                <select
                  value={iaProvider}
                  onChange={(e) => handleCambiarProveedorIA(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-xl bg-white focus:outline-none focus:border-uct-blue-primary"
                >
                  {catalogo.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nombre}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Modelo</label>
                <select
                  value={iaModelo}
                  onChange={(e) => setIaModelo(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-xl bg-white focus:outline-none focus:border-uct-blue-primary"
                >
                  {(proveedorMetaActual?.modelos_sugeridos || []).map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                  <option value="__custom__">Otro modelo (escribir identificador manualmente)...</option>
                </select>
                {iaModelo === '__custom__' && (
                  <input
                    type="text"
                    required
                    value={iaModeloCustom}
                    onChange={(e) => setIaModeloCustom(e.target.value)}
                    placeholder="Ej. gpt-4.1-nano o claude-3-5-sonnet-20241022"
                    className="w-full mt-2 px-3 py-2 border border-slate-200 rounded-xl font-mono focus:outline-none focus:border-uct-blue-primary"
                  />
                )}
              </div>

              {(iaProvider === 'ollama' || iaProvider === 'custom' || Boolean(iaBaseUrl)) && (
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">URL Base del Endpoint</label>
                  <input
                    type="url"
                    required={Boolean(proveedorMetaActual?.requires_base_url)}
                    value={iaBaseUrl}
                    onChange={(e) => setIaBaseUrl(e.target.value)}
                    placeholder="https://api.ejemplo.com/v1"
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl font-mono focus:outline-none focus:border-uct-blue-primary"
                  />
                </div>
              )}

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  API Key {editandoIA ? '(dejar vacío para conservar la actual)' : ''}
                </label>
                <input
                  type="password"
                  autoComplete="new-password"
                  required={!editandoIA && Boolean(proveedorMetaActual?.requires_api_key ?? true)}
                  value={iaApiKey}
                  onChange={(e) => setIaApiKey(e.target.value)}
                  placeholder={editandoIA ? `Actual: ${editandoIA.key_hint}` : 'Pegar API Key secreta'}
                  className="w-full px-3 py-2 border border-slate-200 rounded-xl font-mono focus:outline-none focus:border-uct-blue-primary"
                />
              </div>

              {!editandoIA && (
                <label className="flex items-center gap-2 text-slate-700 font-medium cursor-pointer pt-1">
                  <input
                    type="checkbox"
                    checked={iaActivar}
                    onChange={(e) => setIaActivar(e.target.checked)}
                    className="rounded border-slate-300"
                  />
                  <span>Activar este proveedor inmediatamente para toda la plataforma</span>
                </label>
              )}

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setModalIAOpen(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardarIAMutation.isPending}
                  className="px-4 py-2 rounded-xl bg-uct-blue-primary hover:bg-uct-blue-hover text-white font-bold cursor-pointer disabled:opacity-50"
                >
                  {guardarIAMutation.isPending ? 'Guardando...' : 'Guardar Cifrada'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ─── MODAL ALTA / EDICIÓN PERFIL SMTP ─────────────────────────────────── */}
      {modalSMTPOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-sm font-bold text-slate-900">
                {editandoSMTP ? 'Editar Perfil SMTP' : 'Nuevo Perfil de Servidor SMTP'}
              </h3>
              <button type="button" onClick={() => setModalSMTPOpen(false)} className="text-slate-400 hover:text-slate-700 cursor-pointer">
                <X size={18} />
              </button>
            </div>

            {smtpFormError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs font-semibold text-rose-700">
                {smtpFormError}
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault()
                setSmtpFormError(null)
                guardarSMTPMutation.mutate()
              }}
              className="space-y-3 text-xs"
            >
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Nombre del perfil</label>
                <input
                  type="text"
                  required
                  value={smtpNombre}
                  onChange={(e) => setSmtpNombre(e.target.value)}
                  placeholder="Ej. Correo Institucional UCT"
                  className="w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:border-uct-blue-primary"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="block font-semibold text-slate-700 mb-1">Servidor SMTP (Host)</label>
                  <input
                    type="text"
                    required
                    value={smtpHost}
                    onChange={(e) => setSmtpHost(e.target.value)}
                    placeholder="smtp.uct.cl"
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl font-mono focus:outline-none focus:border-uct-blue-primary"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Puerto</label>
                  <select
                    value={smtpPort}
                    onChange={(e) => {
                      const p = Number(e.target.value)
                      setSmtpPort(p)
                      if (p === 465) setSmtpSeguridad('ssl')
                      else if (p === 587) setSmtpSeguridad('starttls')
                    }}
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl bg-white focus:outline-none focus:border-uct-blue-primary"
                  >
                    <option value={587}>587</option>
                    <option value={465}>465</option>
                    <option value={25}>25</option>
                    <option value={2525}>2525</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Cifrado de transporte</label>
                <select
                  value={smtpSeguridad}
                  onChange={(e) => setSmtpSeguridad(e.target.value as 'starttls' | 'ssl' | 'ninguno')}
                  className="w-full px-3 py-2 border border-slate-200 rounded-xl bg-white focus:outline-none focus:border-uct-blue-primary"
                >
                  <option value="starttls">STARTTLS (recomendado puerto 587)</option>
                  <option value="ssl">SSL / TLS directo (puerto 465)</option>
                  <option value="ninguno">Sin cifrado (solo relay interno)</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Usuario SMTP</label>
                  <input
                    type="text"
                    required
                    value={smtpUser}
                    onChange={(e) => setSmtpUser(e.target.value)}
                    placeholder="notificaciones@uct.cl"
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:border-uct-blue-primary"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    Contraseña {editandoSMTP ? '(opcional al editar)' : ''}
                  </label>
                  <input
                    type="password"
                    autoComplete="new-password"
                    required={!editandoSMTP}
                    value={smtpPassword}
                    onChange={(e) => setSmtpPassword(e.target.value)}
                    placeholder={editandoSMTP ? `Actual: ${editandoSMTP.password_hint}` : 'Contraseña o App Password'}
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl font-mono focus:outline-none focus:border-uct-blue-primary"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Correo remitente</label>
                  <input
                    type="email"
                    required
                    value={smtpFromEmail}
                    onChange={(e) => setSmtpFromEmail(e.target.value)}
                    placeholder="dss@uct.cl"
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:border-uct-blue-primary"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Nombre remitente</label>
                  <input
                    type="text"
                    required
                    value={smtpFromName}
                    onChange={(e) => setSmtpFromName(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:border-uct-blue-primary"
                  />
                </div>
              </div>

              {!editandoSMTP && (
                <label className="flex items-center gap-2 text-slate-700 font-medium cursor-pointer pt-1">
                  <input
                    type="checkbox"
                    checked={smtpActivar}
                    onChange={(e) => setSmtpActivar(e.target.checked)}
                    className="rounded border-slate-300"
                  />
                  <span>Activar este servidor SMTP inmediatamente</span>
                </label>
              )}

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setModalSMTPOpen(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardarSMTPMutation.isPending}
                  className="px-4 py-2 rounded-xl bg-uct-blue-primary hover:bg-uct-blue-hover text-white font-bold cursor-pointer disabled:opacity-50"
                >
                  {guardarSMTPMutation.isPending ? 'Guardando...' : 'Guardar Perfil SMTP'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ─── MODAL PRUEBA DE ENVÍO SMTP ───────────────────────────────────────── */}
      {smtpTestTarget && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-sm font-bold text-slate-900">Enviar Correo de Prueba SMTP</h3>
              <button type="button" onClick={() => setSmtpTestTarget(null)} className="text-slate-400 hover:text-slate-700 cursor-pointer">
                <X size={18} />
              </button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                probarSMTPMutation.mutate({
                  id: smtpTestTarget.id,
                  email: smtpTestEmail.trim() || undefined,
                })
              }}
              className="space-y-3 text-xs"
            >
              <p className="text-slate-600">
                Se enviará un mensaje de verificación usando <strong>{smtpTestTarget.nombre}</strong> ({smtpTestTarget.host}:{smtpTestTarget.port}).
              </p>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Destinatario (opcional)</label>
                <input
                  type="email"
                  value={smtpTestEmail}
                  onChange={(e) => setSmtpTestEmail(e.target.value)}
                  placeholder="Dejar vacío para enviar a tu correo de sesión"
                  className="w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:border-uct-blue-primary"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setSmtpTestTarget(null)}
                  className="px-4 py-2 rounded-xl border border-slate-200 font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={probarSMTPMutation.isPending}
                  className="px-4 py-2 rounded-xl bg-uct-blue-primary hover:bg-uct-blue-hover text-white font-bold cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
                >
                  <Activity size={14} />
                  <span>{probarSMTPMutation.isPending ? 'Enviando...' : 'Enviar Prueba'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ─── MODAL CONFIRMACIÓN DE ELIMINACIÓN DEFINITIVA ─────────────────────── */}
      {itemAEliminar && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-rose-200 shadow-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-rose-100 text-rose-600 flex items-center justify-center shrink-0">
                <Trash2 size={20} />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900">Eliminar definitivamente</h3>
                <p className="text-xs text-slate-600 mt-1">
                  Se borrará físicamente el registro <strong>{itemAEliminar.item.nombre}</strong> junto con su credencial cifrada en base de datos. Esta acción no se puede deshacer.
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setItemAEliminar(null)}
                className="px-4 py-2 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => eliminarMutation.mutate(itemAEliminar)}
                disabled={eliminarMutation.isPending}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold cursor-pointer disabled:opacity-50"
              >
                {eliminarMutation.isPending ? 'Eliminando...' : 'Confirmar Eliminación'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
