import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ShieldCheck,
  Bot,
  Users,
  Power,
  RefreshCw,
  Lock,
  Mail,
  Clock,
  Sparkles,
  AlertTriangle,
  UserPlus,
  X,
  BookOpen,
  Car,
  Activity,
  Eye,
  EyeOff,
  Cpu,
  Save,
  CheckCircle2,
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { api } from '../../api/client'
import { ChatAuditSection } from './ChatAuditSection'

interface RoleItem {
  id: number
  nombre: string
  descripcion?: string
}

interface UserItem {
  id: number
  email: string
  nombre_completo: string
  is_active: boolean
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


export const AdminDashboard: React.FC = () => {
  const { isAuthenticated, isSuperAdmin, userRole, loginWithCredentials, logout } = useAuth()
  const queryClient = useQueryClient()

  const [adminTab, setAdminTab] = useState<'usuarios' | 'auditoria'>('usuarios')
  const [emailInput, setEmailInput] = useState('admin@uct.cl')
  const [passwordInput, setPasswordInput] = useState('PasswordSuperSegura123!')
  const [loginError, setLoginError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')


  const [isModalOpen, setIsModalOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole] = useState('Guardia_Seguridad')
  const [newDatasets, setNewDatasets] = useState<string[]>(['biblioteca', 'estacionamiento'])
  const [modalError, setModalError] = useState<string | null>(null)


  const [providerInput, setProviderInput] = useState('gemini')
  const [modelInput, setModelInput] = useState('gemini-2.5-flash')
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)
  const [llmSuccessMsg, setLlmSuccessMsg] = useState<string | null>(null)
  const [llmErrorMsg, setLlmErrorMsg] = useState<string | null>(null)


  const {
    data: configData,
    isLoading: isConfigLoading,
    isFetching: isConfigFetching,
    refetch: refetchConfig,
  } = useQuery<GlobalConfig>({
    queryKey: ['admin-global-config'],
    queryFn: async () => {
      const res = await api.get('/config')
      return res.data
    },
    enabled: isSuperAdmin,
  })

  const {
    data: usersList = [],
    isLoading: isUsersLoading,
    isFetching: isUsersFetching,
    refetch: refetchUsers,
  } = useQuery<UserItem[]>({
    queryKey: ['admin-users-list'],
    queryFn: async () => {
      const res = await api.get('/auth/users')
      return res.data
    },
    enabled: isSuperAdmin,
  })

  const toggleMutation = useMutation({
    mutationFn: async () => {
      const res = await api.put('/config/toggle-ia')
      return res.data
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(['admin-global-config'], updated)
      queryClient.invalidateQueries({ queryKey: ['admin-global-config'] })
    },
  })

  useEffect(() => {
    if (configData) {
      if (configData.active_provider) setProviderInput(configData.active_provider)
      if (configData.default_model) setModelInput(configData.default_model)
    }
  }, [configData])

  const updateLlmMutation = useMutation({
    mutationFn: async (payload: { provider: string; default_model: string; api_key: string }) => {
      const res = await api.put('/config/llm-provider', payload)
      return res.data
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(['admin-global-config'], updated)
      queryClient.invalidateQueries({ queryKey: ['admin-global-config'] })
      setApiKeyInput('')
      setLlmErrorMsg(null)
      setLlmSuccessMsg('Configuración de motor LLM y API Key cifrada actualizada correctamente.')
      setTimeout(() => setLlmSuccessMsg(null), 4000)
    },
    onError: (err: any) => {
      setLlmSuccessMsg(null)
      setLlmErrorMsg(err.response?.data?.detail || 'Error al actualizar el proveedor de LLM')
    },
  })


  const createUserMutation = useMutation({
    mutationFn: async (payload: {
      nombre_completo: string
      email: string
      password: string
      roles: string[]
      allowed_datasets: string[]
    }) => {
      const res = await api.post('/auth/register', payload)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users-list'] })
      setIsModalOpen(false)
      setNewName('')
      setNewEmail('')
      setNewPassword('')
      setNewRole('Guardia_Seguridad')
      setNewDatasets(['biblioteca', 'estacionamiento'])
      setModalError(null)
    },
    onError: (err: any) => {
      setModalError(err.response?.data?.detail || 'Error al registrar el usuario')
    },
  })

  const toggleUserStatusMutation = useMutation({
    mutationFn: async ({ userId, isActive }: { userId: number; isActive: boolean }) => {
      const res = await api.patch(`/users/${userId}/status`, { is_active: isActive })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users-list'] })
    },
  })

  const handleDatasetCheckbox = (datasetKey: string) => {
    setNewDatasets((prev) =>
      prev.includes(datasetKey)
        ? prev.filter((d) => d !== datasetKey)
        : [...prev, datasetKey]
    )
  }

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoginError(null)
    setIsSubmitting(true)
    const ok = await loginWithCredentials(emailInput, passwordInput)
    setIsSubmitting(false)
    if (!ok) {
      setLoginError('Credenciales incorrectas o permisos denegados.')
    }
  }

  if (!isAuthenticated || !isSuperAdmin) {
    return (
      <div className="max-w-md mx-auto my-16 px-4">
        <div className="bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
          <div className="bg-gradient-to-r from-uct-blue-primary to-uct-blue-secondary p-6 text-white text-center">
            <div className="w-14 h-14 bg-white/10 rounded-2xl mx-auto flex items-center justify-center mb-3 border border-white/20">
              <Lock size={28} className="text-uct-gold" />
            </div>
            <h2 className="text-lg font-bold">Acceso a Panel de Administración</h2>
            <p className="text-xs text-white/70 mt-1">
              Restringido exclusivamente para el rol <span className="text-uct-gold font-semibold">SuperAdmin</span>
            </p>
          </div>

          <form onSubmit={handleLoginSubmit} className="p-6 space-y-4">
            {loginError && (
              <div className="flex items-center gap-2 p-3 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg">
                <AlertTriangle size={16} className="shrink-0" />
                <span>{loginError}</span>
              </div>
            )}

            {isAuthenticated && !isSuperAdmin && (
              <div className="flex items-center justify-between p-3 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg">
                <span>Sesión activa como: <strong>{userRole}</strong></span>
                <button
                  type="button"
                  onClick={logout}
                  className="text-xs font-semibold text-uct-blue-primary underline hover:text-uct-blue-secondary"
                >
                  Cerrar Sesión
                </button>
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Correo Electrónico
              </label>
              <div className="relative">
                <Mail size={16} className="absolute left-3 top-2.5 text-slate-400" />
                <input
                  type="email"
                  required
                  value={emailInput}
                  onChange={(e) => setEmailInput(e.target.value)}
                  placeholder="admin@uct.cl"
                  className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/30 focus:border-uct-blue-primary"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Contraseña
              </label>
              <div className="relative">
                <Lock size={16} className="absolute left-3 top-2.5 text-slate-400" />
                <input
                  type="password"
                  required
                  value={passwordInput}
                  onChange={(e) => setPasswordInput(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/30 focus:border-uct-blue-primary"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 bg-uct-blue-primary hover:bg-uct-blue-secondary text-white font-semibold text-sm rounded-lg transition-colors shadow-sm disabled:opacity-50 cursor-pointer"
            >
              {isSubmitting ? 'Verificando...' : 'Iniciar Sesión como SuperAdmin'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  const isAiActive = configData?.ia_asistente_activo ?? true
  const filteredUsers = usersList.filter(
    (u) =>
      u.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.nombre_completo.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const getRoleBadge = (roleName: string) => {
    switch (roleName) {
      case 'SuperAdmin':
        return (
          <span
            key={roleName}
            className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-800 border border-purple-200"
          >
            <ShieldCheck size={12} />
            SuperAdmin
          </span>
        )
      case 'Directivo':
        return (
          <span
            key={roleName}
            className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-200"
          >
            Directivo
          </span>
        )
      case 'Guardia_Seguridad':
        return (
          <span
            key={roleName}
            className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200"
          >
            Guardia
          </span>
        )
      default:
        return (
          <span
            key={roleName}
            className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-800 border border-slate-200"
          >
            {roleName}
          </span>
        )
    }
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-uct-gold uppercase tracking-wider">
            <ShieldCheck size={15} />
            <span>Panel de Control Administrativo</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mt-1">
            Gestión Global del Sistema & RBAC
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Universidad Católica de Temuco — Administración de accesos, roles y servicios analíticos
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-white px-3.5 py-1.5 rounded-xl border border-slate-200 shadow-xs">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs font-medium text-slate-700">Rol:</span>
            <span className="text-xs font-bold text-purple-700 bg-purple-50 px-2 py-0.5 rounded-md border border-purple-200">
              SuperAdmin
            </span>
          </div>
          <button
            onClick={logout}
            className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:text-rose-600 bg-white hover:bg-rose-50 border border-slate-200 hover:border-rose-200 rounded-xl transition-colors cursor-pointer"
          >
            Cerrar Sesión
          </button>
        </div>
      </div>

      <div className="flex items-center gap-4 border-b border-slate-200">

        <button
          onClick={() => setAdminTab('usuarios')}
          className={`flex items-center gap-2 pb-3 px-1 text-sm font-bold border-b-2 transition-colors cursor-pointer ${
            adminTab === 'usuarios'
              ? 'border-uct-blue-primary text-uct-blue-primary'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Users size={16} />
          <span>Gestión de Usuarios & Control IA</span>
        </button>
        <button
          onClick={() => setAdminTab('auditoria')}
          className={`flex items-center gap-2 pb-3 px-1 text-sm font-bold border-b-2 transition-colors cursor-pointer ${
            adminTab === 'auditoria'
              ? 'border-uct-blue-primary text-uct-blue-primary'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Activity size={16} />
          <span>Auditoría IA</span>
        </button>
      </div>

      {adminTab === 'auditoria' ? (
        <ChatAuditSection />
      ) : (
        <>
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6">

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
                <h2 className="text-base font-bold text-slate-900">Control de IA</h2>
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
                Interruptor maestro para habilitar o suspender temporalmente el Asistente Analítico Gemini en toda la plataforma. Cuando se desactiva, cualquier consulta al endpoint devolverá un código de estado 403 Forbidden.
              </p>
              {configData?.updated_at && (
                <div className="flex items-center gap-1 text-[11px] text-slate-400 mt-2">
                  <Clock size={12} />
                  <span>Última modificación: {new Date(configData.updated_at).toLocaleString()}</span>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4 self-end sm:self-center">
            <button
              onClick={() => toggleMutation.mutate()}
              disabled={isConfigLoading || toggleMutation.isPending}
              aria-label="Alternar estado de IA"
              className={`relative inline-flex h-8 w-16 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/40 focus:ring-offset-2 disabled:opacity-50 ${
                isAiActive ? 'bg-emerald-500' : 'bg-slate-300'
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-7 w-7 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out flex items-center justify-center ${
                  isAiActive ? 'translate-x-8 text-emerald-600' : 'translate-x-0 text-slate-400'
                }`}
              >
                <Power size={14} />
              </span>
            </button>
            <button
              onClick={() => refetchConfig()}
              disabled={isConfigFetching}
              title="Actualizar estado"
              className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition-colors"
            >
              <RefreshCw size={16} className={isConfigFetching ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        <div className="mt-6 pt-6 border-t border-slate-200">
          <div className="flex items-center gap-2 mb-2">
            <Cpu size={18} className="text-uct-blue-primary" />
            <h3 className="text-sm font-bold text-slate-900">Motor de Inteligencia Artificial (Patrón Adapter)</h3>
          </div>
          <p className="text-xs text-slate-500 mb-4">
            Desacoplamiento del proveedor de IA y gestión de API Key en caliente con cifrado simétrico Fernet.
          </p>

          {llmSuccessMsg && (
            <div className="mb-4 flex items-center gap-2 p-3 text-xs text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg">
              <CheckCircle2 size={16} className="shrink-0" />
              <span>{llmSuccessMsg}</span>
            </div>
          )}

          {llmErrorMsg && (
            <div className="mb-4 flex items-center gap-2 p-3 text-xs text-rose-800 bg-rose-50 border border-rose-200 rounded-lg">
              <AlertTriangle size={16} className="shrink-0" />
              <span>{llmErrorMsg}</span>
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (!apiKeyInput.trim()) {
                setLlmErrorMsg('Ingrese una API Key válida')
                return
              }
              updateLlmMutation.mutate({
                provider: providerInput,
                default_model: modelInput,
                api_key: apiKeyInput,
              })
            }}
            className="grid grid-cols-1 md:grid-cols-3 gap-4"
          >
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Proveedor de IA
              </label>
              <select
                value={providerInput}
                onChange={(e) => {
                  setProviderInput(e.target.value)
                  if (e.target.value === 'gemini') {
                    setModelInput('gemini-2.5-flash')
                  } else if (e.target.value === 'openai') {
                    setModelInput('gpt-4o-mini')
                  }
                }}
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/30 focus:border-uct-blue-primary text-slate-800"
              >
                <option value="gemini">Google Gemini (Oficial)</option>
                <option value="openai">OpenAI (Adapter)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Modelo Predeterminado
              </label>
              <input
                type="text"
                required
                value={modelInput}
                onChange={(e) => setModelInput(e.target.value)}
                placeholder="ej. gemini-2.5-flash"
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/30 focus:border-uct-blue-primary font-mono text-slate-800"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-semibold text-slate-700">
                  API Key Cifrada (Fernet)
                </label>
                {configData?.has_api_key && (
                  <span className="text-[10px] text-emerald-700 font-medium">
                    Activa: {configData.masked_api_key}
                  </span>
                )}
              </div>
              <div className="relative">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  required={!configData?.has_api_key}
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  placeholder={configData?.has_api_key ? '•••• Ingrese nueva clave para rotar ••••' : 'AIzaSy...'}
                  className="w-full pl-3 pr-10 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/30 focus:border-uct-blue-primary font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  {showApiKey ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <div className="md:col-span-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
              <p className="text-[11px] text-slate-400 flex items-center gap-1">
                <Lock size={12} className="text-uct-gold shrink-0" />
                <span>Almacenada con cifrado simétrico AES-128/Fernet en PostgreSQL. Inyección dinámica en caliente.</span>
              </p>
              <button
                type="submit"
                disabled={updateLlmMutation.isPending || !apiKeyInput.trim()}
                className="flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-uct-blue-primary hover:bg-uct-blue-secondary rounded-lg transition-colors shadow-xs disabled:opacity-50 cursor-pointer"
              >
                <Save size={13} />
                <span>{updateLlmMutation.isPending ? 'Guardando en caliente...' : 'Actualizar Proveedor & Key'}</span>
              </button>
            </div>
          </form>
        </div>
      </div>


      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="p-6 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-uct-blue-primary/10 border border-uct-blue-primary/20 flex items-center justify-center text-uct-blue-primary">
              <Users size={20} />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">Usuarios y Roles Registrados</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Listado institucional con control de acceso por datasets (Least Privilege)
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="text"
              placeholder="Buscar por nombre o correo..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="px-3.5 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/20 focus:border-uct-blue-primary w-56"
            />
            <button
              onClick={() => {
                setModalError(null)
                setIsModalOpen(true)
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-uct-blue-primary hover:bg-uct-blue-secondary rounded-lg transition-colors shadow-xs cursor-pointer"
            >
              <UserPlus size={14} />
              <span>Nuevo Usuario</span>
            </button>
            <button
              onClick={() => refetchUsers()}
              disabled={isUsersFetching}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors cursor-pointer"
            >
              <RefreshCw size={13} className={isUsersFetching ? 'animate-spin' : ''} />
              <span>Actualizar</span>
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 text-[11px] font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                <th className="py-3 px-6">ID</th>
                <th className="py-3 px-6">Usuario</th>
                <th className="py-3 px-6">Correo Institucional</th>
                <th className="py-3 px-6">Roles Asignados</th>
                <th className="py-3 px-6">Datasets Permitidos</th>
                <th className="py-3 px-6">Estado / Acceso</th>
                <th className="py-3 px-6">Fecha Registro</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-xs">
              {isUsersLoading ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-400">
                    Cargando usuarios del sistema...
                  </td>
                </tr>
              ) : filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-400">
                    No se encontraron usuarios registrados.
                  </td>
                </tr>
              ) : (
                filteredUsers.map((user) => (
                  <tr key={user.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3.5 px-6 font-mono font-medium text-slate-500">
                      #{user.id}
                    </td>
                    <td className="py-3.5 px-6 font-semibold text-slate-900">
                      {user.nombre_completo}
                    </td>
                    <td className="py-3.5 px-6 text-slate-600 font-mono text-[11px]">
                      {user.email}
                    </td>
                    <td className="py-3.5 px-6">
                      <div className="flex flex-wrap gap-1.5">
                        {user.roles && user.roles.length > 0
                          ? user.roles.map((r) => getRoleBadge(r.nombre))
                          : <span className="text-slate-400 italic">Sin roles</span>}
                      </div>
                    </td>
                    <td className="py-3.5 px-6">
                      <div className="flex flex-wrap gap-1.5">
                        {user.allowed_datasets?.includes('biblioteca') && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                            <BookOpen size={10} />
                            Biblioteca
                          </span>
                        )}
                        {user.allowed_datasets?.includes('estacionamiento') && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <Car size={10} />
                            Estacionamiento
                          </span>
                        )}
                        {(!user.allowed_datasets || user.allowed_datasets.length === 0) && (
                          <span className="text-slate-400 italic text-[11px]">Ninguno</span>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-6">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          role="switch"
                          aria-checked={user.is_active}
                          disabled={toggleUserStatusMutation.isPending || user.email === 'admin@uct.cl'}
                          onClick={() =>
                            toggleUserStatusMutation.mutate({
                              userId: user.id,
                              isActive: !user.is_active,
                            })
                          }
                          title={
                            user.email === 'admin@uct.cl'
                              ? 'No se puede desactivar al SuperAdmin principal'
                              : user.is_active
                              ? 'Desactivar usuario'
                              : 'Activar usuario'
                          }
                          className={`relative inline-flex h-5 w-10 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/40 disabled:opacity-40 disabled:cursor-not-allowed ${
                            user.is_active ? 'bg-emerald-500' : 'bg-slate-300'
                          }`}
                        >
                          <span
                            className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                              user.is_active ? 'translate-x-5' : 'translate-x-0'
                            }`}
                          />
                        </button>
                        <span
                          className={`text-[11px] font-semibold ${
                            user.is_active ? 'text-emerald-700' : 'text-slate-400'
                          }`}
                        >
                          {user.is_active ? 'Activo' : 'Inactivo'}
                        </span>
                      </div>
                    </td>
                    <td className="py-3.5 px-6 text-slate-500 text-[11px]">
                      {new Date(user.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
        </>
      )}

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="bg-gradient-to-r from-uct-blue-primary to-uct-blue-secondary p-5 text-white flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center border border-white/20">
                  <UserPlus size={18} className="text-uct-gold" />
                </div>
                <div>
                  <h3 className="text-sm font-bold">Registrar Nuevo Usuario</h3>
                  <p className="text-[11px] text-white/70">Gestión de accesos y datasets (Least Privilege)</p>
                </div>
              </div>
              <button
                onClick={() => setIsModalOpen(false)}
                className="text-white/70 hover:text-white p-1 rounded-lg hover:bg-white/10 transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault()
                setModalError(null)
                if (newDatasets.length === 0) {
                  setModalError('Debe seleccionar al menos un módulo de dataset permitido.')
                  return
                }
                createUserMutation.mutate({
                  nombre_completo: newName,
                  email: newEmail,
                  password: newPassword,
                  roles: [newRole],
                  allowed_datasets: newDatasets,
                })
              }}
              className="p-5 space-y-4"
            >
              {modalError && (
                <div className="flex items-center gap-2 p-2.5 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg">
                  <AlertTriangle size={15} className="shrink-0" />
                  <span>{modalError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Nombre Completo
                </label>
                <input
                  type="text"
                  required
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Ej. Juan Pérez"
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/30 focus:border-uct-blue-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Correo Institucional
                </label>
                <input
                  type="email"
                  required
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="usuario@uct.cl"
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/30 focus:border-uct-blue-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Contraseña
                </label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Mínimo 6 caracteres"
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/30 focus:border-uct-blue-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Rol de Acceso (RBAC)
                </label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-uct-blue-primary/30 focus:border-uct-blue-primary"
                >
                  <option value="Guardia_Seguridad">Guardia de Seguridad</option>
                  <option value="Directivo">Directivo</option>
                  <option value="SuperAdmin">SuperAdmin</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Módulos / Datasets Permitidos
                </label>
                <div className="space-y-2 border border-slate-200 rounded-lg p-3 bg-slate-50/50">
                  <label className="flex items-center gap-2.5 text-xs text-slate-700 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={newDatasets.includes('biblioteca')}
                      onChange={() => handleDatasetCheckbox('biblioteca')}
                      className="rounded border-slate-300 text-uct-blue-primary focus:ring-uct-blue-primary/40 h-4 w-4"
                    />
                    <span className="flex items-center gap-1.5 font-medium">
                      <BookOpen size={14} className="text-blue-600" />
                      Biblioteca CSF
                    </span>
                  </label>
                  <label className="flex items-center gap-2.5 text-xs text-slate-700 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={newDatasets.includes('estacionamiento')}
                      onChange={() => handleDatasetCheckbox('estacionamiento')}
                      className="rounded border-slate-300 text-uct-blue-primary focus:ring-uct-blue-primary/40 h-4 w-4"
                    />
                    <span className="flex items-center gap-1.5 font-medium">
                      <Car size={14} className="text-emerald-600" />
                      Estacionamiento CSF
                    </span>
                  </label>
                </div>
                <p className="text-[10px] text-slate-400 mt-1">
                  Principio de menor privilegio: el usuario solo visualizará las pestañas y consultará datos autorizados.
                </p>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-3.5 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors cursor-pointer"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={createUserMutation.isPending}
                  className="px-4 py-2 text-xs font-semibold text-white bg-uct-blue-primary hover:bg-uct-blue-secondary rounded-lg transition-colors shadow-xs disabled:opacity-50 cursor-pointer"
                >
                  {createUserMutation.isPending ? 'Guardando...' : 'Crear Usuario'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
