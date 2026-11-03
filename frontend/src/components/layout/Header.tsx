import { BookOpen, Car, MapPin, Sparkles, ShieldCheck, LogOut } from 'lucide-react'
import { DateRange } from '../../types/dateRange'
import { PeriodSelector } from './PeriodSelector'
import { useAuth } from '../../context/AuthContext'
import { useAssistant } from '../../context/AssistantContext'

export type Tab = 'biblioteca' | 'estacionamiento' | 'admin'

interface Props {
  active: Tab
  onChange: (t: Tab) => void
  selectedRange: DateRange
  onRangeChange: (r: DateRange) => void
  onOpenAssistant?: () => void
}
export function Header({ active, onChange, selectedRange, onRangeChange, onOpenAssistant }: Props) {
  const { logout, userRole, isSuperAdmin, canAccessAdmin, hasDatasetAccess } = useAuth()
  const { isAiEnabled } = useAssistant()
  const espacioId = active === 'biblioteca' ? 1 : active === 'estacionamiento' ? 2 : undefined

  return (
    <header className="bg-uct-blue-primary text-white shadow-xl sticky top-0 z-50">
      <div className="flex items-center justify-between px-6 py-3 border-b border-white/10">
        <div className="flex items-center gap-3">
          <div className="h-9 px-2.5 py-1 rounded-lg bg-white flex items-center justify-center border border-uct-gold/40 shadow-xs">
            <img src="/uct_logo.png" alt="UCT" className="h-7 w-auto object-contain" />
          </div>
          <div>
            <p className="text-xs text-white/60 leading-none">Dashboard Analítico</p>
            <h1 className="text-sm font-bold leading-tight">Universidad Católica de Temuco</h1>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <PeriodSelector
            selectedRange={selectedRange}
            onRangeChange={onRangeChange}
            espacioId={espacioId}
          />

          <div className="flex items-center gap-1.5 text-xs text-white/70 bg-white/10 px-3 py-1.5 rounded-lg border border-white/10">
            <MapPin size={12} />
            <span>Campus San Francisco</span>
            <span className="text-white/30">›</span>
            <span className="text-uct-gold font-semibold">
              {active === 'biblioteca' ? 'Biblioteca' : active === 'estacionamiento' ? 'Estacionamiento' : 'Administración'}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between px-6 py-2.5">
        <div className="flex items-center gap-2">
          {hasDatasetAccess('biblioteca') && (
            <button
              onClick={() => onChange('biblioteca')}
              className={`tab-btn flex items-center gap-2 ${active === 'biblioteca' ? 'tab-btn-active' : 'tab-btn-inactive'}`}
            >
              <BookOpen size={14} />
              Biblioteca CSF
            </button>
          )}
          {hasDatasetAccess('estacionamiento') && (
            <button
              onClick={() => onChange('estacionamiento')}
              className={`tab-btn flex items-center gap-2 ${active === 'estacionamiento' ? 'tab-btn-active' : 'tab-btn-inactive'}`}
            >
              <Car size={14} />
              Estacionamiento CSF
            </button>
          )}
          {canAccessAdmin && (
            <button
              onClick={() => onChange('admin')}
              className={`tab-btn flex items-center gap-2 ${active === 'admin' ? 'tab-btn-active' : 'tab-btn-inactive'}`}
            >
              <ShieldCheck size={14} />
              Panel de Administración
            </button>
          )}
        </div>

        <div className="flex items-center gap-3">
          {onOpenAssistant && isAiEnabled && (
            <button
              onClick={onOpenAssistant}
              title="Abrir Asistente de IA"
              className="flex items-center gap-2 bg-gradient-to-r from-amber-400 to-amber-500 hover:from-amber-300 hover:to-amber-400 text-slate-950 font-bold px-3.5 py-1.5 rounded-lg border border-amber-200/90 shadow-md hover:shadow-amber-400/25 transition-all text-xs cursor-pointer"
            >
              <Sparkles size={15} className="text-slate-950" />
              <span>Asistente de IA</span>
            </button>
          )}

          <div className="flex items-center gap-2 pl-3 border-l border-white/20">
            {userRole && (
              <span className="text-[11px] font-bold bg-white/10 px-2 py-1 rounded-md text-amber-300 border border-white/10">
                {userRole}
              </span>
            )}
            <button
              onClick={logout}
              title="Cerrar sesión"
              className="flex items-center justify-center bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 hover:text-white p-2 rounded-lg border border-rose-400/30 transition-all cursor-pointer shadow-2xs"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}
