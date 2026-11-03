import React, { useState, useEffect, useMemo, FormEvent } from 'react'
import {
  Lock,
  Eye,
  EyeOff,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ShieldCheck,
  ArrowRight,
  Loader2,
  KeyRound,
  ShieldAlert,
} from 'lucide-react'
import { verifyActivationToken, resetPassword, TokenVerifyData } from '../../api/client'

export function ResetPasswordView() {
  const [token, setToken] = useState<string>('')
  const [isLoadingToken, setIsLoadingToken] = useState(true)
  const [tokenData, setTokenData] = useState<TokenVerifyData | null>(null)
  const [tokenError, setTokenError] = useState<string | null>(null)

  const [nuevaPassword, setNuevaPassword] = useState('')
  const [confirmarPassword, setConfirmarPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSuccess, setIsSuccess] = useState(false)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const tokenParam = params.get('token')

    if (!tokenParam || tokenParam.trim().length === 0) {
      setTokenError('No se proporcionó un token de recuperación válido en el enlace.')
      setIsLoadingToken(false)
      return
    }

    setToken(tokenParam)

    verifyActivationToken(tokenParam)
      .then((data) => {
        setTokenData(data)
        setIsLoadingToken(false)
      })
      .catch((err: unknown) => {
        const axiosErr = err as { response?: { data?: { detail?: string } } }
        const message =
          axiosErr.response?.data?.detail ||
          'El enlace de recuperación es inválido o ha caducado (validez: 15 minutos). Por favor solicite un nuevo enlace.'
        setTokenError(message)
        setIsLoadingToken(false)
      })
  }, [])

  const passwordChecks = useMemo(() => {
    return {
      minLength: nuevaPassword.length >= 8,
      hasUpper: /[A-Z]/.test(nuevaPassword),
      hasNumber: /[0-9]/.test(nuevaPassword),
      hasSpecial: /[!@#$%^&*(),.?":{}|<>\-_=+[\];/~`]/.test(nuevaPassword),
      match: nuevaPassword.length > 0 && nuevaPassword === confirmarPassword,
    }
  }, [nuevaPassword, confirmarPassword])

  const strengthScore = useMemo(() => {
    let score = 0
    if (passwordChecks.minLength) score += 1
    if (passwordChecks.hasUpper) score += 1
    if (passwordChecks.hasNumber) score += 1
    if (passwordChecks.hasSpecial) score += 1
    return score
  }, [passwordChecks])

  const isValidPassword =
    passwordChecks.minLength &&
    passwordChecks.hasUpper &&
    passwordChecks.hasNumber &&
    passwordChecks.hasSpecial &&
    passwordChecks.match

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!isValidPassword) return

    setSubmitError(null)
    setIsSubmitting(true)

    try {
      await resetPassword({
        token,
        nueva_password: nuevaPassword,
        confirmar_password: confirmarPassword,
      })
      setIsSuccess(true)
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      setSubmitError(
        axiosErr.response?.data?.detail ||
          'Ocurrió un error al restablecer su contraseña. Por favor intente nuevamente.'
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  const getStrengthBarColor = () => {
    if (strengthScore <= 1) return 'bg-rose-500'
    if (strengthScore === 2) return 'bg-amber-500'
    if (strengthScore === 3) return 'bg-blue-500'
    return 'bg-emerald-500'
  }

  const getStrengthLabel = () => {
    if (strengthScore === 0) return 'Ingrese su contraseña'
    if (strengthScore <= 1) return 'Débil'
    if (strengthScore === 2) return 'Regular'
    if (strengthScore === 3) return 'Buena'
    return 'Excelente (Cumple Política UCT)'
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-gradient-to-br from-[#002B49] via-[#003865] to-[#001829] px-4 py-8 relative overflow-hidden">
      <div className="absolute inset-0 opacity-5 pointer-events-none bg-[radial-gradient(#C59B27_1px,transparent_1px)] [background-size:24px_24px]" />

      <div className="w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-white/20 overflow-hidden relative z-10 animate-in fade-in zoom-in-95 duration-200">
        {/* Encabezado */}
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
            <span>Sistema DSS · Seguridad y Control</span>
          </div>
          <h1 className="text-white text-base font-bold mt-1">
            Restablecer Contraseña Institucional
          </h1>
          <p className="text-white/70 text-xs mt-0.5">
            Recuperación de Acceso y Desbloqueo Seguro (OWASP ASVS)
          </p>
        </div>

        <div className="p-6">
          {/* 1. Estado de Carga */}
          {isLoadingToken && (
            <div className="py-12 flex flex-col items-center justify-center space-y-3">
              <Loader2 size={36} className="text-[#002B49] animate-spin" />
              <p className="text-xs font-medium text-slate-600">
                Verificando enlace de recuperación en el servidor...
              </p>
            </div>
          )}

          {/* 2. Error de Token */}
          {!isLoadingToken && tokenError && (
            <div className="py-6 space-y-4 text-center">
              <div className="w-12 h-12 bg-rose-50 text-rose-600 rounded-full flex items-center justify-center mx-auto border border-rose-200">
                <ShieldAlert size={26} />
              </div>
              <div className="space-y-1">
                <h3 className="text-sm font-bold text-slate-900">Enlace No Válido o Expirado</h3>
                <p className="text-xs text-slate-600 max-w-sm mx-auto leading-relaxed">
                  {tokenError}
                </p>
              </div>
              <div className="pt-2">
                <a
                  href="/login"
                  className="inline-flex items-center justify-center gap-1.5 px-4 py-2 bg-[#002B49] hover:bg-[#003865] text-white text-xs font-semibold rounded-lg shadow-sm transition"
                >
                  <span>Volver al Inicio de Sesión</span>
                  <ArrowRight size={14} />
                </a>
              </div>
            </div>
          )}

          {/* 3. Éxito de Restablecimiento */}
          {!isLoadingToken && !tokenError && isSuccess && (
            <div className="py-6 space-y-4 text-center animate-in fade-in">
              <div className="w-14 h-14 bg-emerald-50 text-emerald-600 rounded-full flex items-center justify-center mx-auto border border-emerald-200">
                <CheckCircle2 size={32} />
              </div>
              <div className="space-y-1.5">
                <h3 className="text-base font-bold text-slate-900">
                  ¡Contraseña Restablecida con Éxito!
                </h3>
                <p className="text-xs text-slate-600 max-w-sm mx-auto leading-relaxed">
                  Su cuenta institucional ha sido actualizada y desbloqueada preventivamente. Ya
                  puede ingresar a la plataforma con su nueva contraseña.
                </p>
              </div>
              <div className="pt-3">
                <a
                  href="/login"
                  className="inline-flex items-center justify-center gap-2 w-full py-2.5 px-4 bg-[#002B49] hover:bg-[#003865] text-white text-xs font-semibold rounded-lg shadow-md transition"
                >
                  <span>Iniciar Sesión Ahora</span>
                  <ArrowRight size={14} className="text-[#C59B27]" />
                </a>
              </div>
            </div>
          )}

          {/* 4. Formulario de Definición de Contraseña */}
          {!isLoadingToken && !tokenError && !isSuccess && (
            <form onSubmit={handleSubmit} className="space-y-4">
              {submitError && (
                <div className="flex items-start gap-2 p-3 text-xs bg-rose-50 border border-rose-200 text-rose-800 rounded-lg">
                  <AlertCircle size={15} className="text-rose-600 shrink-0 mt-0.5" />
                  <span>{submitError}</span>
                </div>
              )}

              {tokenData && (
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-[#002B49]/10 text-[#002B49] flex items-center justify-center font-bold text-xs shrink-0">
                    {tokenData.nombre_completo.charAt(0)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-bold text-slate-800 truncate">
                      {tokenData.nombre_completo}
                    </p>
                    <p className="text-[11px] text-slate-500 truncate">{tokenData.email}</p>
                  </div>
                  <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full shrink-0">
                    Token Verificado
                  </span>
                </div>
              )}

              {/* Nueva Contraseña */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Nueva Contraseña
                </label>
                <div className="relative">
                  <Lock size={15} className="absolute left-3 top-2.5 text-slate-400" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={nuevaPassword}
                    onChange={(e) => setNuevaPassword(e.target.value)}
                    placeholder="Mínimo 8 caracteres..."
                    className="w-full pl-9 pr-10 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#002B49]/30 focus:border-[#002B49] font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>

                {/* Barra de Fuerza */}
                {nuevaPassword.length > 0 && (
                  <div className="mt-2 space-y-1">
                    <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all duration-300 ${getStrengthBarColor()}`}
                        style={{ width: `${(strengthScore / 4) * 100}%` }}
                      />
                    </div>
                    <div className="flex justify-between items-center text-[10px]">
                      <span className="text-slate-500 font-medium">Fortaleza:</span>
                      <span className="font-bold text-slate-700">{getStrengthLabel()}</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Confirmar Contraseña */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Confirmar Contraseña
                </label>
                <div className="relative">
                  <Lock size={15} className="absolute left-3 top-2.5 text-slate-400" />
                  <input
                    type={showConfirmPassword ? 'text' : 'password'}
                    required
                    value={confirmarPassword}
                    onChange={(e) => setConfirmarPassword(e.target.value)}
                    placeholder="Repita su nueva contraseña..."
                    className="w-full pl-9 pr-10 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#002B49]/30 focus:border-[#002B49] font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                  >
                    {showConfirmPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              {/* Lista de Requisitos de Seguridad */}
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-1 text-[11px]">
                <p className="font-semibold text-slate-700 mb-1">
                  Requisitos de seguridad institucional:
                </p>
                <div className="grid grid-cols-2 gap-1 text-[10.5px]">
                  <div
                    className={`flex items-center gap-1.5 ${
                      passwordChecks.minLength ? 'text-emerald-700 font-semibold' : 'text-slate-500'
                    }`}
                  >
                    {passwordChecks.minLength ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                    <span>Mínimo 8 caracteres</span>
                  </div>
                  <div
                    className={`flex items-center gap-1.5 ${
                      passwordChecks.hasUpper ? 'text-emerald-700 font-semibold' : 'text-slate-500'
                    }`}
                  >
                    {passwordChecks.hasUpper ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                    <span>Al menos 1 mayúscula</span>
                  </div>
                  <div
                    className={`flex items-center gap-1.5 ${
                      passwordChecks.hasNumber ? 'text-emerald-700 font-semibold' : 'text-slate-500'
                    }`}
                  >
                    {passwordChecks.hasNumber ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                    <span>Al menos 1 número</span>
                  </div>
                  <div
                    className={`flex items-center gap-1.5 ${
                      passwordChecks.hasSpecial ? 'text-emerald-700 font-semibold' : 'text-slate-500'
                    }`}
                  >
                    {passwordChecks.hasSpecial ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                    <span>Carácter especial (!@#$)</span>
                  </div>
                </div>
                {confirmarPassword.length > 0 && (
                  <div
                    className={`pt-1 flex items-center gap-1.5 text-[10.5px] border-t border-slate-200/80 mt-1 ${
                      passwordChecks.match ? 'text-emerald-700 font-semibold' : 'text-rose-600'
                    }`}
                  >
                    {passwordChecks.match ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                    <span>{passwordChecks.match ? 'Las contraseñas coinciden' : 'Las contraseñas no coinciden'}</span>
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={!isValidPassword || isSubmitting}
                className="w-full py-2.5 px-4 bg-[#002B49] hover:bg-[#003865] text-white text-xs font-semibold rounded-lg shadow-md transition flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 border border-[#C59B27]/40"
              >
                {isSubmitting ? (
                  <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <>
                    <span>Guardar Nueva Contraseña y Desbloquear</span>
                    <ArrowRight size={14} className="text-[#C59B27]" />
                  </>
                )}
              </button>
            </form>
          )}
        </div>

        <div className="bg-slate-50 px-6 py-2.5 border-t border-slate-200 text-center">
          <p className="text-[10px] text-slate-400">
            Universidad Católica de Temuco · Dirección de Tecnologías de Información
          </p>
        </div>
      </div>
    </div>
  )
}

export default ResetPasswordView
