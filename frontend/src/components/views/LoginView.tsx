import React, { useState, FormEvent } from 'react'
import { Lock, Mail, Eye, EyeOff, AlertCircle, ArrowRight, ShieldCheck } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { api } from '../../api/client'

export function LoginView() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      const res = await api.post('/auth/login', { email, password })
      if (res.data?.access_token) {
        login(res.data.access_token)
      } else {
        setError('Respuesta de autenticación inválida.')
      }
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      const message = axiosErr.response?.data?.detail || 'Credenciales inválidas. Por favor intente nuevamente.'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const setPresetUser = (roleEmail: string, rolePass: string) => {
    setEmail(roleEmail)
    setPassword(rolePass)
    setError(null)
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
            <div className="flex items-start gap-2.5 p-3 text-xs bg-rose-50 border border-rose-200 text-rose-800 rounded-lg animate-in fade-in">
              <AlertCircle size={16} className="text-rose-600 shrink-0 mt-0.5" />
              <span>{error}</span>
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
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              Contraseña
            </label>
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

          <div className="pt-3 border-t border-slate-100">
            <p className="text-[11px] text-slate-500 font-medium mb-1.5 text-center">
              Accesos rápidos para demostración / evaluación:
            </p>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <button
                type="button"
                onClick={() => setPresetUser('admin@uct.cl', 'PasswordSuperSegura123!')}
                className="p-2 rounded-lg border border-purple-200 bg-purple-50 hover:bg-purple-100 text-purple-900 transition-colors text-left cursor-pointer"
              >
                <span className="font-bold block text-[11px]">SuperAdmin</span>
                <span className="text-[10px] text-purple-700 block truncate">admin@uct.cl</span>
              </button>
              <button
                type="button"
                onClick={() => setPresetUser('directivo@uct.cl', 'Password123!')}
                className="p-2 rounded-lg border border-blue-200 bg-blue-50 hover:bg-blue-100 text-blue-900 transition-colors text-left cursor-pointer"
              >
                <span className="font-bold block text-[11px]">Directivo</span>
                <span className="text-[10px] text-blue-700 block truncate">directivo@uct.cl</span>
              </button>
              <button
                type="button"
                onClick={() => setPresetUser('guardia_seguridad@uct.cl', 'Password123!')}
                className="p-2 rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-900 transition-colors text-left cursor-pointer"
              >
                <span className="font-bold block text-[11px]">Guardia</span>
                <span className="text-[10px] text-emerald-700 block truncate">guardia_...</span>
              </button>
            </div>
          </div>
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
    </div>
  )
}
