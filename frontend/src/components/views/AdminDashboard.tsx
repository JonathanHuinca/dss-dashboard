import React, { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  ShieldCheck,
  Users,
  Power,
  Clock,
  Download,
  Building,
  UploadCloud,
  Database,
  Trash2,
  Activity,
  Calendar,
  CalendarCheck,
  Lock,
  Mail,
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { ChatAuditSection } from './ChatAuditSection'
import { DownloadAuditSection } from './DownloadAuditSection'
import { HorariosSection } from './HorariosSection'
import { AforoSection } from './AforoSection'
import { IngestionAuditSection } from './IngestionAuditSection'
import { IngestionWizardModal } from '../ingestion/IngestionWizardModal'
import { PurgaDatosSection } from './PurgaDatosSection'
import { UsuariosSection } from './admin/UsuariosSection'
import { TareasProgramadasSection } from './admin/TareasProgramadasSection'
import { CalendarioSection } from './admin/CalendarioSection'

export const AdminDashboard: React.FC = () => {
  const {
    isAuthenticated,
    isSuperAdmin,
    isDirectivo,
    canAccessAdmin,
    loginWithCredentials,
    logout,
  } = useAuth()
  const isSuperAdminOrDirectivo = isSuperAdmin || isDirectivo
  const queryClient = useQueryClient()

  const [adminTab, setAdminTab] = useState<
    'usuarios' | 'tareas' | 'calendario' | 'aforo' | 'horarios' | 'descargas' | 'auditoria' | 'ingesta' | 'purga'
  >(isSuperAdminOrDirectivo ? 'usuarios' : 'aforo')

  const [emailInput, setEmailInput] = useState('')
  const [passwordInput, setPasswordInput] = useState('')
  const [loginError, setLoginError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isIngestionModalOpen, setIsIngestionModalOpen] = useState(false)

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    setLoginError(null)
    try {
      await loginWithCredentials(emailInput, passwordInput)
    } catch (err: any) {
      setLoginError(err?.response?.data?.detail || 'Credenciales administrativas inválidas.')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Vista de Login Administrativo si no cuenta con sesión o privilegios
  if (!isAuthenticated || !canAccessAdmin) {
    return (
      <div className="min-h-[75vh] flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-white rounded-3xl border border-slate-200 shadow-xl p-8 space-y-6">
          <div className="text-center space-y-2">
            <div className="w-14 h-14 rounded-2xl bg-uct-blue-primary/10 flex items-center justify-center text-uct-blue-primary mx-auto shadow-2xs">
              <ShieldCheck size={28} />
            </div>
            <h1 className="text-xl font-bold text-slate-900">Panel de Administración DSS UCT</h1>
            <p className="text-xs text-slate-500">
              Acceso restringido para Administradores de Sistema y Directores de Recinto.
            </p>
          </div>

          <form onSubmit={handleLoginSubmit} className="space-y-4">
            {loginError && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 text-xs font-semibold rounded-xl">
                {loginError}
              </div>
            )}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Correo Institucional</label>
              <div className="relative">
                <Mail size={16} className="absolute left-3.5 top-3 text-slate-400" />
                <input
                  type="email"
                  required
                  value={emailInput}
                  onChange={(e) => setEmailInput(e.target.value)}
                  className="w-full pl-10 pr-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Contraseña</label>
              <div className="relative">
                <Lock size={16} className="absolute left-3.5 top-3 text-slate-400" />
                <input
                  type="password"
                  required
                  value={passwordInput}
                  onChange={(e) => setPasswordInput(e.target.value)}
                  className="w-full pl-10 pr-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 focus:bg-white focus:outline-none"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 bg-uct-blue-primary hover:bg-uct-blue-hover text-white text-xs font-bold rounded-xl shadow-xs transition cursor-pointer disabled:opacity-50"
            >
              {isSubmitting ? 'Autenticando...' : 'Iniciar Sesión'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-6">
      {/* Barra Superior de Control Administrativo */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-uct-gold uppercase tracking-wider">
            <ShieldCheck size={15} />
            <span>Panel de Administración</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mt-1">Gestión Global del Sistema & RBAC</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Universidad Católica de Temuco — Administración de aforos, tareas automáticas y credenciales.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setIsIngestionModalOpen(true)}
            className="flex items-center gap-2 bg-gradient-to-r from-uct-blue-primary to-blue-700 hover:from-blue-700 hover:to-uct-blue-primary text-white font-bold text-xs px-3.5 py-2 rounded-xl hover:shadow-md transition cursor-pointer shadow-xs"
            title="Carga manual de archivos como canal secundario de contingencia"
          >
            <UploadCloud size={15} />
            <span>Carga Manual de Respaldo</span>
          </button>

          <div className="flex items-center gap-2 bg-white px-3.5 py-1.5 rounded-xl border border-slate-200 shadow-xs">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs font-medium text-slate-700">Rol:</span>
            <span
              className={`text-xs font-bold px-2 py-0.5 rounded-md border ${
                isSuperAdmin
                  ? 'text-purple-700 bg-purple-50 border-purple-200'
                  : 'text-blue-700 bg-blue-50 border-blue-200'
              }`}
            >
              {isSuperAdmin ? 'SuperAdmin' : 'Director de Recinto'}
            </span>
          </div>

          <button
            type="button"
            onClick={logout}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 border border-rose-200 rounded-xl transition cursor-pointer"
          >
            <Power size={14} />
            <span>Cerrar Sesión</span>
          </button>
        </div>
      </div>

      {/* Navegación por Pestañas del Panel */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200">
        {isSuperAdminOrDirectivo && (
          <button
            type="button"
            onClick={() => setAdminTab('usuarios')}
            className={`flex items-center gap-2 pb-3 px-3 text-xs font-bold border-b-2 transition cursor-pointer ${
              adminTab === 'usuarios'
                ? 'border-uct-blue-primary text-uct-blue-primary'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Users size={16} />
            <span>Usuarios & IA</span>
          </button>
        )}

        {isSuperAdmin && (
          <button
            type="button"
            onClick={() => setAdminTab('tareas')}
            className={`flex items-center gap-2 pb-3 px-3 text-xs font-bold border-b-2 transition cursor-pointer ${
              adminTab === 'tareas'
                ? 'border-uct-blue-primary text-uct-blue-primary'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Clock size={16} />
            <span>Tareas Programadas</span>
          </button>
        )}

        <button
          type="button"
          onClick={() => setAdminTab('calendario')}
          className={`flex items-center gap-2 pb-3 px-3 text-xs font-bold border-b-2 transition cursor-pointer ${
            adminTab === 'calendario'
              ? 'border-uct-blue-primary text-uct-blue-primary'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <CalendarCheck size={16} />
          <span>Calendario Académico</span>
        </button>

        <button
          type="button"
          onClick={() => setAdminTab('aforo')}
          className={`flex items-center gap-2 pb-3 px-3 text-xs font-bold border-b-2 transition cursor-pointer ${
            adminTab === 'aforo'
              ? 'border-uct-blue-primary text-uct-blue-primary'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Building size={16} />
          <span>Capacidad y Aforo</span>
        </button>

        <button
          type="button"
          onClick={() => setAdminTab('horarios')}
          className={`flex items-center gap-2 pb-3 px-3 text-xs font-bold border-b-2 transition cursor-pointer ${
            adminTab === 'horarios'
              ? 'border-uct-blue-primary text-uct-blue-primary'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Calendar size={16} />
          <span>Horarios de Atención</span>
        </button>

        {isSuperAdmin && (
          <button
            type="button"
            onClick={() => setAdminTab('descargas')}
            className={`flex items-center gap-2 pb-3 px-3 text-xs font-bold border-b-2 transition cursor-pointer ${
              adminTab === 'descargas'
                ? 'border-uct-blue-primary text-uct-blue-primary'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Download size={16} />
            <span>Auditoría de Descargas</span>
          </button>
        )}

        {isSuperAdmin && (
          <button
            type="button"
            onClick={() => setAdminTab('auditoria')}
            className={`flex items-center gap-2 pb-3 px-3 text-xs font-bold border-b-2 transition cursor-pointer ${
              adminTab === 'auditoria'
                ? 'border-uct-blue-primary text-uct-blue-primary'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Activity size={16} />
            <span>Auditoría IA</span>
          </button>
        )}

        {isSuperAdmin && (
          <button
            type="button"
            onClick={() => setAdminTab('ingesta')}
            className={`flex items-center gap-2 pb-3 px-3 text-xs font-bold border-b-2 transition cursor-pointer ${
              adminTab === 'ingesta'
                ? 'border-uct-blue-primary text-uct-blue-primary'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Database size={16} />
            <span>Historial de Ingesta</span>
          </button>
        )}

        {isSuperAdmin && (
          <button
            type="button"
            onClick={() => setAdminTab('purga')}
            className={`flex items-center gap-2 pb-3 px-3 text-xs font-bold border-b-2 transition cursor-pointer ${
              adminTab === 'purga'
                ? 'border-rose-600 text-rose-600'
                : 'border-transparent text-slate-500 hover:text-rose-600'
            }`}
          >
            <Trash2 size={16} />
            <span>Purga y Reseteo</span>
          </button>
        )}
      </div>

      {/* Contenido de la Pestaña Activa */}
      {adminTab === 'usuarios' && isSuperAdminOrDirectivo ? (
        <UsuariosSection />
      ) : adminTab === 'tareas' && isSuperAdmin ? (
        <TareasProgramadasSection />
      ) : adminTab === 'calendario' ? (
        <CalendarioSection />
      ) : adminTab === 'aforo' ? (
        <AforoSection />
      ) : adminTab === 'horarios' ? (
        <HorariosSection />
      ) : adminTab === 'descargas' && isSuperAdmin ? (
        <DownloadAuditSection />
      ) : adminTab === 'auditoria' && isSuperAdmin ? (
        <ChatAuditSection />
      ) : adminTab === 'ingesta' && isSuperAdmin ? (
        <div className="space-y-4">
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-amber-500/20 flex items-center justify-center text-amber-700">
                <Database size={18} />
              </div>
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-amber-900">
                  Fuente Activa de Producción: API Smart Campus UCT
                </h4>
                <p className="text-xs text-amber-800">
                  La ingesta institucional de torniquetes y estacionamientos se sincroniza automáticamente cada 1 hora. La carga manual por archivo CSV/Excel está clasificada como canal secundario de contingencia y carga histórica.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsIngestionModalOpen(true)}
              className="flex items-center gap-2 bg-gradient-to-r from-uct-blue-primary to-blue-700 hover:from-blue-700 hover:to-uct-blue-primary text-white font-bold text-xs px-3.5 py-2 rounded-xl hover:shadow-md transition cursor-pointer shadow-xs"
            >
              <UploadCloud size={15} />
              <span>Carga Manual de Respaldo (.csv/.xlsx)</span>
            </button>
          </div>
          <IngestionAuditSection />
        </div>
      ) : adminTab === 'purga' && isSuperAdmin ? (
        <PurgaDatosSection />
      ) : null}

      {/* Modal Wizard de Ingesta Asistida (Canal Secundario de Respaldo) */}
      <IngestionWizardModal
        isOpen={isIngestionModalOpen}
        onClose={() => setIsIngestionModalOpen(false)}
        onIngestionCompleted={() => {
          queryClient.invalidateQueries()
        }}
      />
    </div>
  )
}
