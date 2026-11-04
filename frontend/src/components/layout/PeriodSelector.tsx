import React, { useState, useRef, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Calendar,
  ChevronDown,
  Check,
  CalendarRange,
  ArrowRight,
  X,
  Clock,
  AlertCircle,
  Database,
  Layers,
} from 'lucide-react'
import {
  DateRange,
  calculateDaysDifference,
  formatShortDate,
  buildLatestWeekPreset,
} from '../../types/dateRange'
import { fetchDateBounds, fetchHorarios, DateBoundsResponse, HorarioOperacion } from '../../api/client'

interface Props {
  selectedRange: DateRange
  onRangeChange: (r: DateRange) => void
  espacioId?: number
}

export const PeriodSelector: React.FC<Props> = ({ selectedRange, onRangeChange, espacioId }) => {
  const [isOpen, setIsOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<'operativo' | 'meses' | 'personalizado'>('operativo')

  // Consulta dinámica de límites cronológicos y meses disponibles
  const { data: dateBounds } = useQuery<DateBoundsResponse>({
    queryKey: ['date-bounds', espacioId],
    queryFn: () => fetchDateBounds(espacioId),
    staleTime: 5 * 60_000,
  })

  // Consulta dinámica de horarios y períodos operativos configurados
  const { data: horarios = [] } = useQuery<HorarioOperacion[]>({
    queryKey: ['horarios-periodos', espacioId],
    queryFn: () => fetchHorarios({ espacio_id: espacioId }),
    staleTime: 60_000,
  })

  const minDate = dateBounds?.fecha_min || '2026-03-01'
  const maxDate = dateBounds?.fecha_max || '2026-10-31'

  // Fechas locales para el selector personalizado, inicializadas dentro de los límites
  const [customInicio, setCustomInicio] = useState(selectedRange.inicio || minDate)
  const [customFin, setCustomFin] = useState(selectedRange.fin || maxDate)

  const containerRef = useRef<HTMLDivElement>(null)

  // Cerrar al hacer clic fuera
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  // Sincronizar fechas cuando cambia selectedRange externamente o llegan dateBounds
  useEffect(() => {
    if (selectedRange.inicio) {
      const initClamped = selectedRange.inicio < minDate ? minDate : (selectedRange.inicio > maxDate ? maxDate : selectedRange.inicio)
      setCustomInicio(initClamped)
    } else if (dateBounds?.fecha_min) {
      setCustomInicio(dateBounds.fecha_min)
    }

    if (selectedRange.fin) {
      const finClamped = selectedRange.fin > maxDate ? maxDate : (selectedRange.fin < minDate ? minDate : selectedRange.fin)
      setCustomFin(finClamped)
    } else if (dateBounds?.fecha_max) {
      setCustomFin(dateBounds.fecha_max)
    }
  }, [selectedRange, dateBounds, minDate, maxDate])

  const handleSelectPreset = (preset: DateRange) => {
    onRangeChange(preset)
    setIsOpen(false)
  }

  const handleApplyCustom = () => {
    if (!customInicio || !customFin) return
    if (customInicio > customFin) return

    const clampedInicio = customInicio < minDate ? minDate : customInicio
    const clampedFin = customFin > maxDate ? maxDate : customFin

    const label = `Personalizado (${formatShortDate(clampedInicio)} - ${formatShortDate(clampedFin)})`

    onRangeChange({
      label,
      inicio: clampedInicio,
      fin: clampedFin,
      isCustom: true,
    })
    setIsOpen(false)
  }

  const daysSelected = calculateDaysDifference(customInicio, customFin)
  const isOutOfRange = (customInicio && customInicio < minDate) || (customFin && customFin > maxDate)
  const isValidCustomRange =
    customInicio &&
    customFin &&
    customInicio <= customFin &&
    !isOutOfRange

  // Meses dinámicos retornados por la base de datos
  const availableMonths = dateBounds?.meses_disponibles || []

  // Hitos académicos dinámicos actualizados automáticamente con la ingesta de datos
  const hitosAcademicosDinamicos = useMemo(() => {
    const list: DateRange[] = []

    // 1. Última semana registrada calculada dinámicamente según maxDate
    if (maxDate) {
      list.push(buildLatestWeekPreset(maxDate))
    }

    // 2. Últimos 30 días registrados
    if (maxDate) {
      const dMax = new Date(maxDate + 'T00:00:00')
      const d30Ago = new Date(dMax.getTime() - 29 * 24 * 60 * 60 * 1000)
      const iso30Ago = d30Ago.toISOString().substring(0, 10)
      const iniClamped = iso30Ago < minDate ? minDate : iso30Ago
      list.push({
        label: `Últimos 30 días (${formatShortDate(iniClamped)} - ${formatShortDate(maxDate)})`,
        inicio: iniClamped,
        fin: maxDate,
      })
    }

    // 3. Inicio del Semestre / Período Académico
    if (minDate) {
      const dMin = new Date(minDate + 'T00:00:00')
      const d15Post = new Date(dMin.getTime() + 14 * 24 * 60 * 60 * 1000)
      const iso15Post = d15Post.toISOString().substring(0, 10)
      const finClamped = iso15Post > maxDate ? maxDate : iso15Post
      list.push({
        label: `Inicio del Período Académico (${formatShortDate(minDate)} - ${formatShortDate(finClamped)})`,
        inicio: minDate,
        fin: finClamped,
      })
    }

    // 4. Período de Exámenes (si existe en los horarios configurados o rango estándar)
    const horarioExamen = horarios.find(
      (h) => h.activo && (h.descripcion.toLowerCase().includes('examen') || h.tipo_horario === 'extendido_24h')
    )
    if (horarioExamen && horarioExamen.fecha_inicio && horarioExamen.fecha_fin) {
      const ini = horarioExamen.fecha_inicio.substring(0, 10)
      const fi = horarioExamen.fecha_fin.substring(0, 10)
      list.push({
        label: `Semana de Exámenes (${formatShortDate(ini)} - ${formatShortDate(fi)})`,
        inicio: ini,
        fin: fi,
      })
    } else {
      list.push({
        label: 'Semana de Exámenes Semestral (06 Jul 2026 - 13 Jul 2026)',
        inicio: '2026-07-06',
        fin: '2026-07-13',
      })
    }

    // 5. Historial Completo acumulado
    list.push({
      label: `Historial Completo Registrado (${formatShortDate(minDate)} - ${formatShortDate(maxDate)})`,
      inicio: minDate,
      fin: maxDate,
    })

    return list
  }, [minDate, maxDate, horarios])

  return (
    <div className="relative" ref={containerRef}>
      {/* Botón Disparador Principal */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-2.5 px-3 py-1.5 rounded-lg border transition-all text-xs font-medium cursor-pointer ${isOpen
            ? 'bg-white/20 border-uct-gold text-white shadow-xs'
            : 'bg-white/10 hover:bg-white/15 border-white/15 text-white/90 hover:text-white'
          }`}
        title="Cambiar período de análisis y régimen de horario"
      >
        <Calendar size={14} className="text-uct-gold shrink-0" />
        <span className="text-white/60 text-[11px] font-normal">Período:</span>
        <span className="font-semibold text-white max-w-[210px] truncate">
          {selectedRange.label}
        </span>
        <ChevronDown
          size={13}
          className={`text-white/70 transition-transform duration-200 shrink-0 ${isOpen ? 'rotate-180 text-uct-gold' : ''
            }`}
        />
      </button>

      {/* Popover Desplegable */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-[calc(100vw-2rem)] sm:w-[470px] max-w-[470px] bg-slate-900/95 backdrop-blur-xl border border-slate-700/80 rounded-2xl shadow-2xl z-50 text-slate-100 p-4 animate-in fade-in zoom-in-95 duration-150">
          {/* Cabecera del Popover */}
          <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <CalendarRange size={16} className="text-uct-gold" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                Filtro de Período y Modalidad de Horario
              </h3>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-uct-gold/20 text-uct-gold border border-uct-gold/30 font-semibold flex items-center gap-1">
                <Database size={10} />
                <span>Base Dinámica</span>
              </span>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
              >
                <X size={14} />
              </button>
            </div>
          </div>

          {/* Rango Total de Registros en la BD */}
          <div className="mb-3 px-3 py-1.5 rounded-lg bg-slate-800/50 border border-slate-700/50 flex items-center justify-between text-[11px] text-slate-300">
            <span className="text-slate-400">Ventana activa de datos:</span>
            <span className="font-semibold text-uct-gold">
              {formatShortDate(minDate)} — {formatShortDate(maxDate)}
            </span>
          </div>

          {/* Selector de Pestañas: Hitos Académicos vs Meses vs Rango Libre */}
          <div className="flex rounded-lg bg-slate-800/80 p-0.5 mb-3.5 border border-slate-700/50">
            <button
              type="button"
              onClick={() => setActiveTab('operativo')}
              className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-all cursor-pointer flex items-center justify-center gap-1.5 ${activeTab === 'operativo'
                  ? 'bg-uct-blue-primary text-white shadow-xs font-semibold border border-uct-gold/40'
                  : 'text-slate-400 hover:text-white'
                }`}
            >
              <Clock size={13} />
              <span>Hitos Académicos</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('meses')}
              className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-all cursor-pointer flex items-center justify-center gap-1.5 ${activeTab === 'meses'
                  ? 'bg-uct-blue-primary text-white shadow-xs font-semibold border border-uct-gold/40'
                  : 'text-slate-400 hover:text-white'
                }`}
            >
              <Calendar size={13} />
              <span>Meses</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('personalizado')}
              className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-all cursor-pointer flex items-center justify-center gap-1.5 ${activeTab === 'personalizado'
                  ? 'bg-uct-blue-primary text-white shadow-xs font-semibold border border-uct-gold/40'
                  : 'text-slate-400 hover:text-white'
                }`}
            >
              <CalendarRange size={13} />
              <span>Rango Libre</span>
            </button>
          </div>

          {/* Vista 1: Hitos Académicos */}
          {activeTab === 'operativo' && (
            <div className="space-y-3.5 max-h-[300px] overflow-y-auto pr-1">
              <div>
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Layers size={11} className="text-uct-gold" />
                  <span>Hitos Académicos Registrados</span>
                </p>
                <div className="space-y-1">
                  {hitosAcademicosDinamicos.map((p) => {
                    const isSelected = selectedRange.inicio === p.inicio && selectedRange.fin === p.fin
                    return (
                      <button
                        key={p.label}
                        type="button"
                        onClick={() => handleSelectPreset(p)}
                        className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-all text-left cursor-pointer border ${isSelected
                            ? 'bg-uct-blue-primary border-uct-gold text-white font-bold ring-1 ring-uct-gold/50'
                            : 'bg-slate-800/40 hover:bg-slate-800/80 border-slate-700/40 text-slate-300 hover:text-white'
                          }`}
                      >
                        <span className="truncate">{p.label}</span>
                        {isSelected && <Check size={13} className="text-uct-gold shrink-0 ml-1" />}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Vista 2: Meses Predeterminados con Registros */}
          {activeTab === 'meses' && (
            <div className="space-y-3.5">
              <div>
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Calendar size={11} className="text-uct-gold" />
                  <span>Meses con Registros Activos</span>
                </p>
                <div className="grid grid-cols-2 gap-1.5">
                  {availableMonths.map((m) => {
                    const isSelected = selectedRange.label === m.label
                    return (
                      <button
                        key={m.label}
                        type="button"
                        onClick={() => handleSelectPreset(m)}
                        className={`flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-all text-left cursor-pointer border ${isSelected
                            ? 'bg-uct-blue-primary border-uct-gold text-white font-bold ring-1 ring-uct-gold/50'
                            : 'bg-slate-800/60 hover:bg-slate-800 border-slate-700/60 text-slate-200 hover:text-white hover:border-slate-600'
                          }`}
                      >
                        <span className="truncate">{m.label.replace(' 2026', '')}</span>
                        {isSelected && <Check size={13} className="text-uct-gold shrink-0 ml-1" />}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Vista 3: Rango Libre Personalizado */}
          {activeTab === 'personalizado' && (
            <div className="space-y-3.5">
              <p className="text-[11px] text-slate-300">
                Selecciona fechas de inicio y término dentro de los registros disponibles en el sistema:
              </p>

              <div className="grid grid-cols-2 gap-2.5">
                <div className="space-y-1">
                  <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                    Fecha de Inicio
                  </label>
                  <input
                    type="date"
                    value={customInicio}
                    min={minDate}
                    max={maxDate}
                    onChange={(e) => setCustomInicio(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 focus:border-uct-gold text-white rounded-lg px-2.5 py-1.5 text-xs focus:outline-none transition-colors"
                  />
                  <p className="text-[10px] text-slate-500">Mínimo: {minDate}</p>
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                    Fecha de Término
                  </label>
                  <input
                    type="date"
                    value={customFin}
                    min={minDate}
                    max={maxDate}
                    onChange={(e) => setCustomFin(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 focus:border-uct-gold text-white rounded-lg px-2.5 py-1.5 text-xs focus:outline-none transition-colors"
                  />
                  <p className="text-[10px] text-slate-500">Máximo: {maxDate}</p>
                </div>
              </div>

              {customInicio > customFin ? (
                <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
                  <AlertCircle size={14} className="shrink-0 text-rose-400" />
                  <span>La fecha de inicio no puede ser posterior a la de término.</span>
                </div>
              ) : isOutOfRange ? (
                <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-center gap-2">
                  <AlertCircle size={14} className="shrink-0 text-amber-400" />
                  <span>El rango debe estar entre {minDate} y {maxDate}.</span>
                </div>
              ) : (
                <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700/60 text-xs">
                  <span className="text-slate-400">Duración del período:</span>
                  <span className="font-semibold text-uct-gold">
                    {daysSelected} {daysSelected === 1 ? 'día' : 'días'}
                  </span>
                </div>
              )}

              <button
                type="button"
                disabled={!isValidCustomRange}
                onClick={handleApplyCustom}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-uct-blue-primary to-uct-blue-secondary hover:from-uct-blue-secondary hover:to-uct-blue-primary text-white border border-uct-gold/60 font-semibold text-xs shadow-md transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <span>Aplicar Rango al Dashboard</span>
                <ArrowRight size={13} className="text-uct-gold" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
