import { useState, useEffect } from 'react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { Header, Tab } from './components/layout/Header'
import { KPIBanner } from './components/layout/KPIBanner'
import { BibliotecaView } from './components/views/BibliotecaView'
import { EstacionamientoView } from './components/views/EstacionamientoView'
import { AdminDashboard } from './components/views/AdminDashboard'
import { LoginView } from './components/views/LoginView'
import { ActivateAccountView } from './components/views/ActivateAccountView'
import { ResetPasswordView } from './components/views/ResetPasswordView'
import { ReporteCompartidoView } from './components/views/ReporteCompartidoView'
import { AssistantDrawer } from './components/assistant/AssistantDrawer'
import { AuthProvider, useAuth } from './context/AuthContext'
import { AssistantProvider, useAssistant } from './context/AssistantContext'
import { DownloadProgressProvider } from './context/DownloadProgressContext'
import { DownloadProgressModal } from './components/ui/DownloadProgressModal'
import { DateRange, DATE_PRESETS, buildLatestWeekPreset } from './types/dateRange'
import { fetchDateBounds, DateBoundsResponse } from './api/client'
import './index.css'

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
  const { isAuthenticated, userRole, roles, hasDatasetAccess, isSuperAdmin, canAccessAdmin, setCurrentEspacioId } = useAuth()
  const [tab, setTab] = useState<Tab>('biblioteca')
  const esConsultorReporte = userRole === 'Consultor_Reporte' || (roles || []).includes('Consultor_Reporte')
  const currentEspacioId = tab === 'biblioteca' ? 1 : tab === 'estacionamiento' ? 2 : undefined

  const fechaMaxCacheada = obtenerFechaMaxCacheada(currentEspacioId)

  // Consulta dinámica de límites cronológicos y última fecha registrada
  const { data: dateBounds, isError: errorLimitesFechas } = useQuery<DateBoundsResponse>({
    queryKey: ['date-bounds', currentEspacioId],
    queryFn: () => fetchDateBounds(currentEspacioId),
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    enabled: isAuthenticated && currentEspacioId !== undefined,
  })

  const [range, setRange] = useState<DateRange>(() =>
    buildLatestWeekPreset(fechaMaxCacheada || '2026-10-14')
  )
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
      }
    } else if (tab === 'estacionamiento' && !hasDatasetAccess('estacionamiento')) {
      if (hasDatasetAccess('biblioteca')) {
        setTab('biblioteca')
      } else if (canAccessAdmin) {
        setTab('admin')
      }
    } else if (tab === 'admin' && !canAccessAdmin) {
      if (hasDatasetAccess('biblioteca')) {
        setTab('biblioteca')
      } else if (hasDatasetAccess('estacionamiento')) {
        setTab('estacionamiento')
      }
    }
    
    // Sincronizar tab con RLS
    if (tab === 'biblioteca') setCurrentEspacioId(1)
    else if (tab === 'estacionamiento') setCurrentEspacioId(2)
  }, [hasDatasetAccess, isSuperAdmin, canAccessAdmin, tab, setCurrentEspacioId])

  if (!isAuthenticated) {
    return <LoginView />
  }

  if (esConsultorReporte) {
    return <ReporteCompartidoView modoRuta="consultor" />
  }

  return (
    <div className="min-h-screen bg-uct-bg-main relative">
      <Header
        active={tab}
        onChange={setTab}
        selectedRange={range}
        onRangeChange={setRange}
        onOpenAssistant={() => openAssistant()}
      />
      {tab !== 'admin' && rango_fechas_listo && (
        <KPIBanner espacioId={tab === 'biblioteca' ? 1 : 2} selectedRange={range} />
      )}
      <main>
        {!rango_fechas_listo ? (
          <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-8">
            <div className="h-32 w-full rounded-2xl bg-slate-100 animate-pulse mb-6" />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="h-96 rounded-2xl bg-slate-100 animate-pulse" />
              <div className="h-96 rounded-2xl bg-slate-100 animate-pulse" />
            </div>
          </div>
        ) : (
          <>
            {tab === 'biblioteca' && <BibliotecaView dateRange={range} onRangeChange={setRange} />}
            {tab === 'estacionamiento' && <EstacionamientoView dateRange={range} onRangeChange={setRange} />}
            {tab === 'admin' && <AdminDashboard />}
          </>
        )}
      </main>

      <AssistantDrawer
        isOpen={isOpen}
        onClose={closeAssistant}
        contexto_grafico={contextoGrafico}
        dateRange={range}
        dataset_tipo={tab === 'estacionamiento' ? 'estacionamiento' : 'biblioteca'}
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
            <AppRouter />
            <DownloadProgressModal />
          </DownloadProgressProvider>
        </AssistantProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}
