import { BookOpen, Car, MapPin, Calendar, Sparkles, ShieldCheck, LogOut } from 'lucide-react'
import { DateRange, DATE_PRESETS } from '../../types/dateRange'
import { useAuth } from '../../context/AuthContext'

export type Tab = 'biblioteca' | 'estacionamiento' | 'admin'

interface Props {
  active: Tab
  onChange: (t: Tab) => void
  selectedRange: DateRange
  onRangeChange: (r: DateRange) => void
  onOpenAssistant?: () => void
}
export function Header({ active, onChange, selectedRange, onRangeChange, onOpenAssistant }: Props) {
  const { logout, userRole, isSuperAdmin, hasDatasetAccess } = useAuth()

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
          <div className="flex items-center gap-2 bg-white/10 px-3 py-1.5 rounded-lg border border-white/10">
            <Calendar size={14} className="text-uct-gold" />
            <span className="text-xs text-white/70">Período:</span>
            <select
              value={selectedRange.label}
              onChange={(e) => {
                const found = DATE_PRESETS.find(p => p.label === e.target.value)
                if (found) onRangeChange(found)
              }}
              className="bg-transparent text-xs text-white font-medium focus:outline-none cursor-pointer"
            >
              {DATE_PRESETS.map((p) => (
                <option key={p.label} value={p.label} className="bg-uct-blue-primary text-white">
                  {p.label}
                </option>
              ))}
            </select>
          </div>

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
          {isSuperAdmin && (
            <button
              onClick={() => onChange('admin')}
              className={`tab-btn flex items-center gap-2 ${active === 'admin' ? 'tab-btn-active' : 'tab-btn-inactive'}`}
            >
              <ShieldCheck size={14} />
              Panel Admin
            </button>
          )}
        </div>

        <div className="flex items-center gap-3">
          {onOpenAssistant && (
            <button
              onClick={onOpenAssistant}
              className="flex items-center gap-2 bg-gradient-to-r from-amber-500/20 to-uct-gold/30 hover:from-amber-500/30 hover:to-uct-gold/40 text-amber-200 hover:text-white px-3.5 py-1.5 rounded-lg border border-uct-gold/40 transition-all shadow-xs text-xs font-semibold cursor-pointer"
            >
              <Sparkles size={14} className="text-uct-gold animate-pulse" />
              <span>Asistente IA (Gemini)</span>
              <span className="bg-uct-gold text-uct-blue-primary text-[10px] font-bold px-1.5 py-0.2 rounded-full">
                DSS
              </span>
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
              title="Cerrar sesión institucional y volver al portal"
              className="flex items-center gap-1.5 bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 hover:text-white px-3 py-1.5 rounded-lg border border-rose-400/30 transition-all text-xs font-semibold cursor-pointer shadow-2xs"
            >
              <LogOut size={13} />
              <span>Cerrar Sesión</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}
