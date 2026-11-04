import React, { useState, FormEvent } from 'react'
import {
  Lock,
  Mail,
  Eye,
  EyeOff,
  AlertCircle,
  ArrowRight,
  ShieldCheck,
  KeyRound,
  X,
  CheckCircle2,
  Copy,
  ExternalLink,
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { api, forgotPassword, ForgotPasswordResponse } from '../../api/client'

export function LoginView() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isBlocked, setIsBlocked] = useState(false)

  // Estados del modal de recuperación
  const [isForgotModalOpen, setIsForgotModalOpen] = useState(false)
  const [forgotEmail, setForgotEmail] = useState('')
  const [forgotLoading, setForgotLoading] = useState(false)
  const [forgotResult, setForgotResult] = useState<ForgotPasswordResponse | null>(null)
  const [copiedLink, setCopiedLink] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsBlocked(false)
    setLoading(true)

    try {
      const res = await api.post('/auth/login', { email, password })
      if (res.data?.access_token) {
        login(res.data.access_token)
      } else {
        setError('Respuesta de autenticación inválida.')
      }
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
      const status = axiosErr.response?.status
      const message =
        axiosErr.response?.data?.detail || 'Credenciales inválidas. Por favor intente nuevamente.'
      setError(message)
      if (status === 423) {
        setIsBlocked(true)
      }
    } finally {
      setLoading(false)
    }
  }

  const handleForgotSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!forgotEmail.trim()) return

    setForgotLoading(true)
    try {
      const res = await forgotPassword(forgotEmail.trim())
      setForgotResult(res)
    } catch {
      // Respuesta neutral garantizada ante cualquier falla de red o servidor
      setForgotResult({
        mensaje:
          'Si el correo institucional se encuentra registrado en la plataforma DSS, recibirá un enlace con las instrucciones para restablecer su contraseña (validez: 15 minutos).',
      })
    } finally {
      setForgotLoading(false)
    }
  }

  const handleCopyLink = (enlace: string) => {
    const fullUrl = `${window.location.origin}${enlace}`
    navigator.clipboard.writeText(fullUrl)
    setCopiedLink(true)
    setTimeout(() => setCopiedLink(false), 3000)
  }

  const demoEnv = (import.meta as any).env ?? {}
  const demoAdminPass: string = demoEnv.VITE_DEMO_ADMIN_PASSWORD ?? ''
  const demoUserPass: string = demoEnv.VITE_DEMO_USER_PASSWORD ?? ''

  const setPresetUser = (roleEmail: string, rolePass: string) => {
    setEmail(roleEmail)
    setPassword(rolePass)
    setError(null)
    setIsBlocked(false)
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-gradient-to-br from-[#002B49] via-[#003865] to-[#001829] px-4 py-8 relative overflow-hidden">
      <div className="absolute inset-0 opacity-5 pointer-events-none bg-[radial-gradient(#C59B27_1px,transparent_1px)] [background-size:24px_24px]" />

      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-white/20 overflow-hidden relative z-10">
        <div className="bg-gradient-to-r from-[#002B49] to-[#003865] p-6 text-center border-b border-[#C59B27]/30 relative">
          <div className="bg-white/95 rounded-xl p-3 inline-block shadow-md mb-3 border border-[#C59B27]/20">
            <img
              src="/uct_logo.png"
              alt="Universidad Católica de Temuco"
              className="h-12 w-auto object-contain mx-auto"
            />
          </div>
          <div className="flex items-center justify-center gap-1.5 text-[#C59B27] text-xs font-semibold uppercase tracking-wider">
            <ShieldCheck size={14} />
            <span>Sistema DSS · Campus San Francisco</span>
          </div>
          <h1 className="text-white text-base font-bold mt-1">Portal de Autenticación Institucional</h1>
          <p className="text-white/70 text-xs mt-0.5">Control de Aforos, Movilidad y Análisis Predictivo</p>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div
              className={`flex items-start gap-2.5 p-3 text-xs border rounded-lg animate-in fade-in ${
                isBlocked
                  ? 'bg-amber-50 border-amber-300 text-amber-900'
                  : 'bg-rose-50 border-rose-200 text-rose-800'
              }`}
            >
              <AlertCircle
                size={16}
                className={`shrink-0 mt-0.5 ${isBlocked ? 'text-amber-600' : 'text-rose-600'}`}
              />
              <div className="space-y-1">
                <span>{error}</span>
                {isBlocked && (
                  <button
                    type="button"
                    onClick={() => {
                      setForgotEmail(email)
                      setIsForgotModalOpen(true)
                    }}
                    className="block text-xs font-bold text-amber-800 underline hover:text-amber-950 mt-1 cursor-pointer"
                  >
                    Restablecer contraseña ahora
                  </button>
                )}
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              Correo Electrónico Institucional
            </label>
            <div className="relative">
              <Mail size={16} className="absolute left-3 top-2.5 text-slate-400" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="usuario@uct.cl"
                className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#002B49]/30 focus:border-[#002B49] transition-all"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-xs font-semibold text-slate-700">Contraseña</label>
              <button
                type="button"
                onClick={() => {
                  setForgotEmail(email)
                  setForgotResult(null)
                  setIsForgotModalOpen(true)
                }}
                className="text-[11px] font-semibold text-[#002B49] hover:text-[#004B80] hover:underline cursor-pointer"
              >
                ¿Olvidó su contraseña?
              </button>
            </div>
            <div className="relative">
              <Lock size={16} className="absolute left-3 top-2.5 text-slate-400" />
              <input
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full pl-9 pr-10 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#002B49]/30 focus:border-[#002B49] transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 bg-[#002B49] hover:bg-[#003865] text-white text-sm font-semibold rounded-lg shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 border border-[#C59B27]/40"
          >
            {loading ? (
              <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <>
                <span>Ingresar al Dashboard</span>
                <ArrowRight size={16} className="text-[#C59B27]" />
              </>
            )}
          </button>

          {(import.meta as any).env?.DEV && (
            <div className="pt-3 border-t border-slate-100">
              <p className="text-[11px] text-slate-500 font-medium mb-1.5 text-center">
                Accesos rápidos para demostración (Sólo DEV):
              </p>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => setPresetUser('admin@uct.cl', demoAdminPass)}
                  className="p-2 rounded-lg border border-purple-200 bg-purple-50 hover:bg-purple-100 text-purple-900 transition-colors text-left cursor-pointer"
                >
                  <span className="font-bold block text-[11px]">Admin Sistema</span>
                  <span className="text-[10px] text-purple-700 block truncate">admin@uct.cl</span>
                </button>
                <button
                  type="button"
                  onClick={() => setPresetUser('directivo@uct.cl', demoUserPass)}
                  className="p-2 rounded-lg border border-blue-200 bg-blue-50 hover:bg-blue-100 text-blue-900 transition-colors text-left cursor-pointer"
                >
                  <span className="font-bold block text-[11px]">Director Recinto</span>
                  <span className="text-[10px] text-blue-700 block truncate">directivo@uct.cl</span>
                </button>
                <button
                  type="button"
                  onClick={() => setPresetUser('analista@uct.cl', demoUserPass)}
                  className="p-2 rounded-lg border border-indigo-200 bg-indigo-50 hover:bg-indigo-100 text-indigo-900 transition-colors text-left cursor-pointer"
                >
                  <span className="font-bold block text-[11px]">Analista Consulta</span>
                  <span className="text-[10px] text-indigo-700 block truncate">analista@uct.cl</span>
                </button>
                <button
                  type="button"
                  onClick={() => setPresetUser('guardia@uct.cl', demoUserPass)}
                  className="p-2 rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-900 transition-colors text-left cursor-pointer"
                >
                  <span className="font-bold block text-[11px]">Guardia Seguridad</span>
                  <span className="text-[10px] text-emerald-700 block truncate">guardia@uct.cl</span>
                </button>
              </div>
            </div>
          )}
        </form>

        <div className="bg-slate-50 px-6 py-3 border-t border-slate-200 text-center">
          <p className="text-[10px] text-slate-400">
            Universidad Católica de Temuco · Dirección de Tecnologías de Información
          </p>
          <p className="text-[9px] text-slate-400 mt-0.5">
            Cumplimiento Ley 21.719 · Privacidad y Anonimización Criptográfica
          </p>
        </div>
      </div>

      {/* Modal de Recuperación de Contraseña (OWASP ASVS / RF27) */}
      {isForgotModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/70 backdrop-blur-xs animate-in fade-in">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-md w-full overflow-hidden">
            <div className="bg-[#002B49] text-white p-4 px-6 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <KeyRound size={18} className="text-[#C59B27]" />
                <h3 className="font-bold text-sm">Recuperación de Contraseña</h3>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsForgotModalOpen(false)
                  setForgotResult(null)
                }}
                className="text-white/70 hover:text-white cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-4">
              {!forgotResult ? (
                <form onSubmit={handleForgotSubmit} className="space-y-4">
                  <p className="text-xs text-slate-600 leading-relaxed">
                    Ingrese el correo institucional asociado a su cuenta. Si se encuentra registrado,
                    se generará un enlace efímero de un solo uso con validez de 15 minutos para definir una
                    nueva credencial y desbloquear su cuenta.
                  </p>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                      Correo Electrónico Institucional
                    </label>
                    <div className="relative">
                      <Mail size={16} className="absolute left-3 top-2.5 text-slate-400" />
                      <input
                        type="email"
                        required
                        value={forgotEmail}
                        onChange={(e) => setForgotEmail(e.target.value)}
                        placeholder="ejemplo@uct.cl"
                        className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#002B49]/30 focus:border-[#002B49]"
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setIsForgotModalOpen(false)}
                      className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg transition cursor-pointer"
                    >
                      Cancelar
                    </button>
                    <button
                      type="submit"
                      disabled={forgotLoading}
                      className="px-4 py-2 text-xs font-semibold text-white bg-[#002B49] hover:bg-[#003865] rounded-lg transition shadow-md flex items-center gap-2 cursor-pointer disabled:opacity-50"
                    >
                      {forgotLoading ? (
                        <span className="inline-block w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <span>Enviar Enlace de Recuperación</span>
                      )}
                    </button>
                  </div>
                </form>
              ) : (
                <div className="space-y-4">
                  <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl flex items-start gap-2.5 text-xs text-emerald-900">
                    <CheckCircle2 size={18} className="text-emerald-600 shrink-0 mt-0.5" />
                    <div className="space-y-1">
                      <p className="font-semibold">Solicitud Procesada</p>
                      <p className="text-[11.5px] leading-relaxed text-emerald-800">
                        {forgotResult.mensaje}
                      </p>
                    </div>
                  </div>

                  {forgotResult.enlace_recuperacion && (
                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
                      <div className="flex items-center justify-between text-[11px] font-semibold text-slate-700">
                        <span>Enlace de Recuperación Directo:</span>
                        {forgotResult.expira_en && (
                          <span className="text-[10px] text-amber-700 font-normal">
                            Válido por 15 min
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          readOnly
                          value={`${window.location.origin}${forgotResult.enlace_recuperacion}`}
                          className="w-full text-xs font-mono bg-white border border-slate-200 rounded px-2 py-1.5 text-slate-600 truncate select-all"
                        />
                        <button
                          type="button"
                          onClick={() => handleCopyLink(forgotResult.enlace_recuperacion!)}
                          className="px-2.5 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded text-xs font-semibold flex items-center gap-1 shrink-0 transition cursor-pointer"
                        >
                          <Copy size={12} />
                          <span>{copiedLink ? 'Copiado' : 'Copiar'}</span>
                        </button>
                      </div>

                      <div className="pt-1">
                        <a
                          href={forgotResult.enlace_recuperacion}
                          className="inline-flex items-center gap-1.5 text-xs font-bold text-[#002B49] hover:underline"
                        >
                          <span>Ir directamente a restablecer contraseña</span>
                          <ExternalLink size={12} />
                        </a>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center justify-end pt-2">
                    <button
                      type="button"
                      onClick={() => {
                        setIsForgotModalOpen(false)
                        setForgotResult(null)
                      }}
                      className="px-4 py-2 text-xs font-semibold text-white bg-[#002B49] hover:bg-[#003865] rounded-lg transition cursor-pointer"
                    >
                      Cerrar
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
export default LoginView
