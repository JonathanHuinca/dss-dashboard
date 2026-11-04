import { BookOpen, Car, MapPin, Sparkles, ShieldCheck, LogOut, FileSpreadsheet } from 'lucide-react'
import { DateRange } from '../../types/dateRange'
import { PeriodSelector } from './PeriodSelector'
import { useAuth } from '../../context/AuthContext'
import { useAssistant } from '../../context/AssistantContext'

export type Tab = 'biblioteca' | 'estacionamiento' | 'admin' | 'reportes'

interface Props {
  active: Tab
  onChange: (t: Tab) => void
  selectedRange: DateRange
  onRangeChange: (r: DateRange) => void
  onOpenAssistant?: () => void
}
export function Header({ active, onChange, selectedRange, onRangeChange, onOpenAssistant }: Props) {
  const { logout, userRole, roles, isSuperAdmin, canAccessAdmin, hasDatasetAccess } = useAuth()
  const { isAiEnabled } = useAssistant()
  const espacioId = active === 'biblioteca' ? 1 : active === 'estacionamiento' ? 2 : undefined
  const tieneRolConsultor = userRole === 'Consultor_Reporte' || (roles || []).includes('Consultor_Reporte')

  return (
    <header className="bg-uct-blue-primary text-white shadow-xl sticky top-0 z-50">
      <div className="flex flex-wrap sm:flex-nowrap items-center justify-between px-3 sm:px-6 py-2.5 sm:py-3 border-b border-white/10 gap-2 sm:gap-3">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <div className="h-8 sm:h-9 px-2 py-1 rounded-lg bg-white flex items-center justify-center border border-uct-gold/40 shadow-xs shrink-0">
            <img src="/uct_logo.png" alt="UCT" className="h-6 sm:h-7 w-auto object-contain" />
          </div>
          <div className="min-w-0">
            <p className="text-[10px] sm:text-xs text-white/60 leading-none truncate">Dashboard Analítico</p>
            <h1 className="text-xs sm:text-sm font-bold leading-tight truncate">Universidad Católica de Temuco</h1>
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <PeriodSelector
            selectedRange={selectedRange}
            onRangeChange={onRangeChange}
            espacioId={espacioId}
          />

          <div className="hidden md:flex items-center gap-1.5 text-xs text-white/70 bg-white/10 px-3 py-1.5 rounded-lg border border-white/10 shrink-0">
            <MapPin size={12} />
            <span className="hidden lg:inline">Campus San Francisco</span>
            <span className="hidden lg:inline text-white/30">›</span>
            <span className="text-uct-gold font-semibold">
              {active === 'biblioteca' ? 'Biblioteca' : active === 'estacionamiento' ? 'Estacionamiento' : active === 'admin' ? 'Administración' : 'Reportes'}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between px-3 sm:px-6 py-2 border-t sm:border-t-0 border-white/5 overflow-x-auto scrollbar-none gap-3">
        <nav className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          {hasDatasetAccess('biblioteca') && (
            <button
              onClick={() => onChange('biblioteca')}
              className={`tab-btn flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm py-1.5 sm:py-2 px-2.5 sm:px-3.5 whitespace-nowrap ${active === 'biblioteca' ? 'tab-btn-active' : 'tab-btn-inactive'}`}
            >
              <BookOpen size={14} className="shrink-0" />
              <span>Biblioteca CSF</span>
            </button>
          )}
          {hasDatasetAccess('estacionamiento') && (
            <button
              onClick={() => onChange('estacionamiento')}
              className={`tab-btn flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm py-1.5 sm:py-2 px-2.5 sm:px-3.5 whitespace-nowrap ${active === 'estacionamiento' ? 'tab-btn-active' : 'tab-btn-inactive'}`}
            >
              <Car size={14} className="shrink-0" />
              <span>Estacionamiento CSF</span>
            </button>
          )}
          {canAccessAdmin && (
            <button
              onClick={() => onChange('admin')}
              className={`tab-btn flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm py-1.5 sm:py-2 px-2.5 sm:px-3.5 whitespace-nowrap ${active === 'admin' ? 'tab-btn-active' : 'tab-btn-inactive'}`}
            >
              <ShieldCheck size={14} className="shrink-0" />
              <span>Administración</span>
            </button>
          )}
          {tieneRolConsultor && (
            <button
              onClick={() => onChange('reportes')}
              className={`tab-btn flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm py-1.5 sm:py-2 px-2.5 sm:px-3.5 whitespace-nowrap ${active === 'reportes' ? 'tab-btn-active' : 'tab-btn-inactive'}`}
            >
              <FileSpreadsheet size={14} className="shrink-0" />
              <span>Reportes</span>
            </button>
          )}
        </nav>

        <div className="flex items-center gap-2 sm:gap-3 shrink-0 ml-auto">
          {onOpenAssistant && isAiEnabled && (
            <button
              onClick={onOpenAssistant}
              title="Abrir Asistente de IA"
              className="flex items-center gap-1.5 sm:gap-2 bg-gradient-to-r from-amber-400 to-amber-500 hover:from-amber-300 hover:to-amber-400 text-slate-950 font-bold px-2.5 sm:px-3.5 py-1.5 rounded-lg border border-amber-200/90 shadow-md hover:shadow-amber-400/25 transition-all text-xs cursor-pointer whitespace-nowrap"
            >
              <Sparkles size={14} className="text-slate-950 shrink-0" />
              <span className="hidden sm:inline">Asistente de IA</span>
              <span className="sm:hidden">IA</span>
            </button>
          )}

          <div className="flex items-center gap-1.5 sm:gap-2 pl-2 sm:pl-3 border-l border-white/20">
            {userRole && (
              <span className="hidden sm:inline-block text-[10px] sm:text-[11px] font-bold bg-white/10 px-2 py-0.5 sm:py-1 rounded-md text-amber-300 border border-white/10 whitespace-nowrap">
                {userRole}
              </span>
            )}
            <button
              onClick={logout}
              title="Cerrar sesión"
              className="flex items-center justify-center bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 hover:text-white p-1.5 sm:p-2 rounded-lg border border-rose-400/30 transition-all cursor-pointer shadow-2xs shrink-0"
            >
              <LogOut size={14} className="sm:w-[15px] sm:h-[15px]" />
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}
