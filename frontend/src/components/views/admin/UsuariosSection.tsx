import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Users,
  Bot,
  UserPlus,
  Search,
  CheckCircle2,
  AlertTriangle,
  Lock,
  Unlock,
  KeyRound,
  Trash2,
  Clock,
  Cpu,
  Save,
  Eye,
  EyeOff,
  Copy,
  X,
  BookOpen,
  Car,
  ShieldAlert,
  BotOff,
  Mail,
  RefreshCw,
} from 'lucide-react'
import { api, deleteUser, forgotPassword, inviteUser } from '../../../api/client'
import { useAuth } from '../../../context/AuthContext'

interface RoleItem {
  id: number
  nombre: string
  descripcion?: string
  rate_limit_quota?: string
  cooldown_segundos?: number
}

interface UserItem {
  id: number
  email: string
  nombre_completo: string
  is_active: boolean
  can_use_ai?: boolean
  intentos_fallidos_login?: number
  bloqueado_hasta?: string | null
  created_at: string
  roles: RoleItem[]
  allowed_datasets: string[]
}

interface GlobalConfig {
  id: number
  ia_asistente_activo: boolean
  active_provider?: string
  default_model?: string
  has_api_key?: boolean
  masked_api_key?: string
  updated_at?: string
}

const ROLES_PREDETERMINADOS: RoleItem[] = [
  { id: 1, nombre: 'Admin_Sistema', descripcion: 'SuperAdmin técnico global con control total de la plataforma', rate_limit_quota: '1000/day', cooldown_segundos: 5 },
  { id: 2, nombre: 'Director_Recinto', descripcion: 'Jefatura de espacio físico asignado (Biblioteca / Estacionamientos)', rate_limit_quota: '500/day', cooldown_segundos: 10 },
  { id: 3, nombre: 'Analista_Consulta', descripcion: 'Decanos, directores de carrera y analistas institucionales', rate_limit_quota: '200/day', cooldown_segundos: 15 },
  { id: 4, nombre: 'Guardia_Seguridad', descripcion: 'Operador en terreno para control de aforo y tránsito', rate_limit_quota: '50/day', cooldown_segundos: 30 },
  { id: 5, nombre: 'Consultor_Reporte', descripcion: 'Solicitante institucional con acceso a sus reportes ejecutivos', rate_limit_quota: '50/day', cooldown_segundos: 30 },
]

export const UsuariosSection: React.FC = () => {
  const { isSuperAdmin, isDirectivo } = useAuth()
  const isSuperAdminOrDirectivo = isSuperAdmin || isDirectivo
  const queryClient = useQueryClient()

  const [searchQuery, setSearchQuery] = useState('')
  const [userToDelete, setUserToDelete] = useState<UserItem | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newRole, setNewRole] = useState('Guardia_Seguridad')
  const [newDatasets, setNewDatasets] = useState<string[]>(['biblioteca', 'estacionamiento'])
  const [modalError, setModalError] = useState<string | null>(null)

  // Estados para configuración de IA
  const [providerInput, setProviderInput] = useState('gemini')
  const [modelInput, setModelInput] = useState('gemini-2.5-flash')
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)
  const [configSuccessMsg, setConfigSuccessMsg] = useState<string | null>(null)
  const [configErrorMsg, setConfigErrorMsg] = useState<string | null>(null)
  const [userActionMsg, setUserActionMsg] = useState<string | null>(null)
  const [invitationSuccess, setInvitationSuccess] = useState<{
    email: string
    nombre: string
    enlace: string
    temporal?: string
  } | null>(null)

  // Consultas
  const { data: configData, isLoading: isConfigLoading } = useQuery<GlobalConfig>({
    queryKey: ['global-config'],
    queryFn: async () => {
      const res = await api.get('/admin/config')
      return res.data
    },
    enabled: isSuperAdmin,
  })

  const { data: usersList = [], isLoading: isUsersLoading, refetch: refetchUsers } = useQuery<UserItem[]>({
    queryKey: ['admin-users'],
    queryFn: async () => {
      const res = await api.get('/auth/users')
      return res.data
    },
    enabled: isSuperAdminOrDirectivo,
  })

  const { data: rolesList = [] } = useQuery<RoleItem[]>({
    queryKey: ['admin-roles'],
    queryFn: async () => {
      const res = await api.get('/auth/roles')
      return res.data
    },
    enabled: isSuperAdminOrDirectivo,
  })

  // Roles filtrados según permisos jerárquicos delegados
  const rolesDisponibles = React.useMemo(() => {
    const base = rolesList.length > 0 ? rolesList : ROLES_PREDETERMINADOS
    if (!isSuperAdmin && isDirectivo) {
      return base.filter((r) => r.nombre === 'Analista_Consulta' || r.nombre === 'Guardia_Seguridad')
    }
    return base
  }, [rolesList, isSuperAdmin, isDirectivo])

  // Estados para cuotas y tiempos por rol
  const [roleDrafts, setRoleDrafts] = useState<Record<number, { quota: string; cooldown: number }>>({})
  const [roleActionMsg, setRoleActionMsg] = useState<{ id: number; text: string; error?: boolean } | null>(null)

  const updateRoleQuotaMutation = useMutation({
    mutationFn: async ({ roleId, rate_limit_quota, cooldown_segundos }: { roleId: number; rate_limit_quota: string; cooldown_segundos: number }) => {
      const res = await api.put(`/admin/roles/${roleId}/ia-quota`, {
        rate_limit_quota,
        cooldown_segundos,
      })
      return res.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-roles'] })
      setRoleActionMsg({ id: data.id, text: 'Configuración guardada exitosamente' })
      setTimeout(() => setRoleActionMsg(null), 3500)
    },
    onError: (err: any, vars) => {
      setRoleActionMsg({ id: vars.roleId, text: err?.response?.data?.detail || 'Error al guardar política', error: true })
      setTimeout(() => setRoleActionMsg(null), 4000)
    },
  })

  // Mutaciones
  const toggleMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post('/admin/config/toggle-ia')
      return res.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['global-config'] })
      queryClient.invalidateQueries({ queryKey: ['ia-status'] })
      queryClient.invalidateQueries({ queryKey: ['assistant-status'] })
      setUserActionMsg(
        data.ia_asistente_activo
          ? 'Asistente de IA habilitado exitosamente en toda la plataforma.'
          : 'Asistente de IA deshabilitado globalmente. Se han ocultado todos los accesos en el sistema.'
      )
      setTimeout(() => setUserActionMsg(null), 5000)
    },
    onError: (err: any) => {
      setUserActionMsg(err?.response?.data?.detail || 'Error al alternar el estado del Asistente de IA.')
      setTimeout(() => setUserActionMsg(null), 5000)
    },
  })

  const saveConfigMutation = useMutation({
    mutationFn: async () => {
      const payload: any = {
        active_provider: providerInput,
        default_model: modelInput,
      }
      if (apiKeyInput.trim()) {
        payload.api_key = apiKeyInput.trim()
      }
      const res = await api.put('/admin/config', payload)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['global-config'] })
      setConfigSuccessMsg('Configuración de IA guardada con éxito.')
      setApiKeyInput('')
      setTimeout(() => setConfigSuccessMsg(null), 4000)
    },
    onError: (err: any) => {
      setConfigErrorMsg(err?.response?.data?.detail || 'Error al guardar la configuración.')
      setTimeout(() => setConfigErrorMsg(null), 5000)
    },
  })

  const createUserMutation = useMutation({
    mutationFn: async (payload: {
      email: string
      nombre_completo: string
      roles: string[]
      allowed_datasets: string[]
    }) => {
      return await inviteUser(payload)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      setIsModalOpen(false)
      setNewName('')
      setNewEmail('')
      setNewRole('Guardia_Seguridad')
      setNewDatasets(['biblioteca', 'estacionamiento'])
      setModalError(null)

      setInvitationSuccess({
        email: data.usuario.email,
        nombre: data.usuario.nombre_completo,
        enlace: data.enlace_activacion,
        temporal: data.token_temporal,
      })
    },
    onError: (err: any) => {
      setModalError(err?.response?.data?.detail || 'Error al invitar al usuario.')
    },
  })

  const deleteUserMutation = useMutation({
    mutationFn: async (userId: number) => {
      return await deleteUser(userId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      setUserToDelete(null)
      setUserActionMsg('Usuario eliminado exitosamente.')
      setTimeout(() => setUserActionMsg(null), 4000)
    },
    onError: (err: any) => {
      setUserActionMsg(err?.response?.data?.detail || 'Error al eliminar usuario.')
      setTimeout(() => setUserActionMsg(null), 5000)
    },
  })

  const unlockMutation = useMutation({
    mutationFn: async (userId: number) => {
      const res = await api.post(`/auth/users/${userId}/unlock`)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      setUserActionMsg('Cuenta desbloqueada con éxito.')
      setTimeout(() => setUserActionMsg(null), 4000)
    },
  })

  const toggleUserStatusMutation = useMutation({
    mutationFn: async ({ userId, is_active }: { userId: number; is_active: boolean }) => {
      const res = await api.patch(`/auth/users/${userId}/status`, { is_active })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      setUserActionMsg('Estado de activación de usuario actualizado.')
      setTimeout(() => setUserActionMsg(null), 4000)
    },
    onError: (err: any) => {
      setUserActionMsg(err?.response?.data?.detail || 'Error al actualizar estado del usuario.')
      setTimeout(() => setUserActionMsg(null), 5000)
    },
  })

  const toggleUserAiMutation = useMutation({
    mutationFn: async ({ userId, can_use_ai }: { userId: number; can_use_ai: boolean }) => {
      const res = await api.patch(`/auth/users/${userId}/status`, { can_use_ai })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      setUserActionMsg('Permiso de Asistente IA de usuario actualizado.')
      setTimeout(() => setUserActionMsg(null), 4000)
    },
    onError: (err: any) => {
      setUserActionMsg(err?.response?.data?.detail || 'Error al actualizar permiso de IA.')
      setTimeout(() => setUserActionMsg(null), 5000)
    },
  })

  const resendInvitationMutation = useMutation({
    mutationFn: async (userId: number) => {
      const res = await api.post(`/auth/users/${userId}/resend-invitation`)
      return res.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      setInvitationSuccess({
        email: data.usuario.email,
        nombre: data.usuario.nombre_completo,
        enlace: data.enlace_activacion,
        temporal: data.token_temporal,
      })
      setUserActionMsg(`Enlace de acceso y credencial generado para ${data.usuario.email}.`)
      setTimeout(() => setUserActionMsg(null), 5000)
    },
    onError: (err: any) => {
      setUserActionMsg(err?.response?.data?.detail || 'Error al generar enlace de restablecimiento / invitación.')
      setTimeout(() => setUserActionMsg(null), 5000)
    },
  })

  const handleDatasetCheckbox = (dataset: string) => {
    setNewDatasets((prev) =>
      prev.includes(dataset) ? prev.filter((d) => d !== dataset) : [...prev, dataset]
    )
  }

  const isAiActive = configData ? configData.ia_asistente_activo : true

  const filteredUsers = usersList.filter(
    (u) =>
      u.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.nombre_completo.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.roles.some((r) => r.nombre.toLowerCase().includes(searchQuery.toLowerCase()))
  )

  return (
    <div className="space-y-6">
      {/* Tarjeta de Control Maestro de IA (Solo SuperAdmin) */}
      {isSuperAdmin && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-start gap-4">
              <div
                className={`w-12 h-12 rounded-xl flex items-center justify-center border transition-colors ${
                  isAiActive
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-600'
                    : 'bg-rose-50 border-rose-200 text-rose-600'
                }`}
              >
                <Bot size={26} />
              </div>
              <div>
                <div className="flex items-center gap-2.5">
                  <h2 className="text-base font-bold text-slate-900">Control de IA y Asistente Analítico</h2>
                  <span
                    className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                      isAiActive
                        ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                        : 'bg-rose-100 text-rose-800 border border-rose-200'
                    }`}
                  >
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        isAiActive ? 'bg-emerald-600 animate-pulse' : 'bg-rose-600'
                      }`}
                    />
                    {isAiActive ? 'Servicio Activo' : 'Servicio Desactivado'}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1 max-w-xl">
                  Interruptor maestro para habilitar o suspender temporalmente el Asistente Analítico Gemini en toda la plataforma.
                </p>
              </div>
            </div>

            <button
              onClick={() => toggleMutation.mutate()}
              disabled={isConfigLoading || toggleMutation.isPending}
              aria-label="Alternar estado de IA"
              className={`relative inline-flex h-8 w-16 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-50 ${
                isAiActive ? 'bg-emerald-500' : 'bg-slate-300'
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-7 w-7 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out flex items-center justify-center ${
                  isAiActive ? 'translate-x-8' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>
      )}

      {/* Tarjeta de Políticas de Consumo y Cuotas de IA por Rol (Solo SuperAdmin) */}
      {isSuperAdmin && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center">
                <Clock size={22} />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Políticas de Consumo y Cuotas de IA por Rol Institucional
                </h3>
                <p className="text-xs text-slate-500">
                  Configure la cuota diaria de consultas analíticas y el tiempo mínimo de espera (cooldown) por rol para prevenir agotamiento de tokens.
                </p>
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50 text-slate-700 font-bold border-y border-slate-200">
                <tr>
                  <th className="py-2.5 px-3">Rol Institucional</th>
                  <th className="py-2.5 px-3">Descripción</th>
                  <th className="py-2.5 px-3">Cuota Diaria (Preguntas/Día)</th>
                  <th className="py-2.5 px-3">Tiempo Mínimo Entre Preguntas</th>
                  <th className="py-2.5 px-3 text-right">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {(rolesList.length > 0 ? rolesList : ROLES_PREDETERMINADOS).map((rol) => {
                  const draft = roleDrafts[rol.id] || {
                    quota: rol.rate_limit_quota || '50/day',
                    cooldown: rol.cooldown_segundos ?? 10,
                  }
                  const isPending = updateRoleQuotaMutation.isPending && (updateRoleQuotaMutation.variables as any)?.roleId === rol.id
                  const msg = roleActionMsg?.id === rol.id ? roleActionMsg : null

                  return (
                    <tr key={rol.id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-3 px-3">
                        <span className="font-bold text-slate-800 bg-slate-100 px-2.5 py-1 rounded-md text-[11px] border border-slate-200 font-mono">
                          {rol.nombre}
                        </span>
                      </td>
                      <td className="py-3 px-3 max-w-xs text-slate-500 text-[11px]">
                        {rol.descripcion || 'Sin descripción'}
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-1.5">
                          <input
                            type="text"
                            value={draft.quota}
                            onChange={(e) =>
                              setRoleDrafts((prev) => ({
                                ...prev,
                                [rol.id]: { ...draft, quota: e.target.value },
                              }))
                            }
                            placeholder="ej. 50/day o ilimitado"
                            className="w-28 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1 text-slate-800 text-xs font-mono focus:bg-white focus:ring-1 focus:ring-indigo-400 focus:outline-none"
                          />
                          <select
                            value={draft.quota}
                            onChange={(e) =>
                              setRoleDrafts((prev) => ({
                                ...prev,
                                [rol.id]: { ...draft, quota: e.target.value },
                              }))
                            }
                            className="bg-slate-100 border border-slate-200 rounded-lg px-2 py-1 text-[11px] text-slate-700 cursor-pointer"
                          >
                            <option value="ilimitado">Ilimitado</option>
                            <option value="1000/day">1000/día</option>
                            <option value="500/day">500/día</option>
                            <option value="200/day">200/día</option>
                            <option value="100/day">100/día</option>
                            <option value="50/day">50/día</option>
                            <option value="25/day">25/día</option>
                            <option value="10/day">10/día</option>
                            <option value="5/day">5/día</option>
                          </select>
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-2">
                          <select
                            value={draft.cooldown}
                            onChange={(e) =>
                              setRoleDrafts((prev) => ({
                                ...prev,
                                [rol.id]: { ...draft, cooldown: Number(e.target.value) },
                              }))
                            }
                            className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 text-slate-800 text-xs font-mono cursor-pointer focus:bg-white focus:ring-1 focus:ring-indigo-400 focus:outline-none"
                          >
                            <option value={0}>Sin espera (0 seg)</option>
                            <option value={5}>5 segundos</option>
                            <option value={10}>10 segundos</option>
                            <option value={15}>15 segundos</option>
                            <option value={30}>30 segundos</option>
                            <option value={60}>60 segundos (1 min)</option>
                            <option value={120}>120 segundos (2 min)</option>
                          </select>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {msg && (
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                msg.error ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'
                              }`}
                            >
                              {msg.text}
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={() =>
                              updateRoleQuotaMutation.mutate({
                                roleId: rol.id,
                                rate_limit_quota: draft.quota,
                                cooldown_segundos: draft.cooldown,
                              })
                            }
                            disabled={isPending}
                            className="inline-flex items-center gap-1.5 px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer shadow-xs"
                          >
                            <Save size={13} />
                            <span>{isPending ? 'Guardando...' : 'Guardar'}</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Mensajes de Notificación */}
      {userActionMsg && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-800 rounded-xl flex items-center gap-2">
          <CheckCircle2 size={16} className="text-emerald-500" />
          <span>{userActionMsg}</span>
        </div>
      )}

      {invitationSuccess && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-xs space-y-2">
          <div className="flex items-center justify-between font-bold text-emerald-900">
            <span>Invitación enviada a {invitationSuccess.email}</span>
            <button
              onClick={() => setInvitationSuccess(null)}
              className="text-slate-400 hover:text-slate-600 cursor-pointer"
            >
              <X size={14} />
            </button>
          </div>
          <p className="text-emerald-800 text-[11px]">
            Enlace de activación generado (expira en 48 horas):
          </p>
          <div className="flex items-center gap-2 bg-white p-2 rounded-lg border border-emerald-200">
            <span className="font-mono text-[10px] text-slate-700 truncate flex-1">
              {invitationSuccess.enlace}
            </span>
            <button
              onClick={() => navigator.clipboard.writeText(invitationSuccess.enlace)}
              className="text-emerald-700 hover:text-emerald-900 font-bold text-[11px] flex items-center gap-1 cursor-pointer"
            >
              <Copy size={12} />
              <span>Copiar</span>
            </button>
          </div>
        </div>
      )}

      {/* Tabla de Usuarios Registrados */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden space-y-4 p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">Usuarios y Credenciales del Sistema</h3>
            <p className="text-xs text-slate-500">
              Control de acceso basado en roles (RBAC) conforme al marco normativo de privacidad de la Universidad.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative">
              <Search size={15} className="absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Buscar por nombre, email o rol..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none w-64"
              />
            </div>

            <button
              type="button"
              onClick={() => setIsModalOpen(true)}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-uct-blue-primary hover:bg-uct-blue-hover text-white text-xs font-bold rounded-xl shadow-xs transition cursor-pointer"
            >
              <UserPlus size={14} />
              <span>Invitar Usuario</span>
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/75 text-[11px] uppercase font-bold text-slate-500 tracking-wider">
                <th className="py-2.5 px-3">Usuario</th>
                <th className="py-2.5 px-3">Rol Asignado</th>
                <th className="py-2.5 px-3">Datasets</th>
                <th className="py-2.5 px-3">Estado</th>
                <th className="py-2.5 px-3">Acceso IA</th>
                <th className="py-2.5 px-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {isUsersLoading ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-slate-400">Cargando usuarios...</td>
                </tr>
              ) : filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-slate-400">No se encontraron usuarios coincidentes.</td>
                </tr>
              ) : (
                filteredUsers.map((u) => {
                  const estaBloqueado = Boolean(u.bloqueado_hasta && new Date(u.bloqueado_hasta) > new Date())
                  return (
                    <tr key={u.id} className="hover:bg-slate-50/50 transition">
                      <td className="py-3 px-3">
                        <span className="font-bold text-slate-900 block">{u.nombre_completo}</span>
                        <span className="text-slate-500 text-[11px]">{u.email}</span>
                      </td>
                      <td className="py-3 px-3">
                        {u.roles.map((r) => (
                          <span
                            key={r.id}
                            className="inline-block px-2 py-0.5 rounded-md text-[10px] font-bold uppercase bg-blue-50 text-uct-blue-primary border border-blue-200 mr-1"
                          >
                            {r.nombre}
                          </span>
                        ))}
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-1">
                          {(u.allowed_datasets || []).map((ds) => (
                            <span key={ds} className="text-[10px] font-medium bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">
                              {ds}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        {estaBloqueado ? (
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full border border-rose-200">
                            <Lock size={11} /> Bloqueado
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => toggleUserStatusMutation.mutate({ userId: u.id, is_active: !u.is_active })}
                            title={u.is_active ? 'Haga clic para deshabilitar usuario' : 'Haga clic para activar usuario'}
                            className={`inline-flex items-center gap-1 text-[10px] font-bold px-2.5 py-0.5 rounded-full border transition cursor-pointer ${
                              u.is_active
                                ? 'text-emerald-700 bg-emerald-50 border-emerald-200 hover:bg-emerald-100'
                                : 'text-slate-600 bg-slate-100 border-slate-200 hover:bg-slate-200'
                            }`}
                          >
                            <span className={`w-1.5 h-1.5 rounded-full ${u.is_active ? 'bg-emerald-600' : 'bg-slate-400'}`} />
                            <span>{u.is_active ? 'Activo' : 'Inactivo'}</span>
                          </button>
                        )}
                      </td>
                      <td className="py-3 px-3">
                        <button
                          type="button"
                          onClick={() => toggleUserAiMutation.mutate({ userId: u.id, can_use_ai: !u.can_use_ai })}
                          title={u.can_use_ai ? 'Haga clic para revocar acceso a IA' : 'Haga clic para autorizar uso de IA'}
                          className={`inline-flex items-center gap-1.5 text-[10px] font-bold px-2.5 py-0.5 rounded-full border transition cursor-pointer ${
                            u.can_use_ai
                              ? 'text-purple-700 bg-purple-50 border-purple-200 hover:bg-purple-100'
                              : 'text-slate-500 bg-slate-100 border-slate-200 hover:bg-slate-200'
                          }`}
                        >
                          {u.can_use_ai ? <Bot size={12} className="text-purple-600" /> : <BotOff size={12} className="text-slate-400" />}
                          <span>{u.can_use_ai ? 'Habilitado' : 'Deshabilitado'}</span>
                        </button>
                      </td>
                      <td className="py-3 px-3 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => resendInvitationMutation.mutate(u.id)}
                            disabled={resendInvitationMutation.isPending}
                            className="p-1.5 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-lg transition cursor-pointer"
                            title="Reenviar enlace de activación / reseteo de contraseña"
                          >
                            <KeyRound size={14} />
                          </button>
                          {estaBloqueado && (
                            <button
                              type="button"
                              onClick={() => unlockMutation.mutate(u.id)}
                              className="p-1.5 text-amber-600 hover:bg-amber-50 rounded-lg transition cursor-pointer"
                              title="Desbloquear usuario"
                            >
                              <Unlock size={14} />
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => setUserToDelete(u)}
                            className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition cursor-pointer"
                            title="Eliminar usuario"
                          >
                            <Trash2 size={14} />
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

      {/* Modal Invitar Usuario */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 overflow-y-auto">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-md w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <UserPlus size={18} className="text-uct-blue-primary" />
                <h3 className="text-sm font-bold text-slate-900">Invitar Nuevo Usuario</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-lg transition cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault()
                createUserMutation.mutate({
                  nombre_completo: newName,
                  email: newEmail,
                  roles: [newRole],
                  allowed_datasets: newDatasets,
                })
              }}
              className="p-5 space-y-4"
            >
              {modalError && (
                <div className="p-3 bg-rose-50 text-rose-700 text-xs rounded-xl border border-rose-100 flex items-center gap-2">
                  <AlertTriangle size={14} className="shrink-0" />
                  <span>{modalError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Nombre Completo</label>
                <input
                  type="text"
                  required
                  placeholder="Ej. Dr. Juan Pérez Soto"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Correo Institucional (@uct.cl)</label>
                <input
                  type="email"
                  required
                  placeholder="usuario@uct.cl"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Rol Institucional</label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:outline-none"
                >
                  {rolesDisponibles.map((r) => (
                    <option key={r.id} value={r.nombre}>
                      {r.nombre} — {r.descripcion}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">Módulos / Datasets Autorizados</label>
                <div className="flex items-center gap-4 text-xs text-slate-700">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={newDatasets.includes('biblioteca')}
                      onChange={() => handleDatasetCheckbox('biblioteca')}
                      className="rounded text-uct-blue-primary focus:ring-uct-blue-primary/40"
                    />
                    <span>Biblioteca</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={newDatasets.includes('estacionamiento')}
                      onChange={() => handleDatasetCheckbox('estacionamiento')}
                      className="rounded text-uct-blue-primary focus:ring-uct-blue-primary/40"
                    />
                    <span>Estacionamiento</span>
                  </label>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-3.5 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={createUserMutation.isPending}
                  className="px-4 py-2 bg-uct-blue-primary hover:bg-uct-blue-hover text-white text-xs font-bold rounded-xl transition shadow-xs cursor-pointer disabled:opacity-50"
                >
                  {createUserMutation.isPending ? 'Enviando...' : 'Enviar Invitación'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Confirmación Eliminación */}
      {userToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-sm w-full p-5 space-y-4">
            <div className="flex items-center gap-3 text-red-600">
              <div className="p-2 bg-red-50 rounded-xl">
                <ShieldAlert size={20} />
              </div>
              <h3 className="text-sm font-bold text-slate-900">¿Eliminar Usuario?</h3>
            </div>
            <p className="text-xs text-slate-600">
              Se revocará el acceso inmediatamente a <strong className="text-slate-800">{userToDelete.email}</strong>. Esta acción no se puede deshacer.
            </p>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setUserToDelete(null)}
                className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg transition cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={deleteUserMutation.isPending}
                onClick={() => deleteUserMutation.mutate(userToDelete.id)}
                className="px-3.5 py-1.5 text-xs font-bold text-white bg-red-600 hover:bg-red-700 rounded-lg transition shadow-xs cursor-pointer disabled:opacity-50"
              >
                {deleteUserMutation.isPending ? 'Eliminando...' : 'Confirmar Eliminación'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

