import React, { Suspense, lazy, memo, useEffect, useState } from 'react'
import {
  ShieldCheck,
  UserCheck,
  Calendar,
  MapPin,
  Clock,
  Sparkles,
  Send,
  Printer,
  AlertTriangle,
  BarChart2,
  MessageSquare,
  History,
  Lock,
  Layers,
  Users,
  Activity,
  TrendingUp,
  TrendingDown,
  Car,
  RotateCcw,
  LogOut,
  LogIn,
  GraduationCap,
  Flame,
  Repeat,
  ParkingCircle,
  CheckCircle,
  Moon,
} from 'lucide-react'
import {
  RespuestaReportePublico,
  fetchReportePublicoPorToken,
  fetchPortalDestinatarioPorToken,
  fetchMisReportesConsultor,
  consultarIAReportePublico,
  activarCuentaConsultorDesdeReporte,
} from '../../api/client'
import { KpiCard } from '../ui/KpiCard'
import { ChartCard } from '../ui/ChartCard'
import { useAuth } from '../../context/AuthContext'
import { useAssistant } from '../../context/AssistantContext'

const HourlyBarChart = memo(lazy(() => import('../charts/HourlyBarChart').then((m) => ({ default: m.HourlyBarChart }))))
const OccupancyAreaChart = memo(
  lazy(() => import('../charts/OccupancyAreaChart').then((m) => ({ default: m.OccupancyAreaChart })))
)
const ForecastLineChart = memo(
  lazy(() => import('../charts/ForecastLineChart').then((m) => ({ default: m.ForecastLineChart })))
)
const HeatmapChart = memo(lazy(() => import('../charts/HeatmapChart').then((m) => ({ default: m.HeatmapChart }))))
const WeeklyEvolutionPlotlyChart = memo(
  lazy(() => import('../charts/WeeklyEvolutionPlotlyChart').then((m) => ({ default: m.WeeklyEvolutionPlotlyChart })))
)
const MonthlyVolumePlotlyChart = memo(
  lazy(() => import('../charts/MonthlyVolumePlotlyChart').then((m) => ({ default: m.MonthlyVolumePlotlyChart })))
)
const AcademicMilestonesPlotlyChart = memo(
  lazy(() =>
    import('../charts/AcademicMilestonesPlotlyChart').then((m) => ({ default: m.AcademicMilestonesPlotlyChart }))
  )
)
const DoorUsagePlotlyChart = memo(
  lazy(() => import('../charts/DoorUsagePlotlyChart').then((m) => ({ default: m.DoorUsagePlotlyChart })))
)
const RoomComparisonPlotlyChart = memo(
  lazy(() => import('../charts/RoomComparisonPlotlyChart').then((m) => ({ default: m.RoomComparisonPlotlyChart })))
)
const CurricularDistributionPlotlyChart = memo(
  lazy(() =>
    import('../charts/CurricularDistributionPlotlyChart').then((m) => ({
      default: m.CurricularDistributionPlotlyChart,
    }))
  )
)
const CheckinDistributionPlotlyChart = memo(
  lazy(() =>
    import('../charts/CheckinDistributionPlotlyChart').then((m) => ({ default: m.CheckinDistributionPlotlyChart }))
  )
)
const VisitProfilesPlotlyChart = memo(
  lazy(() => import('../charts/VisitProfilesPlotlyChart').then((m) => ({ default: m.VisitProfilesPlotlyChart })))
)
const DailyAverageAttendancePlotlyChart = memo(
  lazy(() =>
    import('../charts/DailyAverageAttendancePlotlyChart').then((m) => ({
      default: m.DailyAverageAttendancePlotlyChart,
    }))
  )
)

const FleetDonutChart = memo(
  lazy(() => import('../charts/FleetDonutChart').then((m) => ({ default: m.FleetDonutChart })))
)
const VehicleDailyPlotlyChart = memo(
  lazy(() => import('../charts/VehicleDailyPlotlyChart').then((m) => ({ default: m.VehicleDailyPlotlyChart })))
)
const VehicleMilestonesPlotlyChart = memo(
  lazy(() =>
    import('../charts/VehicleMilestonesPlotlyChart').then((m) => ({ default: m.VehicleMilestonesPlotlyChart }))
  )
)
const CameraStatsPlotlyChart = memo(
  lazy(() => import('../charts/CameraStatsPlotlyChart').then((m) => ({ default: m.CameraStatsPlotlyChart })))
)
const IntercampusMobilityPlotlyChart = memo(
  lazy(() =>
    import('../charts/IntercampusMobilityPlotlyChart').then((m) => ({ default: m.IntercampusMobilityPlotlyChart }))
  )
)
const VehicleBehavioralClustersPlotlyChart = memo(
  lazy(() =>
    import('../charts/VehicleBehavioralClustersPlotlyChart').then((m) => ({
      default: m.VehicleBehavioralClustersPlotlyChart,
    }))
  )
)
const SeccionCampana24Horas = lazy(() =>
  import('./biblioteca/SeccionCampana24Horas').then((m) => ({
    default: m.SeccionCampana24Horas,
  }))
) as React.ComponentType<any>

function EsqueletoGraficoInstitucional() {
  return (
    <div className="h-full min-h-[280px] w-full flex items-center justify-center bg-slate-50 rounded-xl animate-pulse border border-slate-200">
      <div className="flex flex-col items-center gap-2 text-slate-500">
        <BarChart2 className="w-7 h-7 text-uct-blue-primary" />
        <span className="text-xs font-medium">Cargando visualización institucional...</span>
      </div>
    </div>
  )
}

interface ReporteCompartidoViewProps {
  modoRuta: 'reporte' | 'portal' | 'consultor'
  token?: string
}

export const ReporteCompartidoView: React.FC<ReporteCompartidoViewProps> = ({ modoRuta, token = '' }) => {
  const { isAuthenticated, logout, loginWithCredentials } = useAuth()
  const { isAiEnabled } = useAssistant()
  const [tokenReporteActivo, setTokenReporteActivo] = useState<string>(modoRuta === 'reporte' ? token : '')
  const [datosReporte, setDatosReporte] = useState<RespuestaReportePublico | null>(null)
  const [datosPortal, setDatosPortal] = useState<{ destinatario: any; reportes: any[] } | null>(null)
  const [cargando, setCargando] = useState<boolean>(true)
  const [errorAcceso, setErrorAcceso] = useState<string | null>(null)
  const [mostrarBandejaHistorica, setMostrarBandejaHistorica] = useState<boolean>(modoRuta !== 'reporte')

  const [preguntaIA, setPreguntaIA] = useState<string>('')
  const [consultandoIA, setConsultandoIA] = useState<boolean>(false)
  const [conversacionIA, setConversacionIA] = useState<Array<{ pregunta: string; respuesta: string; hora: string }>>([])
  const [errorIA, setErrorIA] = useState<string | null>(null)

  const [emailIngreso, setEmailIngreso] = useState<string>('')
  const [passwordIngreso, setPasswordIngreso] = useState<string>('')
  const [ingresandoLogin, setIngresandoLogin] = useState<boolean>(false)
  const [errorLogin, setErrorLogin] = useState<string | null>(null)

  const [nuevaPassword, setNuevaPassword] = useState<string>('')
  const [confirmarPassword, setConfirmarPassword] = useState<string>('')
  const [creandoPassword, setCreandoPassword] = useState<boolean>(false)
  const [errorPassword, setErrorPassword] = useState<string | null>(null)
  const [passwordCreadaExito, setPasswordCreadaExito] = useState<boolean>(false)

  useEffect(() => {
    if (modoRuta === 'consultor') {
      cargarPortalConsultorAutenticado()
    } else if (modoRuta === 'portal') {
      cargarPortalDestinatario(token)
    } else {
      cargarReportePorToken(token)
    }
  }, [modoRuta, token])

  const cargarPortalConsultorAutenticado = async () => {
    setCargando(true)
    setErrorAcceso(null)
    try {
      const resp = await fetchMisReportesConsultor()
      setDatosPortal(resp)
      const primerVigente = (resp.reportes || []).find((r: any) => r.vigente)
      if (primerVigente) {
        setTokenReporteActivo(primerVigente.token_acceso)
        const repData = await fetchReportePublicoPorToken(primerVigente.token_acceso)
        setDatosReporte(repData)
      }
    } catch (err: any) {
      setErrorAcceso(err?.response?.data?.detail || 'No fue posible cargar su bandeja de reportes ejecutivos.')
    } finally {
      setCargando(false)
    }
  }

  const cargarPortalDestinatario = async (tokenPortal: string) => {
    setCargando(true)
    setErrorAcceso(null)
    try {
      const resp = await fetchPortalDestinatarioPorToken(tokenPortal)
      setDatosPortal(resp)
      const primerVigente = (resp.reportes || []).find((r: any) => r.vigente)
      if (primerVigente) {
        setTokenReporteActivo(primerVigente.token_acceso)
        const repData = await fetchReportePublicoPorToken(primerVigente.token_acceso)
        setDatosReporte(repData)
      }
    } catch (err: any) {
      setErrorAcceso(
        err?.response?.data?.detail || 'No fue posible acceder a la bandeja histórica de reportes ejecutivos.'
      )
    } finally {
      setCargando(false)
    }
  }

  const cargarReportePorToken = async (tokenRep: string) => {
    setCargando(true)
    setErrorAcceso(null)
    try {
      const resp = await fetchReportePublicoPorToken(tokenRep)
      setDatosReporte(resp)
      setTokenReporteActivo(tokenRep)
      if (resp.reporte?.destinatario?.email) {
        setEmailIngreso(resp.reporte.destinatario.email)
      }
    } catch (err: any) {
      setErrorAcceso(
        err?.response?.data?.detail || 'Este enlace de reporte compartido no está disponible o ha sido deshabilitado.'
      )
    } finally {
      setCargando(false)
    }
  }

  const handleConsultarIA = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!preguntaIA.trim() || !tokenReporteActivo) return
    setConsultandoIA(true)
    setErrorIA(null)
    const pregActual = preguntaIA.trim()
    setPreguntaIA('')
    try {
      const res = await consultarIAReportePublico(tokenReporteActivo, pregActual)
      setConversacionIA((prev) => [
        ...prev,
        {
          pregunta: pregActual,
          respuesta: res.respuesta,
          hora: new Date().toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' }),
        },
      ])
    } catch (err: any) {
      setErrorIA(err?.response?.data?.detail || 'No fue posible procesar la consulta con el asistente IA.')
    } finally {
      setConsultandoIA(false)
    }
  }

  const handleCrearPasswordConsultor = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!datosReporte?.token_activacion) return
    if (nuevaPassword.length < 8) {
      setErrorPassword('La contraseña debe tener al menos 8 caracteres.')
      return
    }
    if (nuevaPassword !== confirmarPassword) {
      setErrorPassword('Las contraseñas ingresadas no coinciden.')
      return
    }
    setCreandoPassword(true)
    setErrorPassword(null)
    try {
      await activarCuentaConsultorDesdeReporte(datosReporte.token_activacion, nuevaPassword, confirmarPassword)
      setPasswordCreadaExito(true)
    } catch (err: any) {
      setErrorPassword(
        err?.response?.data?.detail ||
          'No fue posible registrar la contraseña. Debe tener mínimo 8 caracteres, una mayúscula, un número y un carácter especial.'
      )
    } finally {
      setCreandoPassword(false)
    }
  }

  const handleLoginReporte = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!emailIngreso.trim() || !passwordIngreso) return
    setIngresandoLogin(true)
    setErrorLogin(null)
    try {
      const ok = await loginWithCredentials(emailIngreso.trim(), passwordIngreso)
      if (!ok) {
        setErrorLogin('Credenciales institucionales incorrectas. Verifique su correo y contraseña.')
      }
    } catch (err: any) {
      setErrorLogin(err?.message || 'Error al autenticar credenciales institucionales.')
    } finally {
      setIngresandoLogin(false)
    }
  }

  if (cargando) {
    return (
      <div className="min-h-screen bg-uct-bg-main text-slate-800 flex flex-col items-center justify-center p-6">
        <div className="bg-white p-8 rounded-2xl border border-slate-200 shadow-lg flex flex-col items-center text-center max-w-md">
          <div className="h-12 px-3 py-1.5 rounded-xl bg-white border border-uct-gold/50 shadow-xs mb-4 flex items-center justify-center">
            <img src="/uct_logo.png" alt="UCT" className="h-8 w-auto object-contain" />
          </div>
          <h2 className="text-base font-bold text-uct-blue-primary">
            Cargando Reporte Ejecutivo Institucional...
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Universidad Católica de Temuco — Campus San Francisco
          </p>
        </div>
      </div>
    )
  }

  if (errorAcceso || (!datosReporte && !datosPortal)) {
    return (
      <div className="min-h-screen bg-uct-bg-main text-slate-800 flex flex-col items-center justify-center p-6">
        <div className="max-w-md w-full bg-white border border-slate-200 rounded-2xl p-6 text-center space-y-4 shadow-xl">
          <div className="h-11 px-3 py-1 rounded-xl bg-white border border-uct-gold/50 shadow-xs mx-auto w-fit flex items-center justify-center">
            <img src="/uct_logo.png" alt="UCT" className="h-7 w-auto object-contain" />
          </div>
          <div className="w-11 h-11 mx-auto rounded-full bg-red-50 border border-red-200 flex items-center justify-center text-red-600">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <h2 className="text-base font-bold text-uct-blue-primary">Reporte Ejecutivo No Disponible</h2>
          <p className="text-xs text-slate-600 leading-relaxed">{errorAcceso}</p>
          <div className="pt-3 border-t border-slate-100 text-[11px] text-slate-500">
            Si requiere reactivar este reporte o solicitar una nueva emisión, contacte a la Dirección del Recinto o
            Administración DSS UCT.
          </div>
        </div>
      </div>
    )
  }

  const reporte = datosReporte?.reporte
  const datos = datosReporte?.datos
  const indEjecutivos = datos?.indicadores_ejecutivos || {}
  const indVisibles = datos?.indicadores_visibles || []
  const grafVisibles = datos?.graficos_visibles || []
  const grafData = datos?.graficos || {}
  const notasItems = reporte?.notas_items || []
  const historial = datosReporte?.historial_destinatario || datosPortal?.reportes || []
  const destinatario = reporte?.destinatario || datosPortal?.destinatario

  if (datosReporte?.requiere_crear_password && !passwordCreadaExito && datosReporte?.token_activacion) {
    return (
      <div className="min-h-screen bg-uct-bg-main text-slate-800 flex flex-col items-center justify-center p-6">
        <div className="max-w-lg w-full bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-xl">
          <div className="bg-uct-blue-primary px-6 py-5 border-b-4 border-uct-gold flex items-center gap-3">
            <div className="h-10 px-2.5 py-1 rounded-lg bg-white border border-uct-gold/50 shadow-xs shrink-0 flex items-center justify-center">
              <img src="/uct_logo.png" alt="UCT" className="h-6 w-auto object-contain" />
            </div>
            <div>
              <span className="text-[10px] font-bold uppercase tracking-widest text-uct-gold block">
                Activación de Cuenta Consultor de Reporte
              </span>
              <h2 className="text-sm font-bold text-white leading-snug">
                Universidad Católica de Temuco — DSS Campus San Francisco
              </h2>
            </div>
          </div>

          <form onSubmit={handleCrearPasswordConsultor} className="p-6 space-y-4">
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 text-xs text-slate-700 space-y-1">
              <p className="font-bold text-uct-blue-primary">
                Bienvenido/a, {destinatario?.nombre_completo || 'Consultor Institucional'}
              </p>
              <p className="text-slate-600">
                Para visualizar el reporte ejecutivo{' '}
                <strong className="text-slate-800">"{reporte?.titulo_reporte}"</strong> y acceder a su bandeja histórica
                en <span className="font-mono text-[11px]">{destinatario?.correo}</span>, primero debe definir su
                contraseña personal de acceso.
              </p>
            </div>

            {errorPassword && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs font-medium flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 text-red-600" />
                <span>{errorPassword}</span>
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Crear Contraseña Institucional *
              </label>
              <input
                type="password"
                required
                value={nuevaPassword}
                onChange={(e) => setNuevaPassword(e.target.value)}
                placeholder="Mínimo 8 caracteres, 1 mayúscula, 1 número y 1 símbolo"
                className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800 focus:border-uct-blue-primary outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Confirmar Contraseña *
              </label>
              <input
                type="password"
                required
                value={confirmarPassword}
                onChange={(e) => setConfirmarPassword(e.target.value)}
                placeholder="Repita su contraseña"
                className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800 focus:border-uct-blue-primary outline-none"
              />
            </div>

            <p className="text-[11px] text-slate-500">
              Requisitos de seguridad: mínimo 8 caracteres, al menos una letra mayúscula, un número y un carácter
              especial (ej. <span className="font-mono">Uct2026!</span>).
            </p>

            <button
              type="submit"
              disabled={creandoPassword}
              className="w-full py-2.5 px-4 rounded-xl bg-uct-blue-primary hover:bg-uct-blue-dark disabled:opacity-50 text-white text-xs font-bold shadow-sm transition-colors flex items-center justify-center gap-2"
            >
              <Lock className="w-4 h-4 text-uct-gold" />
              {creandoPassword ? 'Guardando contraseña y abriendo reporte...' : 'Crear Contraseña y Ver Reporte Ejecutivo'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  if (!isAuthenticated && !passwordCreadaExito) {
    return (
      <div className="min-h-screen bg-uct-bg-main text-slate-800 flex flex-col items-center justify-center p-6">
        <div className="max-w-md w-full bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-xl">
          <div className="bg-uct-blue-primary px-6 py-5 border-b-4 border-uct-gold flex items-center gap-3">
            <div className="h-10 px-2.5 py-1 rounded-lg bg-white border border-uct-gold/50 shadow-xs shrink-0 flex items-center justify-center">
              <img src="/uct_logo.png" alt="UCT" className="h-6 w-auto object-contain" />
            </div>
            <div>
              <span className="text-[10px] font-bold uppercase tracking-widest text-uct-gold block">
                Acceso a Reporte Confidencial
              </span>
              <h2 className="text-sm font-bold text-white leading-snug">
                Universidad Católica de Temuco — DSS Campus San Francisco
              </h2>
            </div>
          </div>

          <form onSubmit={handleLoginReporte} className="p-6 space-y-4">
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 text-xs text-slate-700 space-y-1">
              <p className="font-bold text-uct-blue-primary">
                Identificación Requerida
              </p>
              <p className="text-slate-600">
                Para visualizar el reporte ejecutivo{' '}
                <strong className="text-slate-800">"{reporte?.titulo_reporte}"</strong> ({reporte?.codigo_corto}),
                ingrese sus credenciales institucionales.
              </p>
            </div>

            {errorLogin && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs font-medium flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 text-red-600" />
                <span>{errorLogin}</span>
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Correo Electrónico Institucional *
              </label>
              <input
                type="email"
                required
                value={emailIngreso}
                onChange={(e) => setEmailIngreso(e.target.value)}
                placeholder="ejemplo@uct.cl"
                className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800 focus:border-uct-blue-primary outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Contraseña Institucional *
              </label>
              <input
                type="password"
                required
                value={passwordIngreso}
                onChange={(e) => setPasswordIngreso(e.target.value)}
                placeholder="Ingrese su contraseña"
                className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800 focus:border-uct-blue-primary outline-none"
              />
            </div>

            <button
              type="submit"
              disabled={ingresandoLogin}
              className="w-full py-2.5 px-4 rounded-xl bg-uct-blue-primary hover:bg-uct-blue-dark disabled:opacity-50 text-white text-xs font-bold shadow-sm transition-colors flex items-center justify-center gap-2 cursor-pointer"
            >
              <Lock className="w-4 h-4 text-uct-gold" />
              {ingresandoLogin ? 'Verificando credenciales...' : 'Ingresar y Ver Reporte'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  const obtenerNotasDeSeccion = (seccionId: string) => {
    return notasItems.filter((n) => n.seccion === seccionId)
  }

  const formatearValorIndicador = (
    id: string
  ): {
    valor: string
    subtitulo: string
    icono: any
    color: string
    esBannerGerencial?: boolean
    gradienteBarra?: string
    claseIconoBanner?: string
  } => {
    if (reporte?.espacio_id === 1) {
      switch (id) {
        case 'dias_operativos':
          return {
            valor: `${Number(indEjecutivos.dias_operativos ?? 0).toLocaleString('es-CL')} días`,
            subtitulo: 'Con registro de actividad',
            icono: Calendar,
            color: '#0D9488',
            esBannerGerencial: true,
            gradienteBarra: 'from-teal-500 to-emerald-500',
            claseIconoBanner: 'bg-teal-50 text-teal-600 border-teal-200/60',
          }
        case 'carrera_mas_concurrida':
          return {
            valor: String(indEjecutivos.carrera_mas_concurrida || 'Sin catalogar'),
            subtitulo: 'Mayor afluencia acumulada',
            icono: GraduationCap,
            color: '#003865',
            esBannerGerencial: true,
            gradienteBarra: 'from-uct-blue-primary to-blue-600',
            claseIconoBanner: 'bg-blue-50 text-uct-blue-primary border-blue-200/60',
          }
        case 'recurrencia_mensual':
          return {
            valor: `${Number(indEjecutivos.recurrencia_mensual ?? 0).toFixed(1).replace('.', ',')}x`,
            subtitulo: 'Visitas promedio / usuario',
            icono: Repeat,
            color: '#9333EA',
            esBannerGerencial: true,
            gradienteBarra: 'from-purple-500 to-violet-600',
            claseIconoBanner: 'bg-purple-50 text-purple-600 border-purple-200/60',
          }
        case 'hora_pico_ingreso':
          return {
            valor: String(indEjecutivos.hora_pico_ingreso || '14:00 hrs'),
            subtitulo: 'Mayor afluencia histórica',
            icono: Flame,
            color: '#D97706',
            esBannerGerencial: true,
            gradienteBarra: 'from-amber-400 to-orange-500',
            claseIconoBanner: 'bg-amber-50 text-amber-600 border-amber-200/60',
          }
        case 'pico_concurrente':
          return {
            valor: `${Number(indEjecutivos.pico_concurrente ?? 0).toLocaleString('es-CL')} pers`,
            subtitulo: 'Máximo horario registrado',
            icono: Users,
            color: '#E11D48',
            esBannerGerencial: true,
            gradienteBarra: 'from-rose-500 to-red-600',
            claseIconoBanner: 'bg-rose-50 text-rose-600 border-rose-200/60',
          }
        case 'afluencia_total':
        case 'total_accesos':
          return {
            valor: Number(
              indEjecutivos.afluencia_total ?? indEjecutivos.total_accesos ?? 0
            ).toLocaleString('es-CL'),
            subtitulo: `${Number(indEjecutivos.usuarios_unicos ?? 0).toLocaleString('es-CL')} estudiantes únicos`,
            icono: Users,
            color: '#00689B',
          }
        case 'aforo_maximo_registrado':
          return {
            valor: `${Number(indEjecutivos.aforo_maximo_registrado ?? 0).toLocaleString('es-CL')} personas`,
            subtitulo: `Máximo vs ${indEjecutivos.capacidad_asientos ?? 276} asientos (${indEjecutivos.sala_filtrada || 'Global'})`,
            icono: BarChart2,
            color: '#16A34A',
          }
        case 'estadia_promedio':
        case 'permanencia_promedio':
          return {
            valor: `${indEjecutivos.estadia_promedio_min ?? indEjecutivos.permanencia_promedio_min ?? 0} min`,
            subtitulo: 'tiempo promedio de visita regular',
            icono: Clock,
            color: '#D97706',
          }
        case 'tasa_rebote':
          return {
            valor: `${Number(indEjecutivos.tasa_rebote_pct ?? 0).toFixed(1).replace('.', ',')}%`,
            subtitulo: 'visitas menores a 15 min',
            icono: TrendingDown,
            color: '#DC2626',
          }
        default:
          return { valor: '—', subtitulo: '', icono: Activity, color: '#003865' }
      }
    } else {
      switch (id) {
        case 'dias_operativos':
          return {
            valor: `${Number(indEjecutivos.dias_operativos ?? 0).toLocaleString('es-CL')} días`,
            subtitulo: 'Con monitoreo ANPR activo',
            icono: Calendar,
            color: '#0D9488',
            esBannerGerencial: true,
            gradienteBarra: 'from-teal-500 to-emerald-500',
            claseIconoBanner: 'bg-teal-50 text-teal-600 border-teal-200/60',
          }
        case 'sector_mas_concurrido':
          return {
            valor: String(indEjecutivos.sector_mas_concurrido || 'Campus San Francisco'),
            subtitulo: 'Mayor afluencia de accesos ANPR',
            icono: ParkingCircle,
            color: '#003865',
            esBannerGerencial: true,
            gradienteBarra: 'from-uct-blue-primary to-blue-600',
            claseIconoBanner: 'bg-blue-50 text-uct-blue-primary border-blue-200/60',
          }
        case 'recurrencia_vehicular':
          return {
            valor: `${Number(indEjecutivos.recurrencia_vehicular ?? 0).toFixed(1).replace('.', ',')}x`,
            subtitulo: 'Ingresos promedio / patente',
            icono: Repeat,
            color: '#9333EA',
            esBannerGerencial: true,
            gradienteBarra: 'from-purple-500 to-violet-600',
            claseIconoBanner: 'bg-purple-50 text-purple-600 border-purple-200/60',
          }
        case 'hora_pico_acceso':
        case 'hora_punta_congestion':
          return {
            valor: String(indEjecutivos.hora_pico_acceso || indEjecutivos.hora_punta_congestion || '08:00 hrs'),
            subtitulo: 'Mayor flujo vehicular matutino',
            icono: Flame,
            color: '#D97706',
            esBannerGerencial: true,
            gradienteBarra: 'from-amber-400 to-orange-500',
            claseIconoBanner: 'bg-amber-50 text-amber-600 border-amber-200/60',
          }
        case 'pico_concurrente':
          return {
            valor: `${Number(indEjecutivos.pico_concurrente ?? 0).toLocaleString('es-CL')} veh`,
            subtitulo: 'Máximo aforo vehicular en 1h',
            icono: Car,
            color: '#E11D48',
            esBannerGerencial: true,
            gradienteBarra: 'from-rose-500 to-red-600',
            claseIconoBanner: 'bg-rose-50 text-rose-600 border-rose-200/60',
          }
        case 'vehiculos_dentro':
          return {
            valor: `${Number(indEjecutivos.vehiculos_presentes ?? 0)} / ${Number(indEjecutivos.capacidad_plazas ?? 125)}`,
            subtitulo: `${Number(indEjecutivos.ocupacion_pct ?? 0).toFixed(1).replace('.', ',')}% ocupación`,
            icono: Car,
            color: '#00689B',
          }
        case 'plazas_libres':
          return {
            valor: Number(indEjecutivos.plazas_disponibles ?? 0).toLocaleString('es-CL'),
            subtitulo: `de ${indEjecutivos.capacidad_plazas ?? 125} plazas calibradas`,
            icono: CheckCircle,
            color: '#16A34A',
          }
        case 'total_ingresos':
        case 'total_ingresos_vehiculares':
          return {
            valor: Number(
              indEjecutivos.total_ingresos ?? indEjecutivos.total_ingresos_vehiculares ?? 0
            ).toLocaleString('es-CL'),
            subtitulo: 'entradas vehiculares registradas',
            icono: LogIn,
            color: '#00689B',
          }
        case 'total_salidas':
          return {
            valor: Number(indEjecutivos.total_salidas ?? 0).toLocaleString('es-CL'),
            subtitulo: 'salidas ANPR validadas',
            icono: LogOut,
            color: '#D97706',
          }
        case 'rotacion_diaria':
        case 'indice_rotacion_plaza':
          return {
            valor: `${Number(indEjecutivos.rotacion_diaria ?? indEjecutivos.indice_rotacion_plaza ?? 0).toFixed(2).replace('.', ',')}x`,
            subtitulo: 'vehículos / plaza / día',
            icono: RotateCcw,
            color: '#16A34A',
          }
        case 'permanencia_mediana':
        case 'permanencia_promedio_min':
          return {
            valor: `${Number(indEjecutivos.permanencia_mediana_min ?? indEjecutivos.permanencia_promedio_min ?? 0)} min`,
            subtitulo: 'estadía media por vehículo',
            icono: Clock,
            color: '#003865',
          }
        default:
          return { valor: '—', subtitulo: '', icono: Car, color: '#003865' }
      }
    }
  }

  return (
    <div className="min-h-screen bg-uct-bg-main print:bg-white text-slate-800 pb-16 print:pb-0 reporte-imprimible-uct">
      <style>{`
        @media print {
          @page {
            size: landscape;
            margin: 10mm;
          }
          body {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            background: #ffffff !important;
          }
          .no-imprimir-reporte,
          .modebar,
          .modebar-container,
          .reporte-graficos-contenedor button,
          .reporte-graficos-contenedor select {
            display: none !important;
          }
          .tarjeta-grafico-imprimible {
            break-inside: avoid;
            page-break-inside: avoid;
          }
        }
      `}</style>
      {/* Cabecera Institucional UCT idéntica al Dashboard Principal (#003865 + Logo Oficial + Dorado #C59B27) */}
      <header className="bg-uct-blue-primary text-white shadow-xl print:shadow-none sticky print:static top-0 z-40">
        <div className="flex flex-wrap items-center justify-between px-6 py-3 border-b border-white/10 gap-3">
          <div className="flex items-center gap-3">
            <div className="h-9 px-2.5 py-1 rounded-lg bg-white flex items-center justify-center border border-uct-gold/40 shadow-xs">
              <img src="/uct_logo.png" alt="UCT" className="h-7 w-auto object-contain" />
            </div>
            <div>
              <p className="text-xs text-white/70 leading-none">
                Sistema de Apoyo a la Toma de Decisiones (DSS) — Campus San Francisco
              </p>
              <h1 className="text-sm font-bold leading-tight">Universidad Católica de Temuco</h1>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {reporte && (
              <div className="flex items-center gap-1.5 text-xs text-white bg-white/10 px-3 py-1.5 rounded-lg border border-white/15">
                <Calendar size={13} className="text-uct-gold" />
                <span>Período:</span>
                <strong className="text-uct-gold">
                  {reporte.fecha_inicio} al {reporte.fecha_fin}
                </strong>
              </div>
            )}

            <div className="flex items-center gap-1.5 text-xs text-white/80 bg-white/10 px-3 py-1.5 rounded-lg border border-white/10">
              <MapPin size={12} />
              <span>Módulo:</span>
              {reporte ? (
                <span className="text-uct-gold font-semibold">{reporte.espacio_nombre}</span>
              ) : (
                <span>Campus San Francisco</span>
              )}
            </div>

            <button
              type="button"
              onClick={() => setMostrarBandejaHistorica(!mostrarBandejaHistorica)}
              className="no-imprimir-reporte print:hidden px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 border border-white/20 text-xs font-semibold text-white flex items-center gap-1.5 cursor-pointer"
            >
              <History size={13} className="text-uct-gold" />
              <span>Mis Reportes ({historial.length})</span>
            </button>

            {reporte?.permitir_exportacion && (
              <button
                type="button"
                onClick={() => window.print()}
                className="no-imprimir-reporte print:hidden px-3 py-1.5 rounded-lg bg-uct-gold hover:bg-amber-500 text-uct-blue-primary text-xs font-bold flex items-center gap-1.5 cursor-pointer shadow-2xs"
              >
                <Printer size={13} />
                <span>Imprimir / PDF</span>
              </button>
            )}

            {isAuthenticated && (
              <button
                type="button"
                onClick={logout}
                className="no-imprimir-reporte print:hidden px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 border border-rose-400/30 text-rose-100 text-xs font-semibold flex items-center gap-1.5 cursor-pointer"
              >
                <LogOut size={13} />
                <span>Cerrar Sesión</span>
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="p-6 print:p-3 space-y-6 print:space-y-4 max-w-[1600px] mx-auto">
        {/* Tarjeta Institucional Blanca de Identificación del Reporte (oculta datos de destinatario al imprimir, dejando solo filtros) */}
        {destinatario && (
          <section className="bg-white p-5 print:p-3 rounded-2xl border border-slate-200/90 shadow-xs print:shadow-none space-y-4 print:space-y-0">
            <div className="no-imprimir-reporte print:hidden flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[11px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-md bg-uct-blue-primary text-white">
                    {reporte ? reporte.codigo_corto : 'PORTAL CONSULTOR'}
                  </span>
                  <h2 className="text-base sm:text-lg font-bold text-uct-blue-primary">
                    {reporte
                      ? reporte.titulo_reporte
                      : `Bandeja Histórica de Reportes — ${destinatario.nombre_completo}`}
                  </h2>
                </div>
                <p className="text-xs text-slate-600">
                  <strong>Destinatario:</strong> {destinatario.nombre_completo} ({destinatario.email}) |{' '}
                  <strong>Cargo:</strong> {destinatario.cargo} | <strong>Unidad / Carrera:</strong>{' '}
                  {destinatario.unidad_academica}
                </p>
                {reporte && (
                  <p className="text-xs text-slate-500">
                    <strong>Finalidad institucional:</strong> {reporte.finalidad_reporte}
                  </p>
                )}
              </div>

              {reporte && (
                <div className="flex items-center gap-2 bg-slate-50 px-3.5 py-2 rounded-xl border border-slate-200 text-xs text-slate-700">
                  <Lock className="w-4 h-4 text-uct-blue-primary shrink-0" />
                  <div>
                    <div className="font-bold text-uct-blue-primary">Alcance y Filtros Aplicados</div>
                    <div className="text-[11px] text-slate-500">
                      {reporte.modo_datos === 'instantanea_fija'
                        ? 'Instantánea Oficial Congelada'
                        : 'Datos Verificados del Período'}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {reporte && (
              <div className="flex flex-wrap items-center gap-2 pt-3 print:pt-0 border-t print:border-t-0 border-slate-100 text-xs">
                <span className="text-slate-500 font-semibold">Filtros aplicados ({reporte.espacio_nombre} | {reporte.fecha_inicio} al {reporte.fecha_fin}):</span>
                {reporte.espacio_id === 1 ? (
                  <>
                    <span className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-800 border border-slate-200 font-medium">
                      Sala:{' '}
                      <strong>
                        {reporte.filtros_bloqueados?.sala === 'CSF02' || reporte.filtros_bloqueados?.sala === 'sala_1'
                          ? 'Sala 1 (CSF02 - 2° Piso)'
                          : reporte.filtros_bloqueados?.sala === 'CSF04' || reporte.filtros_bloqueados?.sala === 'sala_2'
                          ? 'Sala 2 Pecera (CSF04 - 1° Piso)'
                          : 'Ambas Salas (Sala 1 + Sala 2)'}
                      </strong>
                    </span>
                    <span className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-800 border border-slate-200 font-medium">
                      Facultad: <strong>{reporte.filtros_bloqueados?.facultad || 'Todas las facultades'}</strong>
                    </span>
                    <span className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-800 border border-slate-200 font-medium">
                      Carrera: <strong>{reporte.filtros_bloqueados?.carrera || 'Todas las carreras'}</strong>
                    </span>
                  </>
                ) : (
                  <>
                    <span className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-800 border border-slate-200 font-medium">
                      Sector: <strong>{reporte.filtros_bloqueados?.sector || 'Todos los sectores CSF'}</strong>
                    </span>
                    <span className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-800 border border-slate-200 font-medium">
                      Tipo Vehículo: <strong>{reporte.filtros_bloqueados?.tipo_vehiculo || 'Toda la flota'}</strong>
                    </span>
                  </>
                )}
                <span className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-800 border border-slate-200 font-medium">
                  Régimen Horario:{' '}
                  <strong>
                    {!reporte.filtros_bloqueados?.regimen_horario || reporte.filtros_bloqueados?.regimen_horario === '24h_total'
                      ? 'Todo Horario (24h completo)'
                      : reporte.filtros_bloqueados?.regimen_horario === 'dentro_horario'
                      ? 'En Horario Hábil'
                      : reporte.filtros_bloqueados?.regimen_horario === 'fuera_horario'
                      ? 'Fuera de Horario'
                      : reporte.filtros_bloqueados?.regimen_horario}
                  </strong>
                </span>
                {reporte.filtros_bloqueados?.direccion && (
                  <span className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-800 border border-slate-200 font-medium">
                    Flujo:{' '}
                    <strong>
                      {reporte.filtros_bloqueados.direccion === 'entrar'
                        ? 'Solo Entradas'
                        : reporte.filtros_bloqueados.direccion === 'salir'
                        ? 'Solo Salidas'
                        : reporte.filtros_bloqueados.direccion}
                    </strong>
                  </span>
                )}
                {(reporte.filtros_bloqueados as any)?.tipo_dia && (
                  <span className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-800 border border-slate-200 font-medium">
                    Días:{' '}
                    <strong>
                      {(reporte.filtros_bloqueados as any).tipo_dia === 'habiles'
                        ? 'Lunes a Viernes'
                        : (reporte.filtros_bloqueados as any).tipo_dia === 'fines_semana'
                        ? 'Sábado y Domingo'
                        : (reporte.filtros_bloqueados as any).tipo_dia}
                    </strong>
                  </span>
                )}
              </div>
            )}
          </section>
        )}

        {/* Bandeja Histórica de Reportes Recibidos por el Consultor */}
        {mostrarBandejaHistorica && (
          <section className="no-imprimir-reporte print:hidden bg-white p-5 rounded-2xl border border-slate-200 shadow-xs space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-uct-blue-primary" />
                <h3 className="text-sm font-bold text-uct-blue-primary">
                  Historial de Reportes Ejecutivos Enviados a {destinatario?.nombre_completo}
                </h3>
              </div>
              <span className="text-xs text-slate-500">
                Seleccione un reporte para visualizar sus métricas y gráficos
              </span>
            </div>

            {historial.length === 0 ? (
              <div className="text-center py-8 text-xs text-slate-500">
                Aún no registra reportes ejecutivos activos en su bandeja.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {historial.map((item) => {
                  const seleccionado = item.token_acceso === tokenReporteActivo
                  return (
                    <div
                      key={item.id}
                      className={`p-3.5 rounded-xl border transition-all flex flex-col justify-between gap-2.5 ${
                        seleccionado
                          ? 'bg-blue-50/70 border-uct-blue-primary shadow-xs'
                          : item.vigente
                          ? 'bg-slate-50/70 border-slate-200 hover:border-slate-300'
                          : 'bg-slate-50 border-slate-200 opacity-60'
                      }`}
                    >
                      <div>
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="text-[11px] font-mono font-bold text-uct-blue-primary">
                            {item.codigo_corto}
                          </span>
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                              item.vigente
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                : 'bg-red-50 text-red-700 border border-red-200'
                            }`}
                          >
                            {item.vigente ? 'Disponible' : item.expirado ? 'Expirado' : 'Deshabilitado'}
                          </span>
                        </div>
                        <h4 className="text-xs font-bold text-slate-900">{item.titulo_reporte}</h4>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          {item.espacio_nombre} | Período: {item.fecha_inicio} al {item.fecha_fin}
                        </p>
                      </div>
                      {item.vigente && (
                        <button
                          type="button"
                          onClick={() => cargarReportePorToken(item.token_acceso)}
                          className={`w-full py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
                            seleccionado
                              ? 'bg-uct-blue-primary text-white'
                              : 'bg-white hover:bg-slate-100 text-uct-blue-primary border border-slate-300'
                          }`}
                        >
                          {seleccionado ? 'Reporte Activo en Pantalla' : 'Visualizar este Reporte'}
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </section>
        )}

        {/* Notas y Observaciones del Emisor */}
        {reporte && (reporte.nota_general || obtenerNotasDeSeccion('general').length > 0) && (
          <section className="no-imprimir-reporte print:hidden bg-amber-50/80 p-5 rounded-2xl border border-amber-200 border-l-4 border-l-uct-gold space-y-3 shadow-2xs">
            <div className="flex items-center gap-2 text-uct-blue-primary font-bold text-sm">
              <MessageSquare className="w-4 h-4 text-amber-700" />
              <h3>Notas Ejecutivas y Observaciones del Emisor</h3>
            </div>
            {reporte.nota_general && (
              <p className="text-xs sm:text-sm text-slate-800 leading-relaxed whitespace-pre-line bg-white p-3.5 rounded-xl border border-amber-200/80">
                {reporte.nota_general}
              </p>
            )}
            {obtenerNotasDeSeccion('general').length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                {obtenerNotasDeSeccion('general').map((n) => (
                  <div
                    key={n.id}
                    className="p-3 rounded-xl bg-white border border-amber-200 text-xs space-y-1"
                  >
                    <div className="font-bold text-uct-blue-primary">{n.titulo}</div>
                    <p className="text-slate-700">{n.contenido}</p>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Panel Gerencial de Métricas Clave y Tarjetas de Resumen Global (idénticas al Dashboard Principal) */}
        {reporte && indVisibles.length > 0 && (() => {
          const indicadoresAutorizados = (datosReporte?.catalogos?.indicadores || []).filter((catInd) =>
            indVisibles.includes(catInd.id)
          )
          const bannerItems = indicadoresAutorizados.filter((catInd) => formatearValorIndicador(catInd.id).esBannerGerencial)
          const kpiCardsItems = indicadoresAutorizados.filter((catInd) => !formatearValorIndicador(catInd.id).esBannerGerencial)

          return (
            <section className="space-y-4">
              {bannerItems.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                  {bannerItems.map((catInd) => {
                    const info = formatearValorIndicador(catInd.id)
                    const IconComp = info.icono
                    return (
                      <div
                        key={catInd.id}
                        className="relative overflow-hidden bg-white rounded-xl p-3.5 border border-slate-200/80 shadow-2xs transition-all group"
                      >
                        <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${info.gradienteBarra || 'from-uct-blue-primary to-blue-600'}`} />
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 pr-1">
                            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider truncate">
                              {catInd.titulo}
                            </p>
                            <p
                              className="text-lg sm:text-xl font-black text-slate-900 mt-1 tracking-tight truncate"
                              title={info.valor}
                            >
                              {info.valor}
                            </p>
                          </div>
                          <div
                            className={`w-9 h-9 shrink-0 rounded-lg border flex items-center justify-center ${
                              info.claseIconoBanner || 'bg-blue-50 text-uct-blue-primary border-blue-200/60'
                            }`}
                          >
                            <IconComp size={18} />
                          </div>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-1.5 flex items-center gap-1 font-medium truncate">
                          {info.subtitulo}
                        </p>
                      </div>
                    )
                  })}
                </div>
              )}

              {kpiCardsItems.length > 0 && (
                <div
                  className={`grid grid-cols-1 sm:grid-cols-2 ${
                    reporte.espacio_id === 2 && kpiCardsItems.length > 4
                      ? 'lg:grid-cols-3 xl:grid-cols-6'
                      : 'lg:grid-cols-4'
                  } gap-4`}
                >
                  {kpiCardsItems.map((catInd) => {
                    const info = formatearValorIndicador(catInd.id)
                    return (
                      <KpiCard
                        key={catInd.id}
                        title={catInd.titulo}
                        value={info.valor}
                        subtitle={info.subtitulo}
                        icon={info.icono}
                        iconColor={info.color}
                      />
                    )
                  })}
                </div>
              )}
            </section>
          )
        })()}

        {/* Gráficos Autorizados con ChartCard Institucional idéntica al Dashboard */}
        {reporte && (
          <section className="space-y-4 reporte-graficos-contenedor">
            <div className="flex flex-wrap gap-4 items-start">
              {reporte.espacio_id === 1 && (
                <>
                  {grafVisibles.includes('aforo_curva') && (grafData.aforo_curva || grafData.flujo_horario) && (
                    <div className="w-full space-y-2">
                      <ChartCard
                        layout="full"
                        title={`Curva de Aforo Concurrente vs Capacidad (${reporte.fecha_inicio} al ${reporte.fecha_fin})`}
                      >
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <OccupancyAreaChart
                            data={grafData.aforo_curva || grafData.flujo_horario}
                            capacidad={
                              reporte.filtros_bloqueados?.sala === 'CSF02'
                                ? 93
                                : reporte.filtros_bloqueados?.sala === 'CSF04'
                                ? 120
                                : 213
                            }
                            unit="ocupantes"
                            salaLabel={
                              reporte.filtros_bloqueados?.sala === 'CSF02'
                                ? 'Sala 1 (CSF02)'
                                : reporte.filtros_bloqueados?.sala === 'CSF04'
                                ? 'Sala 2 Pecera (CSF04)'
                                : 'Ambas Salas'
                            }
                            capSala1={93}
                            capSala2={120}
                            comparativaSalas={grafData.comparativa_salas || []}
                          />
                        </Suspense>
                      </ChartCard>
                      {obtenerNotasDeSeccion('aforo_curva').map((n) => (
                        <div
                          key={n.id}
                          className="no-imprimir-reporte print:hidden px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-slate-800"
                        >
                          <strong className="text-uct-blue-primary">Nota del Emisor ({n.titulo}):</strong> {n.contenido}
                        </div>
                      ))}
                    </div>
                  )}

                  {grafVisibles.includes('flujo_horario') && grafData.flujo_horario && (
                    <div className="w-full space-y-2">
                      <ChartCard
                        layout="full"
                        title={`Flujo Horario de Ingresos y Salidas (${reporte.fecha_inicio} al ${reporte.fecha_fin})`}
                      >
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <HourlyBarChart data={grafData.flujo_horario} />
                        </Suspense>
                      </ChartCard>
                      {obtenerNotasDeSeccion('flujo_horario').map((n) => (
                        <div
                          key={n.id}
                          className="no-imprimir-reporte print:hidden px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-slate-800"
                        >
                          <strong className="text-uct-blue-primary">Nota del Emisor ({n.titulo}):</strong> {n.contenido}
                        </div>
                      ))}
                    </div>
                  )}

                  {grafVisibles.includes('comparativa_salas') && grafData.comparativa_salas && (
                    <div className="w-full space-y-2">
                      <ChartCard
                        layout="full"
                        title="Comparativa de Afluencia entre Salas (Sala 1 CSF02 vs Sala 2 Pecera CSF04)"
                      >
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <RoomComparisonPlotlyChart data={grafData.comparativa_salas} />
                        </Suspense>
                      </ChartCard>
                      {obtenerNotasDeSeccion('comparativa_salas').map((n) => (
                        <div
                          key={n.id}
                          className="no-imprimir-reporte print:hidden px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-slate-800"
                        >
                          <strong className="text-uct-blue-primary">Nota del Emisor ({n.titulo}):</strong> {n.contenido}
                        </div>
                      ))}
                    </div>
                  )}

                  {grafVisibles.includes('evolucion_semanal') && grafData.evolucion_semanal && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Evolución Semanal por Semanas ISO">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <WeeklyEvolutionPlotlyChart data={grafData.evolucion_semanal} />
                        </Suspense>
                      </ChartCard>
                      {obtenerNotasDeSeccion('evolucion_semanal').map((n) => (
                        <div
                          key={n.id}
                          className="no-imprimir-reporte print:hidden px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-slate-800"
                        >
                          <strong className="text-uct-blue-primary">Nota del Emisor ({n.titulo}):</strong> {n.contenido}
                        </div>
                      ))}
                    </div>
                  )}

                  {grafVisibles.includes('volumen_mensual') && grafData.volumen_mensual && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Volumen y Promedio Diario Mensual">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <MonthlyVolumePlotlyChart data={grafData.volumen_mensual} />
                        </Suspense>
                      </ChartCard>
                      {obtenerNotasDeSeccion('volumen_mensual').map((n) => (
                        <div
                          key={n.id}
                          className="no-imprimir-reporte print:hidden px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-slate-800"
                        >
                          <strong className="text-uct-blue-primary">Nota del Emisor ({n.titulo}):</strong> {n.contenido}
                        </div>
                      ))}
                    </div>
                  )}

                  {grafVisibles.includes('mapa_calor') && grafData.mapa_calor && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Mapa de Calor — Ocupación por Día y Hora">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <HeatmapChart data={grafData.mapa_calor} />
                        </Suspense>
                      </ChartCard>
                      {obtenerNotasDeSeccion('mapa_calor').map((n) => (
                        <div
                          key={n.id}
                          className="no-imprimir-reporte print:hidden px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-slate-800"
                        >
                          <strong className="text-uct-blue-primary">Nota del Emisor ({n.titulo}):</strong> {n.contenido}
                        </div>
                      ))}
                    </div>
                  )}

                  {grafVisibles.includes('promedio_dia_semana') && grafData.promedio_dia_semana && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Promedio de Ingresos por Día de la Semana">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <DailyAverageAttendancePlotlyChart data={grafData.promedio_dia_semana} />
                        </Suspense>
                      </ChartCard>
                      {obtenerNotasDeSeccion('promedio_dia_semana').map((n) => (
                        <div
                          key={n.id}
                          className="no-imprimir-reporte print:hidden px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-slate-800"
                        >
                          <strong className="text-uct-blue-primary">Nota del Emisor ({n.titulo}):</strong> {n.contenido}
                        </div>
                      ))}
                    </div>
                  )}

                  {grafVisibles.includes('distribucion_curricular') && grafData.distribucion_curricular && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Distribución Curricular por Carrera y Facultad">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <CurricularDistributionPlotlyChart data={grafData.distribucion_curricular} />
                        </Suspense>
                      </ChartCard>
                      {obtenerNotasDeSeccion('distribucion_curricular').map((n) => (
                        <div
                          key={n.id}
                          className="no-imprimir-reporte print:hidden px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-slate-800"
                        >
                          <strong className="text-uct-blue-primary">Nota del Emisor ({n.titulo}):</strong> {n.contenido}
                        </div>
                      ))}
                    </div>
                  )}

                  {grafVisibles.includes('perfiles_visita') && grafData.perfiles_visita && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Perfiles de Visita y Permanencia">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <VisitProfilesPlotlyChart data={grafData.perfiles_visita} />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}

                  {grafVisibles.includes('uso_torniquetes') && grafData.uso_torniquetes && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Uso de Torniquetes y Accesos Universales">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <DoorUsagePlotlyChart data={grafData.uso_torniquetes} />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}

                  {grafVisibles.includes('hitos_academicos') && grafData.hitos_academicos && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Comparativa por Hito del Calendario Académico">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <AcademicMilestonesPlotlyChart data={grafData.hitos_academicos} />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}

                  {grafVisibles.includes('frecuencia_marcajes') && grafData.frecuencia_marcajes && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Distribución de Frecuencia de Marcajes">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <CheckinDistributionPlotlyChart data={grafData.frecuencia_marcajes} />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}

                  {grafVisibles.includes('prophet_diario') && grafData.prophet_diario && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Pronóstico Continuo Prophet (7 Días)">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <ForecastLineChart
                            forecast={grafData.prophet_diario.forecast || []}
                            historico7d={grafData.prophet_diario.historico_7d || []}
                            pronostico7d={grafData.prophet_diario.pronostico_7d || []}
                            capacidad={grafData.prophet_diario.capacidad || 213}
                            salaNombre={
                              reporte.filtros_bloqueados?.sala === 'CSF02'
                                ? 'Sala 1 (CSF02)'
                                : reporte.filtros_bloqueados?.sala === 'CSF04'
                                ? 'Sala 2 Pecera (CSF04)'
                                : 'Biblioteca Campus San Francisco'
                            }
                            recinto="biblioteca"
                          />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}

                  {grafVisibles.includes('campana_24_horas') && grafData.campana_24_horas && (
                    <div className="w-full space-y-3">
                      <div className="p-4 bg-slate-900 text-white rounded-2xl shadow-sm border border-slate-800 flex items-center justify-between">
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <Moon className="w-5 h-5 text-uct-gold" />
                            <h3 className="text-sm font-bold text-white">
                              8. Campaña 24 Horas Exámenes & Análisis de Flujo Nocturno
                            </h3>
                          </div>
                          <p className="text-xs text-slate-300">
                            Monitoreo de demanda fuera de horario habitual (20:30 a 07:00 hrs) y justificación de capacidad en Sala 2 Pecera
                          </p>
                        </div>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-uct-gold border border-uct-gold/40">
                          Régimen Continuo 24h
                        </span>
                      </div>
                      <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                        <SeccionCampana24Horas
                          data={grafData.campana_24_horas}
                          isLoading={false}
                          selectedCampanaId={grafData.campana_24_horas?.campana?.id ?? 0}
                          fechaInicioPersonalizada={reporte.fecha_inicio}
                          fechaFinPersonalizada={reporte.fecha_fin}
                          bloqueHorario="todos"
                          currentDateRange={{
                            inicio: reporte.fecha_inicio,
                            fin: reporte.fecha_fin,
                            label: `Período Reporte (${reporte.fecha_inicio} al ${reporte.fecha_fin})`,
                            isCustom: true,
                          }}
                          ocultarAccionesReporte={true}
                        />
                      </Suspense>
                    </div>
                  )}
                </>
              )}

              {reporte.espacio_id === 2 && (
                <>
                  {grafVisibles.includes('aforo_vehicular_curva') &&
                    (grafData.aforo_vehicular_curva || grafData.flujo_horario_vehicular) && (
                      <div className="w-full space-y-2">
                        <ChartCard
                          layout="full"
                          title={`Curva de Ocupación Vehicular vs Capacidad (${reporte.fecha_inicio} al ${reporte.fecha_fin})`}
                        >
                          <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                            <OccupancyAreaChart
                              data={grafData.aforo_vehicular_curva || grafData.flujo_horario_vehicular}
                              capacidad={indEjecutivos.capacidad_plazas || 125}
                              unit="vehículos"
                              salaLabel={reporte.filtros_bloqueados?.sector || 'Estacionamiento CSF'}
                            />
                          </Suspense>
                        </ChartCard>
                      </div>
                    )}

                  {grafVisibles.includes('flujo_horario_vehicular') && grafData.flujo_horario_vehicular && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Flujo Horario de Ingresos vs Salidas Vehiculares">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <HourlyBarChart data={grafData.flujo_horario_vehicular} />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}

                  {grafVisibles.includes('evolucion_diaria_vehicular') && grafData.evolucion_diaria_vehicular && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Evolución Diaria de Accesos Vehiculares">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <VehicleDailyPlotlyChart data={grafData.evolucion_diaria_vehicular} />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}

                  {grafVisibles.includes('composicion_flota') && grafData.composicion_flota?.por_tipo && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Composición por Tipo de Vehículo">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <FleetDonutChart data={grafData.composicion_flota.por_tipo} nameKey="tipo" />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}

                  {grafVisibles.includes('distribucion_marcas') &&
                    (grafData.distribucion_marcas || grafData.composicion_flota?.por_marca) && (
                      <div className="w-full space-y-2">
                        <ChartCard layout="full" title="Distribución por Marca Vehicular">
                          <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                            <FleetDonutChart
                              data={grafData.distribucion_marcas || grafData.composicion_flota?.por_marca}
                              nameKey="marca"
                            />
                          </Suspense>
                        </ChartCard>
                      </div>
                    )}

                  {grafVisibles.includes('estadisticas_camaras') && grafData.estadisticas_camaras && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Capturas por Cámara ANPR y Calidad">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <CameraStatsPlotlyChart data={grafData.estadisticas_camaras} />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}

                  {grafVisibles.includes('hitos_academicos_vehicular') && grafData.hitos_academicos_vehicular && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Comparativa Vehicular por Hito Académico">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <VehicleMilestonesPlotlyChart data={grafData.hitos_academicos_vehicular} />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}

                  {grafVisibles.includes('movilidad_intercampus') && grafData.movilidad_intercampus && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Movilidad y Traslados Intercampus CSF y CHS">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <IntercampusMobilityPlotlyChart data={grafData.movilidad_intercampus} />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}

                  {grafVisibles.includes('clusters_comportamiento') && grafData.clusters_comportamiento && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Perfiles de Uso Vehicular (Clustering)">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <VehicleBehavioralClustersPlotlyChart data={grafData.clusters_comportamiento} />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}

                  {grafVisibles.includes('prophet_vehicular') && grafData.prophet_vehicular && (
                    <div className="w-full space-y-2">
                      <ChartCard layout="full" title="Pronóstico Continuo Prophet Vehicular (7 Días)">
                        <Suspense fallback={<EsqueletoGraficoInstitucional />}>
                          <ForecastLineChart
                            forecast={grafData.prophet_vehicular.forecast || []}
                            historico7d={grafData.prophet_vehicular.historico_7d || []}
                            pronostico7d={grafData.prophet_vehicular.pronostico_7d || []}
                            capacidad={grafData.prophet_vehicular.capacidad || 125}
                            salaNombre="Estacionamiento Campus San Francisco"
                            recinto="estacionamiento"
                          />
                        </Suspense>
                      </ChartCard>
                    </div>
                  )}
                </>
              )}
            </div>
          </section>
        )}

        {/* Asistente Analítico IA Confinado (SOLO visible si permitir_ia === true y la IA está activa globalmente) */}
        {reporte && reporte.permitir_ia && isAiEnabled && (
          <section className="no-imprimir-reporte print:hidden p-5 rounded-2xl bg-white border border-slate-200 shadow-xs space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
              <div className="flex items-center gap-2 text-uct-blue-primary font-bold text-sm">
                <Sparkles className="w-4 h-4 text-uct-gold" />
                <h3>Asistente Analítico IA (Acotado a este Reporte)</h3>
              </div>
              <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-blue-50 text-uct-blue-primary border border-blue-200 font-semibold">
                Alcance restringido exclusivamente a las cifras de este reporte
              </span>
            </div>

            {conversacionIA.length > 0 && (
              <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                {conversacionIA.map((msg, idx) => (
                  <div key={idx} className="space-y-2 bg-slate-50 p-3.5 rounded-xl border border-slate-200 text-xs">
                    <div className="font-bold text-uct-blue-primary">
                      Consulta ({msg.hora}): <span className="text-slate-800 font-normal">{msg.pregunta}</span>
                    </div>
                    <div className="text-slate-700 leading-relaxed whitespace-pre-line border-t border-slate-200 pt-2">
                      {msg.respuesta}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {errorIA && <div className="text-xs text-red-600">{errorIA}</div>}

            <form onSubmit={handleConsultarIA} className="flex gap-2">
              <input
                type="text"
                placeholder="Pregunte sobre los indicadores, tendencias o notas de este reporte..."
                value={preguntaIA}
                onChange={(e) => setPreguntaIA(e.target.value)}
                disabled={consultandoIA}
                className="flex-1 bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2.5 text-xs text-slate-800"
              />
              <button
                type="submit"
                disabled={consultandoIA || !preguntaIA.trim()}
                className="px-4 py-2.5 rounded-xl bg-uct-blue-primary hover:bg-uct-blue-secondary disabled:opacity-50 text-white text-xs font-bold flex items-center gap-1.5 cursor-pointer"
              >
                <Send className="w-3.5 h-3.5 text-uct-gold" />
                {consultandoIA ? 'Analizando...' : 'Consultar'}
              </button>
            </form>
          </section>
        )}
      </main>
    </div>
  )
}
