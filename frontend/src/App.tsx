import { useState, useEffect, useCallback, Suspense, lazy } from 'react'
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchAttendanceKpis } from './api/asistencia'
import { fetchVehicleKpis } from './api/vehiculos'
import { Header, Tab } from './components/layout/Header'
import { LoginView } from './components/views/LoginView'
import { ActivateAccountView } from './components/views/ActivateAccountView'
import { ResetPasswordView } from './components/views/ResetPasswordView'
import { AssistantDrawer } from './components/assistant/AssistantDrawer'
import { AuthProvider, useAuth } from './context/AuthContext'
import { AssistantProvider, useAssistant } from './context/AssistantContext'
import { DownloadProgressProvider } from './context/DownloadProgressContext'
import { DownloadProgressModal } from './components/ui/DownloadProgressModal'
import { DateRange, DATE_PRESETS, buildLatestWeekPreset } from './types/dateRange'
import { fetchDateBounds, DateBoundsResponse, DataFilters } from './api/client'
import './index.css'

const BibliotecaView = lazy(() => import('./components/views/BibliotecaView').then(m => ({ default: m.BibliotecaView })))
const EstacionamientoView = lazy(() => import('./components/views/EstacionamientoView').then(m => ({ default: m.EstacionamientoView })))
const AdminDashboard = lazy(() => import('./components/views/AdminDashboard').then(m => ({ default: m.AdminDashboard })))
const ReporteCompartidoView = lazy(() => import('./components/views/ReporteCompartidoView').then(m => ({ default: m.ReporteCompartidoView })))

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

function AppRouter() {
  const queryClient = useQueryClient()
  const { isAuthenticated, userRole, roles, hasDatasetAccess, isSuperAdmin, canAccessAdmin, setCurrentEspacioId } = useAuth()
  const esConsultorReporte = userRole === 'Consultor_Reporte' || (roles || []).includes('Consultor_Reporte')
  const esSoloConsultor = esConsultorReporte && !hasDatasetAccess('biblioteca') && !hasDatasetAccess('estacionamiento') && !canAccessAdmin

  const [tab, setTab] = useState<Tab>(() => {
    if (userRole === 'Consultor_Reporte' && !hasDatasetAccess('biblioteca') && !hasDatasetAccess('estacionamiento') && !canAccessAdmin) {
      return 'reportes'
    }
    return 'biblioteca'
  })
  const currentEspacioId = tab === 'biblioteca' ? 1 : tab === 'estacionamiento' ? 2 : undefined

  const fechaMaxCacheada = obtenerFechaMaxCacheada(currentEspacioId)

  // Consulta dinámica de límites cronológicos y última fecha registrada
  const { data: dateBounds, isError: errorLimitesFechas } = useQuery<DateBoundsResponse>({
    queryKey: ['date-bounds', currentEspacioId],
    queryFn: ({ signal }) => fetchDateBounds(currentEspacioId, signal),
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    enabled: isAuthenticated && currentEspacioId !== undefined,
  })

  const [range, setRange] = useState<DateRange>(() =>
    buildLatestWeekPreset(fechaMaxCacheada || '2026-10-14')
  )
  const [bibliotecaFilters, setBibliotecaFilters] = useState<DataFilters>({
    alcance: 'conformes',
    regimen_horario: 'todos',
    direccion: 'todos',
    dias_semana: '',
    door: '',
    perfil_visita: 'todos',
    marcajes: 'todos',
    incluir_pausas_bano: true,
    desduplicar_rafagas: true,
  })
  const [estacionamientoFilters] = useState<Record<string, any>>({
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
      const dIni = new Date(newRange.inicio + 'T00:00:00')
      const dFin = new Date(newRange.fin + 'T00:00:00')
      const diffDias = Math.round((dFin.getTime() - dIni.getTime()) / 86400000)

      if (diffDias >= 5 && diffDias <= 8) {
        const dIniAnt = new Date(dIni.getTime() - 7 * 86400000)
        const dFinAnt = new Date(dFin.getTime() - 7 * 86400000)
        const isoIniAnt = dIniAnt.toISOString().slice(0, 10)
        const isoFinAnt = dFinAnt.toISOString().slice(0, 10)

        const dIniPost = new Date(dIni.getTime() + 7 * 86400000)
        const dFinPost = new Date(dFin.getTime() + 7 * 86400000)
        const isoIniPost = dIniPost.toISOString().slice(0, 10)
        const isoFinPost = dFinPost.toISOString().slice(0, 10)

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
  const { isOpen, openAssistant, closeAssistant, contextoGrafico } = useAssistant()

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

  // Rutas públicas para activación y recuperación de contraseñas (RF27)
  const isActivarCuenta = typeof window !== 'undefined' && window.location.pathname.startsWith('/activar-cuenta')
  if (isActivarCuenta) {
    return <ActivateAccountView />
  }

  const isRecuperarPassword = typeof window !== 'undefined' && window.location.pathname.startsWith('/recuperar-password')
  if (isRecuperarPassword) {
    return <ResetPasswordView />
  }

  const rutaActual = typeof window !== 'undefined' ? window.location.pathname : ''
  if (rutaActual.startsWith('/reporte-compartido/')) {
    const tokenRep = decodeURIComponent(rutaActual.replace('/reporte-compartido/', '').split('/')[0] || '')
    return <ReporteCompartidoView modoRuta="reporte" token={tokenRep} />
  }
  if (rutaActual.startsWith('/mis-reportes/')) {
    const tokenPortal = decodeURIComponent(rutaActual.replace('/mis-reportes/', '').split('/')[0] || '')
    return <ReporteCompartidoView modoRuta="portal" token={tokenPortal} />
  }

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

  if (!isAuthenticated) {
    return <LoginView />
  }

  if (esSoloConsultor) {
    return <ReporteCompartidoView modoRuta="consultor" />
  }

  return (
    <div className="min-h-screen bg-uct-bg-main relative">
      <Header
        active={tab}
        onChange={setTab}
        selectedRange={range}
        onRangeChange={handleRangeChange}
        onOpenAssistant={() => openAssistant()}
      />
      <main>
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
            {tab === 'biblioteca' && (
              <BibliotecaView
                dateRange={range}
                onRangeChange={handleRangeChange}
                filters={bibliotecaFilters}
                onFiltersChange={setBibliotecaFilters}
              />
            )}
            {tab === 'estacionamiento' && <EstacionamientoView dateRange={range} onRangeChange={handleRangeChange} />}
            {tab === 'admin' && <AdminDashboard />}
          </>
          )}
          </Suspense>
      </main>

      <AssistantDrawer
        isOpen={isOpen}
        onClose={closeAssistant}
        contexto_grafico={contextoGrafico}
        dateRange={range}
        dataset_tipo={tab === 'estacionamiento' ? 'estacionamiento' : 'biblioteca'}
        filtros={filtrosActivos}
      />
    </div>
  )
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
