import { useState, useEffect, useCallback, Suspense, lazy } from 'react'
import { QueryClient, QueryClientProvider, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { fetchAttendanceKpis } from './api/asistencia'
import { fetchVehicleKpis } from './api/vehiculos'
import { Header, type Tab } from './components/layout/Header'
import { LoginView } from './components/views/LoginView'
import { ActivateAccountView } from './components/views/ActivateAccountView'
import { ResetPasswordView } from './components/views/ResetPasswordView'
import { ErrorBoundary } from './components/ui/ErrorBoundary'
import { AuthProvider, useAuth } from './context/AuthContext'
import { AssistantProvider, useAssistant } from './context/AssistantContext'
import { DownloadProgressProvider } from './context/DownloadProgressContext'
import { DownloadProgressModal } from './components/ui/DownloadProgressModal'
import { type DateRange, buildLatestWeekPreset } from './types/dateRange'
import { fetchDateBounds, type DateBoundsResponse, type DataFilters } from './api/client'
import { buildUserStorageKey } from './utils/userStorage'
import { diferenciaDiasIso, sumarDiasIso } from './utils/fechaChile'
import './index.css'

const BibliotecaView = lazy(() => import('./components/views/BibliotecaView').then(m => ({ default: m.BibliotecaView })))
const EstacionamientoView = lazy(() => import('./components/views/EstacionamientoView').then(m => ({ default: m.EstacionamientoView })))
const AdminDashboard = lazy(() => import('./components/views/AdminDashboard').then(m => ({ default: m.AdminDashboard })))
const ReporteCompartidoView = lazy(() => import('./components/views/ReporteCompartidoView').then(m => ({ default: m.ReporteCompartidoView })))
const AssistantDrawer = lazy(() => import('./components/assistant/AssistantDrawer').then(m => ({ default: m.AssistantDrawer })))

const VistaCargando = () => (
  <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-8">
    <div className="h-32 w-full rounded-2xl bg-slate-100 animate-pulse" />
  </div>
)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

function obtenerFechaMaxCacheada(espacioId?: number): string | null {
  if (typeof window === 'undefined') return null
  try {
    const claveEspacio = `uct_ultima_fecha_max_espacio_${espacioId ?? 1}`
    return localStorage.getItem(claveEspacio) || localStorage.getItem('uct_ultima_fecha_max_espacio_1')
  } catch {
    return null
  }
}

function guardarRangoInicialCache(espacioId: number | undefined, fechaMax: string): void {
  if (typeof window === 'undefined' || !fechaMax) return
  try {
    const idFinal = espacioId ?? 1
    localStorage.setItem(`uct_ultima_fecha_max_espacio_${idFinal}`, fechaMax)
  } catch { }
}

const DEFAULT_BIBLIOTECA_FILTERS: DataFilters = {
  alcance: 'conformes',
  regimen_horario: 'dentro_horario,24h_delta',
  direccion: 'completos',
  dias_semana: '',
  door: '',
  perfil_visita: 'todos',
  marcajes: 'todos',
  sala: '',
  carrera: '',
  facultad: '',
  cohorte: '',
  incluir_pausas_bano: true,
  desduplicar_rafagas: true,
  incluir_funcionarios: true,
  incluir_sin_identificar: true,
}

function AuthenticatedApp() {
  const queryClient = useQueryClient()
  const { userRole, roles, hasDatasetAccess, isSuperAdmin, canAccessAdmin, setCurrentEspacioId } = useAuth()
  const esConsultorReporte = userRole === 'Consultor_Reporte' || (roles || []).includes('Consultor_Reporte')

  const tabInicial: Tab = (() => {
    if (esConsultorReporte && !hasDatasetAccess('biblioteca') && !hasDatasetAccess('estacionamiento') && !canAccessAdmin) {
      return 'reportes'
    }
    if (hasDatasetAccess('biblioteca')) return 'biblioteca'
    if (hasDatasetAccess('estacionamiento')) return 'estacionamiento'
    if (canAccessAdmin) return 'admin'
    return 'biblioteca'
  })()

  const [tab, setTab] = useState<Tab>(tabInicial)

  const currentEspacioId = tab === 'biblioteca' ? 1 : tab === 'estacionamiento' ? 2 : undefined

  const fechaMaxCacheada = obtenerFechaMaxCacheada(currentEspacioId)

  // Consulta dinámica de límites cronológicos y última fecha registrada
  const { data: dateBounds, isError: errorLimitesFechas } = useQuery<DateBoundsResponse>({
    queryKey: ['date-bounds', currentEspacioId],
    queryFn: ({ signal }) => fetchDateBounds(currentEspacioId, signal),
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
    enabled: currentEspacioId !== undefined,
  })

  const [range, setRange] = useState<DateRange>(() =>
    buildLatestWeekPreset(fechaMaxCacheada || '2026-10-14')
  )
  const [lastBibRange, setLastBibRange] = useState<DateRange>(range)
  const [lastEstRange, setLastEstRange] = useState<DateRange>(range)

  useEffect(() => {
    if (tab === 'biblioteca') setLastBibRange(range)
    else if (tab === 'estacionamiento') setLastEstRange(range)
  }, [tab, range])

  const bibliotecaRange = tab === 'biblioteca' ? range : lastBibRange
  const estacionamientoRange = tab === 'estacionamiento' ? range : lastEstRange
  const [bibliotecaFilters, setBibliotecaFilters] = useState<DataFilters>(() => ({ ...DEFAULT_BIBLIOTECA_FILTERS }))
  const [estacionamientoFilters] = useState<DataFilters>({
    calidad: 'conformes',
    tipo_dia: 'todos',
    rango_horario: 'todos',
    sentido: 'todos',
  })

  const filtrosActivos = tab === 'estacionamiento' ? estacionamientoFilters : bibliotecaFilters

  // Prefetching predictivo ante cambio de semana (semana anterior y posterior)
  const handleRangeChange = useCallback((newRange: DateRange) => {
    setRange(newRange)

    if (newRange.inicio && newRange.fin) {
      const diffDias = diferenciaDiasIso(newRange.inicio, newRange.fin)

      if (diffDias >= 5 && diffDias <= 8) {
        const isoIniAnt = sumarDiasIso(newRange.inicio, -7)
        const isoFinAnt = sumarDiasIso(newRange.fin, -7)

        const isoIniPost = sumarDiasIso(newRange.inicio, 7)
        const isoFinPost = sumarDiasIso(newRange.fin, 7)

        const stale = 1000 * 60 * 5
        if (tab === 'biblioteca') {
          queryClient.prefetchQuery({
            queryKey: ['attendance-kpis', isoIniAnt, isoFinAnt, bibliotecaFilters],
            queryFn: ({ signal }) => fetchAttendanceKpis(isoIniAnt, isoFinAnt, bibliotecaFilters, signal),
            staleTime: stale,
          })
          queryClient.prefetchQuery({
            queryKey: ['attendance-kpis', isoIniPost, isoFinPost, bibliotecaFilters],
            queryFn: ({ signal }) => fetchAttendanceKpis(isoIniPost, isoFinPost, bibliotecaFilters, signal),
            staleTime: stale,
          })
        } else if (tab === 'estacionamiento') {
          queryClient.prefetchQuery({
            queryKey: ['vehicle-kpis', isoIniAnt, isoFinAnt, undefined, 'todos'],
            queryFn: ({ signal }) => fetchVehicleKpis(isoIniAnt, isoFinAnt, undefined, 'todos', signal),
            staleTime: stale,
          })
          queryClient.prefetchQuery({
            queryKey: ['vehicle-kpis', isoIniPost, isoFinPost, undefined, 'todos'],
            queryFn: ({ signal }) => fetchVehicleKpis(isoIniPost, isoFinPost, undefined, 'todos', signal),
            staleTime: stale,
          })
        }
      }
    }
  }, [tab, bibliotecaFilters, queryClient])
  const rango_fechas_listo = Boolean(fechaMaxCacheada || dateBounds?.fecha_max || errorLimitesFechas || tab === 'admin')
  const { isOpen, openAssistant, closeAssistant, contextoGrafico, canUseAssistant } = useAssistant()

  // Sincronizar dinámicamente la última semana registrada según nuevos datos o cambio de espacio
  useEffect(() => {
    const fechaEfectiva = dateBounds?.fecha_max || obtenerFechaMaxCacheada(currentEspacioId)
    if (dateBounds?.fecha_max) {
      guardarRangoInicialCache(currentEspacioId, dateBounds.fecha_max)
    }
    if (fechaEfectiva) {
      const isDefaultWeek = !range.isCustom && (!range.inicio || range.label.startsWith('Última semana registrada'))
      const isOutOfSpaceBounds =
        Boolean(dateBounds?.fecha_min && range.inicio && range.inicio < dateBounds.fecha_min) ||
        Boolean(dateBounds?.fecha_max && range.fin && range.fin > dateBounds.fecha_max)

      if ((isDefaultWeek || isOutOfSpaceBounds) && range.fin !== fechaEfectiva) {
        setRange(buildLatestWeekPreset(fechaEfectiva))
      }
    }
  }, [dateBounds?.fecha_max, dateBounds?.fecha_min, currentEspacioId])

  useEffect(() => {
    if (tab === 'biblioteca' && !hasDatasetAccess('biblioteca')) {
      if (hasDatasetAccess('estacionamiento')) {
        setTab('estacionamiento')
      } else if (canAccessAdmin) {
        setTab('admin')
      } else if (esConsultorReporte) {
        setTab('reportes')
      }
    } else if (tab === 'estacionamiento' && !hasDatasetAccess('estacionamiento')) {
      if (hasDatasetAccess('biblioteca')) {
        setTab('biblioteca')
      } else if (canAccessAdmin) {
        setTab('admin')
      } else if (esConsultorReporte) {
        setTab('reportes')
      }
    } else if (tab === 'admin' && !canAccessAdmin) {
      if (hasDatasetAccess('biblioteca')) {
        setTab('biblioteca')
      } else if (hasDatasetAccess('estacionamiento')) {
        setTab('estacionamiento')
      } else if (esConsultorReporte) {
        setTab('reportes')
      }
    }

    // Sincronizar tab con RLS
    if (tab === 'biblioteca') setCurrentEspacioId(1)
    else if (tab === 'estacionamiento') setCurrentEspacioId(2)
  }, [hasDatasetAccess, isSuperAdmin, canAccessAdmin, tab, setCurrentEspacioId, esConsultorReporte])

  return (
    <div className="min-h-screen bg-uct-bg-main relative">
      <Header
        active={tab}
        onChange={setTab}
        selectedRange={range}
        onRangeChange={handleRangeChange}
        onOpenAssistant={canUseAssistant ? () => openAssistant() : undefined}
        filters={filtrosActivos}
      />
      <main>
        <ErrorBoundary titulo="Error al renderizar la vista" descripcion="Se produjo un error inesperado en este módulo. Puedes reintentar cargarlo.">
          <Suspense fallback={<VistaCargando />}>
            {tab === 'reportes' ? (
              <ReporteCompartidoView modoRuta="consultor" />
            ) : !rango_fechas_listo ? (
              <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-8">
                <div className="h-32 w-full rounded-2xl bg-slate-100 animate-pulse mb-6" />
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className="h-96 rounded-2xl bg-slate-100 animate-pulse" />
                  <div className="h-96 rounded-2xl bg-slate-100 animate-pulse" />
                </div>
              </div>
            ) : (
              <>
                {tab === 'biblioteca' && hasDatasetAccess('biblioteca') && (
                  <BibliotecaView
                    dateRange={bibliotecaRange}
                    onRangeChange={handleRangeChange}
                    filters={bibliotecaFilters}
                    onFiltersChange={setBibliotecaFilters}
                  />
                )}
                {tab === 'estacionamiento' && hasDatasetAccess('estacionamiento') && (
                  <EstacionamientoView dateRange={estacionamientoRange} onRangeChange={handleRangeChange} />
                )}
                {tab === 'admin' && canAccessAdmin && (
                  <AdminDashboard />
                )}
              </>
            )}
          </Suspense>
        </ErrorBoundary>
      </main>

      {canUseAssistant && (
        <Suspense fallback={null}>
          <AssistantDrawer
            isOpen={isOpen}
            onClose={closeAssistant}
            contexto_grafico={contextoGrafico}
            dateRange={range}
            dataset_tipo={tab === 'estacionamiento' ? 'estacionamiento' : 'biblioteca'}
            filtros={filtrosActivos}
          />
        </Suspense>
      )}
    </div>
  )
}

function AppRouter() {
  const { isAuthenticated, userId, userEmail, userRole, roles, hasDatasetAccess, canAccessAdmin } = useAuth()
  const esConsultorReporte = userRole === 'Consultor_Reporte' || (roles || []).includes('Consultor_Reporte')
  const esSoloConsultor = esConsultorReporte && !hasDatasetAccess('biblioteca') && !hasDatasetAccess('estacionamiento') && !canAccessAdmin

  // Rutas públicas para activación y recuperación de contraseñas (RF27)
  const rutaActual = typeof window !== 'undefined' ? window.location.pathname : ''
  if (rutaActual.startsWith('/activar-cuenta')) {
    return <ActivateAccountView />
  }
  if (rutaActual.startsWith('/recuperar-password')) {
    return <ResetPasswordView />
  }
  if (rutaActual.startsWith('/reporte-compartido/')) {
    const tokenRep = decodeURIComponent(rutaActual.replace('/reporte-compartido/', '').split('/')[0] || '')
    return <ReporteCompartidoView modoRuta="reporte" token={tokenRep} />
  }
  if (rutaActual.startsWith('/mis-reportes/')) {
    const tokenPortal = decodeURIComponent(rutaActual.replace('/mis-reportes/', '').split('/')[0] || '')
    return <ReporteCompartidoView modoRuta="portal" token={tokenPortal} />
  }

  if (!isAuthenticated) {
    return <LoginView />
  }

  if (esSoloConsultor) {
    return <ReporteCompartidoView modoRuta="consultor" />
  }

  const sessionKey = `${buildUserStorageKey('session', userId, userEmail)}_${userRole || ''}`
  return <AuthenticatedApp key={sessionKey} />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AssistantProvider>
          <DownloadProgressProvider>
            <Suspense fallback={<VistaCargando />}>
              <AppRouter />
            </Suspense>
            <DownloadProgressModal />
          </DownloadProgressProvider>
        </AssistantProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}
