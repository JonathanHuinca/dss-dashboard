import { useState, useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Header, Tab } from './components/layout/Header'
import { KPIBanner } from './components/layout/KPIBanner'
import { BibliotecaView } from './components/views/BibliotecaView'
import { EstacionamientoView } from './components/views/EstacionamientoView'
import { AdminDashboard } from './components/views/AdminDashboard'
import { LoginView } from './components/views/LoginView'
import { AssistantDrawer } from './components/assistant/AssistantDrawer'
import { AuthProvider, useAuth } from './context/AuthContext'
import { AssistantProvider, useAssistant } from './context/AssistantContext'
import { Sparkles } from 'lucide-react'
import { DateRange, DATE_PRESETS } from './types/dateRange'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

function AppRouter() {
  const { isAuthenticated, hasDatasetAccess, isSuperAdmin } = useAuth()
  const [tab, setTab] = useState<Tab>('biblioteca')
  const [range, setRange] = useState<DateRange>(DATE_PRESETS[0])
  const { isOpen, openAssistant, closeAssistant, contextoGrafico } = useAssistant()

  useEffect(() => {
    if (tab === 'biblioteca' && !hasDatasetAccess('biblioteca')) {
      if (hasDatasetAccess('estacionamiento')) {
        setTab('estacionamiento')
      } else if (isSuperAdmin) {
        setTab('admin')
      }
    } else if (tab === 'estacionamiento' && !hasDatasetAccess('estacionamiento')) {
      if (hasDatasetAccess('biblioteca')) {
        setTab('biblioteca')
      } else if (isSuperAdmin) {
        setTab('admin')
      }
    } else if (tab === 'admin' && !isSuperAdmin) {
      if (hasDatasetAccess('biblioteca')) {
        setTab('biblioteca')
      } else if (hasDatasetAccess('estacionamiento')) {
        setTab('estacionamiento')
      }
    }
  }, [hasDatasetAccess, isSuperAdmin, tab])

  if (!isAuthenticated) {
    return <LoginView />
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
      {tab !== 'admin' && (
        <KPIBanner espacioId={tab === 'biblioteca' ? 1 : 2} selectedRange={range} />
      )}
      <main>
        {tab === 'biblioteca' && <BibliotecaView dateRange={range} />}
        {tab === 'estacionamiento' && <EstacionamientoView dateRange={range} />}
        {tab === 'admin' && <AdminDashboard />}
      </main>

      <button
        onClick={() => openAssistant()}
        title="Abrir Asistente IA Gemini"
        className="fixed bottom-6 right-6 z-40 bg-gradient-to-r from-uct-blue-primary to-uct-blue-secondary text-white px-4 py-3 rounded-full shadow-xl hover:shadow-2xl hover:scale-105 transition-all border border-uct-gold/40 flex items-center gap-2.5 cursor-pointer group"
      >
        <Sparkles size={18} className="text-uct-gold group-hover:rotate-12 transition-transform" />
        <span className="text-xs font-bold tracking-wide">Asistente Gemini</span>
      </button>

      <AssistantDrawer
        isOpen={isOpen}
        onClose={closeAssistant}
        contexto_grafico={contextoGrafico}
      />
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AssistantProvider>
          <AppRouter />
        </AssistantProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}
