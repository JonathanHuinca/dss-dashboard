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
  UserCheck,
} from 'lucide-react'
import { verifyActivationToken, activateAccount, TokenVerifyData } from '../../api/client'

export function ActivateAccountView() {
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
      setTokenError('No se proporcionó un token de activación válido en el enlace.')
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
          'El enlace de activación es inválido o ha caducado. Por favor solicite una nueva invitación al administrador.'
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
      await activateAccount({
        token,
        nueva_password: nuevaPassword,
        confirmar_password: confirmarPassword,
      })
      setIsSuccess(true)
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      const msg =
        axiosErr.response?.data?.detail ||
        'Error al procesar la activación. Verifique que el enlace no haya expirado.'
      setSubmitError(msg)
    } finally {
      setIsSubmitting(false)
    }
  }

  const irAlLogin = () => {
    window.location.href = '/'
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
          <h1 className="text-white text-base font-bold mt-1">Activación de Cuenta Institucional</h1>
          <p className="text-white/70 text-xs mt-0.5">Establecimiento Seguro de Contraseña (Zero-Plaintext)</p>
        </div>

        {isLoadingToken ? (
          <div className="p-8 text-center space-y-3">
            <Loader2 className="w-8 h-8 animate-spin text-[#003865] mx-auto" />
            <p className="text-sm font-medium text-slate-700">Verificando firma digital del enlace...</p>
            <p className="text-xs text-slate-400">Validando vigencia criptográfica y estado de cuenta</p>
          </div>
        ) : tokenError ? (
          <div className="p-6 space-y-4">
            <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 space-y-2">
              <div className="flex items-center gap-2 font-semibold text-sm">
                <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />
                <span>Enlace No Válido o Expirado</span>
              </div>
              <p className="text-xs text-rose-700 leading-relaxed">{tokenError}</p>
            </div>
            <p className="text-xs text-slate-500 text-center">
              Por razones de seguridad institucional (Ley 21.719), los enlaces de activación tienen una vigencia estricta de 1 hora.
            </p>
            <button
              onClick={irAlLogin}
              className="w-full py-2.5 px-4 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-2"
            >
              <span>Volver a la Pantalla de Ingreso</span>
              <ArrowRight size={14} />
            </button>
          </div>
        ) : isSuccess ? (
          <div className="p-6 space-y-5 text-center">
            <div className="w-14 h-14 bg-emerald-50 border border-emerald-200 rounded-full flex items-center justify-center mx-auto text-emerald-600 shadow-inner">
              <CheckCircle2 size={32} />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">Cuenta Activada Exitosamente</h2>
              <p className="text-xs text-slate-600 mt-1">
                Su contraseña institucional ha sido cifrada y almacenada bajo estándares de alta seguridad.
              </p>
            </div>
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-left text-xs text-slate-600 space-y-1">
              <div>
                <span className="font-semibold text-slate-700">Usuario:</span> {tokenData?.nombre_completo}
              </div>
              <div>
                <span className="font-semibold text-slate-700">Correo:</span> {tokenData?.email}
              </div>
              <div>
                <span className="font-semibold text-slate-700">Estado:</span> Cuenta Activa
              </div>
            </div>
            <button
              onClick={irAlLogin}
              className="w-full py-2.5 px-4 bg-gradient-to-r from-[#002B49] to-[#003865] hover:from-[#003865] hover:to-[#004f8f] text-white rounded-lg text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2"
            >
              <span>Iniciar Sesión en DSS UCT</span>
              <ArrowRight size={14} />
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            {submitError && (
              <div className="flex items-start gap-2.5 p-3 text-xs bg-rose-50 border border-rose-200 text-rose-800 rounded-lg">
                <AlertCircle size={16} className="text-rose-600 shrink-0 mt-0.5" />
                <span>{submitError}</span>
              </div>
            )}

            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-[#002B49]/10 text-[#002B49] flex items-center justify-center shrink-0">
                <UserCheck size={18} />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-bold text-slate-900 truncate">{tokenData?.nombre_completo}</p>
                <p className="text-xs text-slate-500 truncate">{tokenData?.email}</p>
              </div>
            </div>

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
                  placeholder="Ingrese contraseña segura"
                  className="w-full pl-9 pr-10 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#002B49]/30 focus:border-[#002B49] transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Confirmar Contraseña
              </label>
              <div className="relative">
                <KeyRound size={15} className="absolute left-3 top-2.5 text-slate-400" />
                <input
                  type={showConfirmPassword ? 'text' : 'password'}
                  required
                  value={confirmarPassword}
                  onChange={(e) => setConfirmarPassword(e.target.value)}
                  placeholder="Reingrese contraseña"
                  className="w-full pl-9 pr-10 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#002B49]/30 focus:border-[#002B49] transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  {showConfirmPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <div className="space-y-1.5 pt-1">
              <div className="flex items-center justify-between text-[11px] font-medium text-slate-600">
                <span>Fortaleza de Contraseña</span>
                <span
                  className={
                    strengthScore >= 4
                      ? 'text-emerald-600 font-bold'
                      : strengthScore >= 2
                      ? 'text-amber-600 font-bold'
                      : 'text-slate-400'
                  }
                >
                  {strengthScore === 4
                    ? 'Muy Fuerte'
                    : strengthScore === 3
                    ? 'Fuerte'
                    : strengthScore === 2
                    ? 'Media'
                    : 'Insuficiente'}
                </span>
              </div>
              <div className="grid grid-cols-4 gap-1 h-1.5">
                {[1, 2, 3, 4].map((step) => (
                  <div
                    key={step}
                    className={`rounded-full transition-all ${
                      strengthScore >= step
                        ? strengthScore === 4
                          ? 'bg-emerald-500'
                          : strengthScore === 3
                          ? 'bg-blue-500'
                          : 'bg-amber-400'
                        : 'bg-slate-200'
                    }`}
                  />
                ))}
              </div>
            </div>

            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-1.5 text-[11px]">
              <div className="flex items-center gap-2">
                {passwordChecks.minLength ? (
                  <CheckCircle2 size={13} className="text-emerald-600 shrink-0" />
                ) : (
                  <XCircle size={13} className="text-slate-300 shrink-0" />
                )}
                <span className={passwordChecks.minLength ? 'text-slate-800' : 'text-slate-400'}>
                  Mínimo 8 caracteres
                </span>
              </div>
              <div className="flex items-center gap-2">
                {passwordChecks.hasUpper ? (
                  <CheckCircle2 size={13} className="text-emerald-600 shrink-0" />
                ) : (
                  <XCircle size={13} className="text-slate-300 shrink-0" />
                )}
                <span className={passwordChecks.hasUpper ? 'text-slate-800' : 'text-slate-400'}>
                  Al menos una letra mayúscula (A-Z)
                </span>
              </div>
              <div className="flex items-center gap-2">
                {passwordChecks.hasNumber ? (
                  <CheckCircle2 size={13} className="text-emerald-600 shrink-0" />
                ) : (
                  <XCircle size={13} className="text-slate-300 shrink-0" />
                )}
                <span className={passwordChecks.hasNumber ? 'text-slate-800' : 'text-slate-400'}>
                  Al menos un dígito numérico (0-9)
                </span>
              </div>
              <div className="flex items-center gap-2">
                {passwordChecks.hasSpecial ? (
                  <CheckCircle2 size={13} className="text-emerald-600 shrink-0" />
                ) : (
                  <XCircle size={13} className="text-slate-300 shrink-0" />
                )}
                <span className={passwordChecks.hasSpecial ? 'text-slate-800' : 'text-slate-400'}>
                  Al menos un caracter especial (!@#$%...)
                </span>
              </div>
              <div className="flex items-center gap-2 pt-0.5 border-t border-slate-200">
                {passwordChecks.match ? (
                  <CheckCircle2 size={13} className="text-emerald-600 shrink-0" />
                ) : (
                  <XCircle size={13} className="text-slate-300 shrink-0" />
                )}
                <span className={passwordChecks.match ? 'text-slate-800' : 'text-slate-400'}>
                  Las contraseñas coinciden
                </span>
              </div>
            </div>

            <button
              type="submit"
              disabled={!isValidPassword || isSubmitting}
              className={`w-full py-2.5 px-4 rounded-lg text-xs font-bold text-white transition-all shadow-md flex items-center justify-center gap-2 ${
                isValidPassword && !isSubmitting
                  ? 'bg-gradient-to-r from-[#002B49] to-[#003865] hover:from-[#003865] hover:to-[#004f8f] cursor-pointer'
                  : 'bg-slate-300 cursor-not-allowed opacity-75'
              }`}
            >
              {isSubmitting ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Cifrando y activando...</span>
                </>
              ) : (
                <>
                  <span>Activar Cuenta y Definir Credencial</span>
                  <ArrowRight size={14} />
                </>
              )}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
export default ActivateAccountView
