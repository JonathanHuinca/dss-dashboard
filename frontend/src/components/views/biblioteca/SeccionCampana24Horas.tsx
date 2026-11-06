import React, { useState } from 'react'
import {
  Moon,
  Calendar,
  TrendingUp,
  Users,
  Clock,
  Flame,
  ShieldCheck,
  FileSpreadsheet,
  Layers,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  GraduationCap,
  Building2,
  BarChart3,
  Download,
  Check,
} from 'lucide-react'
import * as XLSX from 'xlsx'
import { Analisis24hResponse } from '../../../api/asistencia'
import { DateRange } from '../../../types/dateRange'
import { HeatmapChart } from '../../charts/HeatmapChart'

interface SeccionCampana24HorasProps {
  data: Analisis24hResponse | null
  isLoading: boolean
  selectedCampanaId?: number
  onSelectCampana?: (id: number) => void
  fechaInicioPersonalizada?: string
  fechaFinPersonalizada?: string
  onChangeFechaPersonalizada?: (inicio: string, fin: string) => void
  bloqueHorario?: 'todos' | 'lunes_jueves' | 'viernes'
  onSelectBloqueHorario?: (bloque: 'todos' | 'lunes_jueves' | 'viernes') => void
  currentDateRange?: DateRange
  onApplyDateRange?: (range: DateRange) => void
  onOpenReporteModal?: () => void
  isRegimenDeltaActive?: boolean
  onToggleRegimenDelta?: () => void
  ocultarAccionesReporte?: boolean
}

function formatFechaCl(isoStr?: string | null): string {
  if (!isoStr) return 'N/A'
  const parts = isoStr.slice(0, 10).split('-')
  if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`
  return isoStr
}

export const SeccionCampana24Horas: React.FC<SeccionCampana24HorasProps> = ({
  data,
  isLoading,
  selectedCampanaId,
  onSelectCampana = () => {},
  fechaInicioPersonalizada,
  fechaFinPersonalizada,
  onChangeFechaPersonalizada,
  bloqueHorario = 'todos',
  onSelectBloqueHorario,
  currentDateRange,
  onApplyDateRange,
  onOpenReporteModal,
  isRegimenDeltaActive = false,
  onToggleRegimenDelta = () => {},
  ocultarAccionesReporte = false,
}) => {
  const [exportando, setExportando] = useState(false)
  const [semanaHeatmap, setSemanaHeatmap] = useState<string>('todas')

  const campanaActual = data?.campana
  const kpis = data?.kpis_comparativa
  const pico = data?.pico_nocturno

  // Verificar si las fechas del dashboard ya coinciden con la campaña seleccionada
  const fIniCampana = campanaActual?.fecha_inicio?.slice(0, 10)
  const fFinCampana = campanaActual?.fecha_fin?.slice(0, 10)
  const fechasSincronizadas =
    fIniCampana &&
    fFinCampana &&
    currentDateRange?.inicio === fIniCampana &&
    currentDateRange?.fin === fFinCampana

  const handleSincronizarFecha = () => {
    if (!fIniCampana || !fFinCampana || !onApplyDateRange) return
    onApplyDateRange({
      inicio: fIniCampana,
      fin: fFinCampana,
      label: campanaActual?.descripcion || `Período 24h: ${formatFechaCl(fIniCampana)} al ${formatFechaCl(fFinCampana)}`,
    })
  }

  const handleExportarExcelDedicado = () => {
    if (!data) return
    setExportando(true)
    try {
      const wb = XLSX.utils.book_new()

      // Hoja 1: Resumen General y Métricas Clave
      const resumenRows = [
        ['REPORTE ESPECIAL DE RENDIMIENTO OPERATIVO — HORARIO 24 HORAS'],
        ['Análisis de Demanda Nocturna Extendida (20:30 a 07:00 hrs) — Sala 2 Pecera (Capacidad: 226 Asientos)'],
        [''],
        ['Métrica', 'Valor'],
        ['Campaña Analizada', campanaActual?.descripcion || 'N/A'],
        ['Vigencia Período', `${formatFechaCl(campanaActual?.fecha_inicio)} al ${formatFechaCl(campanaActual?.fecha_fin)}`],
        ['Capacidad Nominal de Asientos', campanaActual?.capacidad_asientos || 226],
        ['Ingresos Diurnos (08:30 a 20:30 hrs)', kpis?.ingresos_diurnos ?? 0],
        ['Ingresos Nocturnos Extendidos (20:30 a 07:00 hrs)', kpis?.ingresos_nocturnos ?? 0],
        ['Total General de Ingresos', kpis?.total_ingresos ?? 0],
        ['Aporte Nocturno sobre la Demanda (Delta 24h %)', `${kpis?.porcentaje_delta_24h ?? 0}%`],
        ['Estudiantes Nocturnos Únicos Beneficiados', kpis?.estudiantes_nocturnos_unicos ?? 0],
        ['Horas de Estudio Nocturnas Capturadas', `${kpis?.horas_estudio_nocturnas ?? 0} hrs`],
        ['Permanencia Promedio Nocturna', `${kpis?.permanencia_promedio_nocturna_min ?? 0} min`],
        ['Aforo Máximo de Concurrencia Nocturna', `${pico?.aforo_maximo ?? 0} personas`],
        ['Hora Crítica de Concurrencia Simultánea', pico?.hora_pico || 'N/A'],
        ['Tasa de Ocupación Máxima sobre Asientos', `${pico?.tasa_ocupacion_asientos_pct ?? 0}%`],
      ]
      const wsResumen = XLSX.utils.aoa_to_sheet(resumenRows)
      XLSX.utils.book_append_sheet(wb, wsResumen, 'Métricas y Resumen')

      // Hoja 2: Curva Horaria Nocturna
      const curvaRows = [
        ['DISTRIBUCIÓN HORARIA DEL TURNO NOCTURNO Y MADRUGADA (20:00 a 07:00 hrs)'],
        ['Hora', 'Accesos Registrados'],
        ...(data.curva_nocturna || []).map(c => [c.hora, c.ingresos]),
      ]
      const wsCurva = XLSX.utils.aoa_to_sheet(curvaRows)
      XLSX.utils.book_append_sheet(wb, wsCurva, 'Curva Horaria Nocturna')

      // Hoja 3: Fases de la Noche
      const fasesRows = [
        ['AFLUENCIA POR FASES DE NOCHE Y MADRUGADA'],
        ['Fase Horaria', 'Ingresos', 'Porcentaje'],
        ...data.fases_madrugada.map(f => [f.fase, f.ingresos, `${f.porcentaje}%`]),
      ]
      const wsFases = XLSX.utils.aoa_to_sheet(fasesRows)
      XLSX.utils.book_append_sheet(wb, wsFases, 'Fases Madrugada')

      // Hoja 4: Distribución por Días de la Semana
      const diasRows = [
        ['DISTRIBUCIÓN NOCTURNA POR DÍA DE LA SEMANA'],
        ['Día', 'Ingresos Nocturnos', 'Estudiantes Únicos', 'Participación %'],
        ...(data.dias_semana_nocturno || []).map(d => [d.dia, d.ingresos, d.estudiantes, `${d.porcentaje}%`]),
      ]
      const wsDias = XLSX.utils.aoa_to_sheet(diasRows)
      XLSX.utils.book_append_sheet(wb, wsDias, 'Días de la Semana')

      // Hoja 5: Top Carreras y Facultades
      const curricularRows = [
        ['SEGMENTACIÓN CURRICULAR NOCTURNA — TOP CARRERAS'],
        ['Carrera', 'Visitas', 'Estudiantes Únicos', 'Participación %'],
        ...data.top_carreras.map(c => [c.carrera || 'N/A', c.visitas, c.estudiantes, `${c.porcentaje}%`]),
        [''],
        ['SEGMENTACIÓN CURRICULAR NOCTURNA — FACULTADES'],
        ['Facultad', 'Visitas', 'Estudiantes Únicos', 'Participación %'],
        ...data.top_facultades.map(f => [f.facultad || 'N/A', f.visitas, f.estudiantes, `${f.porcentaje}%`]),
      ]
      const wsCurricular = XLSX.utils.aoa_to_sheet(curricularRows)
      XLSX.utils.book_append_sheet(wb, wsCurricular, 'Segmentación Curricular')

      // Hoja 6: Comparativa entre Campañas
      if (data.comparativa_campanas && data.comparativa_campanas.length > 0) {
        const compRows = [
          ['COMPARATIVA HISTÓRICA ENTRE CAMPAÑAS 24 HORAS'],
          ['Campaña', 'Vigencia Inicio', 'Vigencia Fin', 'Ingresos Nocturnos', 'Ingresos Diurnos', 'Total Accesos', 'Delta 24h %', 'Alumnos Únicos', 'Horas de Estudio'],
          ...data.comparativa_campanas.map(c => [
            c.descripcion,
            formatFechaCl(c.fecha_inicio),
            formatFechaCl(c.fecha_fin),
            c.ingresos_nocturnos,
            c.ingresos_diurnos,
            c.total_ingresos,
            `${c.porcentaje_delta_24h}%`,
            c.estudiantes_nocturnos_unicos,
            `${c.horas_estudio_nocturnas} hrs`,
          ]),
        ]
        const wsComp = XLSX.utils.aoa_to_sheet(compRows)
        XLSX.utils.book_append_sheet(wb, wsComp, 'Comparativa de Campañas')
      }

      const filename = `Reporte_Especial_24Horas_${(campanaActual?.descripcion || 'Sala2').replace(/[^a-zA-Z0-9]/g, '_')}.xlsx`
      XLSX.writeFile(wb, filename)
    } finally {
      setExportando(false)
    }
  }

  // Cálculo del valor máximo de la curva horaria para normalizar alturas de barras
  const maxIngresoCurva = Math.max(1, ...(data?.curva_nocturna || []).map(c => c.ingresos))
  const maxIngresoDia = Math.max(1, ...(data?.dias_semana_nocturno || []).map(d => d.ingresos))

  return (
    <div className="space-y-6">
      
      {/* Encabezado Principal de la Sección */}
      <div className="bg-slate-900 text-white p-6 rounded-2xl border border-indigo-900/60 shadow-lg relative overflow-hidden">
        <div className="absolute top-0 right-0 -mr-16 -mt-16 w-56 h-56 bg-indigo-600/15 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5 pb-5 border-b border-indigo-800/40">
          <div className="flex items-start gap-3.5">
            <div className="p-3 rounded-xl bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 shrink-0">
              <Moon className="w-6 h-6 text-indigo-400" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2.5">
                <h2 className="text-lg font-bold text-white tracking-tight">
                  8. Campaña 24 Horas Exámenes & Análisis de Flujo Nocturno
                </h2>
                <span className="text-xs px-2.5 py-0.5 rounded-full font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-400/30">
                  Sala 2 CSF04 Pecera (226 Asientos)
                </span>
              </div>
              <p className="text-xs text-indigo-200/80 mt-1 max-w-3xl leading-relaxed">
                Estudio analítico exclusivo del flujo posterior al horario regular de Sala 2 Pecera (Lunes a Jueves de 23:00 a 07:00 hrs y Viernes de 22:00 a 06:00 hrs).
                Permite examinar períodos individuales (Junio o Noviembre), casos emergentes o el consolidado histórico para justificar técnicamente la dotación de recursos y aforo ante las autoridades.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 shrink-0">
            <button
              type="button"
              onClick={onToggleRegimenDelta}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all shadow-xs cursor-pointer ${
                isRegimenDeltaActive
                  ? 'bg-indigo-500 text-white ring-2 ring-indigo-300'
                  : 'bg-white/10 hover:bg-white/20 text-indigo-100 border border-white/20'
              }`}
              title="Filtrar todas las métricas del panel general para visualizar exclusivamente el turno nocturno"
            >
              <Layers className="w-4 h-4 text-indigo-300" />
              <span>
                {isRegimenDeltaActive ? 'Filtro Activo: Solo Turno Nocturno' : 'Filtrar Dashboard por Turno Nocturno'}
              </span>
            </button>

            <button
              type="button"
              onClick={handleExportarExcelDedicado}
              disabled={exportando || !data}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-all cursor-pointer disabled:opacity-50"
              title="Descargar libro Excel estructurado con todos los gráficos y tablas del turno nocturno"
            >
              <Download className="w-4 h-4" />
              <span>{exportando ? 'Generando Excel...' : 'Descargar Informe Especial (Excel)'}</span>
            </button>

            <button
              type="button"
              onClick={onOpenReporteModal}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition-all cursor-pointer border border-indigo-400/40"
              title="Ver dictamen formal para Vicerrectoría Académica"
            >
              <FileSpreadsheet className="w-4 h-4 text-amber-300" />
              <span>Dictamen Vicerrectoría</span>
            </button>
          </div>
        </div>

        {/* Selector de Período / Caso de Estudio */}
        <div className="pt-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-indigo-200">
            <Calendar className="w-4 h-4 text-indigo-400" />
            <span>Seleccionar Caso o Período a Analizar:</span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {data?.campanas_disponibles.map(c => {
              const isSelected = selectedCampanaId === c.id || (selectedCampanaId === undefined && campanaActual?.id === c.id)
              return (
                <button
                  key={c.id}
                  onClick={() => onSelectCampana(c.id)}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    isSelected
                      ? 'bg-indigo-500 text-white shadow-sm ring-2 ring-indigo-300/60 font-bold'
                      : 'bg-white/10 hover:bg-white/15 text-indigo-100 border border-white/15'
                  }`}
                >
                  {c.descripcion}
                </button>
              )
            })}
          </div>
        </div>

        {/* Filtro de Bloque Nocturno 24 Horas */}
        <div className="pt-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3 border-t border-indigo-800/40">
          <div className="flex items-center gap-2 text-xs font-semibold text-indigo-200">
            <Clock className="w-4 h-4 text-amber-400" />
            <span>Filtro de Bloque Nocturno:</span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => onSelectBloqueHorario?.('todos')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                bloqueHorario === 'todos'
                  ? 'bg-amber-500 text-slate-900 font-bold shadow-xs ring-1 ring-amber-300'
                  : 'bg-white/10 hover:bg-white/15 text-indigo-100 border border-white/15'
              }`}
            >
              Régimen Completo 24h
            </button>
            <button
              type="button"
              onClick={() => onSelectBloqueHorario?.('lunes_jueves')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                bloqueHorario === 'lunes_jueves'
                  ? 'bg-amber-500 text-slate-900 font-bold shadow-xs ring-1 ring-amber-300'
                  : 'bg-white/10 hover:bg-white/15 text-indigo-100 border border-white/15'
              }`}
            >
              Lunes a Jueves (23:00 a 07:00 h)
            </button>
            <button
              type="button"
              onClick={() => onSelectBloqueHorario?.('viernes')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                bloqueHorario === 'viernes'
                  ? 'bg-amber-500 text-slate-900 font-bold shadow-xs ring-1 ring-amber-300'
                  : 'bg-white/10 hover:bg-white/15 text-indigo-100 border border-white/15'
              }`}
            >
              Viernes (22:00 a 06:00 h)
            </button>
          </div>
        </div>

        {/* Subpanel de Rango Personalizado */}
        {(selectedCampanaId === -1 || campanaActual?.id === -1) && (
          <div className="mt-4 pt-3 border-t border-indigo-800/40 bg-indigo-950/40 p-4 rounded-xl border border-indigo-500/30 space-y-3">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-indigo-400 shrink-0" />
                <span className="text-xs font-bold text-indigo-200">
                  Período Personalizado para Análisis Nocturno:
                </span>
                <span className="text-[11px] text-indigo-300/80">
                  {formatFechaCl(fechaInicioPersonalizada)} al {formatFechaCl(fechaFinPersonalizada)}
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (currentDateRange?.inicio && currentDateRange?.fin) {
                      onChangeFechaPersonalizada?.(currentDateRange.inicio, currentDateRange.fin)
                    }
                  }}
                  className="px-2.5 py-1 text-xs rounded-lg bg-indigo-600/40 hover:bg-indigo-600/60 text-indigo-200 border border-indigo-400/30 transition-colors cursor-pointer"
                  title="Cargar fechas activas del selector superior del dashboard"
                >
                  Usar fechas del panel
                </button>
                <button
                  type="button"
                  onClick={() => onChangeFechaPersonalizada?.('2026-06-01', '2026-06-30')}
                  className="px-2.5 py-1 text-xs rounded-lg bg-white/5 hover:bg-white/10 text-indigo-200 border border-white/10 transition-colors cursor-pointer"
                >
                  Mes de Junio 2026
                </button>
                <button
                  type="button"
                  onClick={() => onChangeFechaPersonalizada?.('2026-11-01', '2026-11-30')}
                  className="px-2.5 py-1 text-xs rounded-lg bg-white/5 hover:bg-white/10 text-indigo-200 border border-white/10 transition-colors cursor-pointer"
                >
                  Mes de Noviembre 2026
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-4 text-xs">
              <div className="flex items-center gap-2">
                <label className="text-indigo-200 font-medium">Fecha Inicio:</label>
                <input
                  type="date"
                  value={fechaInicioPersonalizada || ''}
                  onChange={(e) => onChangeFechaPersonalizada?.(e.target.value, fechaFinPersonalizada || '')}
                  className="bg-slate-900 border border-indigo-400/40 rounded-lg px-2.5 py-1 text-white font-mono text-xs focus:ring-1 focus:ring-indigo-400 focus:outline-none"
                />
              </div>

              <div className="flex items-center gap-2">
                <label className="text-indigo-200 font-medium">Fecha Fin:</label>
                <input
                  type="date"
                  value={fechaFinPersonalizada || ''}
                  onChange={(e) => onChangeFechaPersonalizada?.(fechaInicioPersonalizada || '', e.target.value)}
                  className="bg-slate-900 border border-indigo-400/40 rounded-lg px-2.5 py-1 text-white font-mono text-xs focus:ring-1 focus:ring-indigo-400 focus:outline-none"
                />
              </div>

              {fechaInicioPersonalizada && fechaFinPersonalizada && onApplyDateRange && (
                <button
                  type="button"
                  onClick={() => onApplyDateRange({
                    inicio: fechaInicioPersonalizada,
                    fin: fechaFinPersonalizada,
                    label: `Período Personalizado: ${formatFechaCl(fechaInicioPersonalizada)} al ${formatFechaCl(fechaFinPersonalizada)}`,
                  })}
                  className="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-500 hover:bg-amber-600 text-slate-900 font-bold rounded-lg text-xs transition-colors shadow-2xs cursor-pointer"
                  title="Sincronizar estas fechas con el resto de módulos del dashboard"
                >
                  <span>Sincronizar hacia el panel general</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        )}

        {/* Banner de Sincronización de Fechas para Campañas fijas */}
        {fIniCampana && fFinCampana && campanaActual?.id !== 0 && campanaActual?.id !== -1 && selectedCampanaId !== -1 && (
          <div className="mt-4 pt-3 border-t border-indigo-800/30">
            {fechasSincronizadas ? (
              <div className="flex items-center gap-2 text-xs text-emerald-300 bg-emerald-950/40 border border-emerald-500/30 px-3.5 py-2 rounded-xl">
                <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
                <span>
                  <strong>Período sincronizado:</strong> El dashboard está consultando el rango oficial de esta campaña ({formatFechaCl(fIniCampana)} al {formatFechaCl(fFinCampana)}).
                </span>
              </div>
            ) : (
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs bg-amber-950/40 border border-amber-500/30 px-4 py-2.5 rounded-xl text-amber-200">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 text-amber-400" />
                  <span>
                    El rango de fechas actual del panel ({formatFechaCl(currentDateRange?.inicio)} al {formatFechaCl(currentDateRange?.fin)}) difiere del período oficial de esta campaña ({formatFechaCl(fIniCampana)} al {formatFechaCl(fFinCampana)}).
                  </span>
                </div>
                <button
                  type="button"
                  onClick={handleSincronizarFecha}
                  className="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-500 hover:bg-amber-600 text-slate-900 font-bold rounded-lg text-xs shrink-0 transition-colors shadow-2xs"
                >
                  <span>Sincronizar fechas del panel</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {data && data.campana && data.campana.tiene_campana_activa === false && (
        <div className="flex items-center gap-3 p-4 bg-amber-50 border border-amber-300 rounded-xl text-amber-900">
          <AlertCircle className="text-amber-600 shrink-0" size={20} />
          <div>
            <p className="text-sm font-semibold text-amber-800">Período Regular sin Régimen 24 Horas Activo</p>
            <p className="text-xs text-amber-700/90">
              El rango consultado corresponde a horario habitual. Las métricas nocturnas computan en 0. Seleccione &quot;Campaña Junio 2026&quot;, &quot;Campaña Noviembre 2026&quot; o &quot;Consolidado Histórico&quot; para auditar períodos de exámenes 24 Horas.
            </p>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="py-20 text-center text-slate-600 text-sm">
          Cargando análisis exhaustivo de régimen 24 horas...
        </div>
      ) : data ? (
        <>
          {/* Tarjetas KPI de Rendimiento Nocturno */}
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
            <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs">
              <div className="text-[11px] text-slate-500 font-medium">Aporte Nocturno (Delta 24h)</div>
              <div className="text-2xl font-bold text-indigo-600 mt-1">
                {kpis?.porcentaje_delta_24h}%
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">
                {kpis?.ingresos_nocturnos.toLocaleString('es-CL')} de {kpis?.total_ingresos.toLocaleString('es-CL')} accesos
              </div>
            </div>

            <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs">
              <div className="text-[11px] text-slate-500 font-medium">Alumnos Nocturnos</div>
              <div className="text-2xl font-bold text-slate-800 mt-1">
                {kpis?.estudiantes_nocturnos_unicos.toLocaleString('es-CL')}
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5" title="Alumnos únicos con presencia efectiva en la noche: nuevos ingresos nocturnos más alumnos que ingresaron en horario vespertino y permanecieron estudiando después de las 23:00 h">
                {kpis?.estudiantes_remanentes_vespertinos ? (
                  <span>
                    {(kpis.estudiantes_nocturnos_unicos - kpis.estudiantes_remanentes_vespertinos)} nuevos + {kpis.estudiantes_remanentes_vespertinos} remanentes
                  </span>
                ) : (
                  <span>alumnos con presencia nocturna</span>
                )}
              </div>
            </div>

            <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs">
              <div className="text-[11px] text-slate-500 font-medium">Horas de Estudio</div>
              <div className="text-2xl font-bold text-purple-600 mt-1">
                {kpis?.horas_estudio_nocturnas.toLocaleString('es-CL')}
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">
                horas-estudiante capturadas
              </div>
            </div>

            <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs">
              <div className="text-[11px] text-slate-500 font-medium">Máxima Concurrencia</div>
              <div className="text-2xl font-bold text-amber-600 mt-1">
                {pico?.aforo_maximo} <span className="text-xs font-normal text-slate-400">pers.</span>
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">
                {pico?.hora_pico}
              </div>
            </div>

            <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs">
              <div className="text-[11px] text-slate-500 font-medium">Uso Asientos Sala 2</div>
              <div className="text-2xl font-bold text-emerald-600 mt-1">
                {pico?.tasa_ocupacion_asientos_pct}%
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">
                sobre los 226 asientos
              </div>
            </div>

            <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs">
              <div className="text-[11px] text-slate-500 font-medium">Estadía Nocturna</div>
              <div className="text-2xl font-bold text-slate-700 mt-1">
                {kpis?.permanencia_promedio_nocturna_min} <span className="text-xs font-normal text-slate-400">min</span>
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">
                permanencia promedio
              </div>
            </div>
          </div>

          {/* Gráfico 1: Curva Continua de Flujo Nocturno por Hora */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-4 pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-bold text-slate-800">
                  Curva Continua de Afluencia Nocturna (20:00 a 07:00 hrs)
                </h3>
                <p className="text-xs text-slate-500">
                  Distribución secuencial de ingresos registrados a lo largo de las horas de la noche y madrugada
                </p>
              </div>
              <span className="text-xs font-semibold px-2.5 py-1 bg-indigo-50 text-indigo-700 rounded-lg">
                Máximo: {pico?.hora_pico} ({pico?.aforo_maximo} personas)
              </span>
            </div>

            <div className="grid grid-cols-6 sm:grid-cols-12 gap-2 pt-2">
              {(data.curva_nocturna || []).map((c, i) => {
                const alturaPct = Math.round((c.ingresos / maxIngresoCurva) * 100)
                const esPico = c.hora.startsWith(pico?.hora_pico.slice(0, 2) || '99')
                return (
                  <div key={i} className="flex flex-col items-center gap-1.5 group">
                    <span className="text-[11px] font-bold text-slate-700">
                      {c.ingresos}
                    </span>
                    <div className="w-full bg-slate-100 h-32 rounded-lg flex items-end p-1 overflow-hidden">
                      <div
                        className={`w-full rounded-md transition-all duration-300 ${
                          esPico
                            ? 'bg-amber-500'
                            : c.hora_num >= 20 || c.hora_num < 4
                            ? 'bg-indigo-600'
                            : 'bg-purple-500'
                        }`}
                        style={{ height: `${Math.max(6, alturaPct)}%` }}
                        title={`${c.hora}: ${c.ingresos} accesos`}
                      />
                    </div>
                    <span className={`text-[10px] font-mono ${esPico ? 'font-bold text-amber-600' : 'text-slate-500'}`}>
                      {c.hora}
                    </span>
                  </div>
                )
              })}
            </div>
            <div className="flex items-center justify-between text-[11px] text-slate-400 mt-4 pt-2 border-t border-slate-100">
              <span>← Apertura 24h Viernes (22:00) / Lun-Jue (23:00)</span>
              <span>Madrugada Profunda (00:00 a 04:00 hrs)</span>
              <span>Cierre de Jornada (06:00 / 07:00 hrs) →</span>
            </div>
          </div>

          {/* Gráfico Heatmap: Mapa de Calor — Ocupación por Día y Hora por Semanas */}
          {data.mapa_calor && (
            <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs space-y-4">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-100">
                <div className="flex items-center gap-2.5">
                  <div className="p-2.5 rounded-xl bg-indigo-50 text-indigo-600 border border-indigo-100">
                    <Flame className="w-5 h-5 text-amber-500" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-800">
                      Mapa de Calor — Ocupación por Día y Hora
                    </h3>
                    <p className="text-xs text-slate-500">
                      Ocupación continua de Lunes a Domingo (00:00 a 23:00 hrs) con desglose por semanas de la campaña
                    </p>
                  </div>
                </div>

                {/* Filtro por Semanas */}
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-xs font-semibold text-slate-500 mr-1 flex items-center gap-1">
                    <Calendar className="w-3.5 h-3.5 text-indigo-500" />
                    Semana:
                  </span>
                  {(data.mapa_calor.semanas_disponibles || []).map((sem) => {
                    const isSelected = semanaHeatmap === sem.id
                    return (
                      <button
                        key={sem.id}
                        type="button"
                        onClick={() => setSemanaHeatmap(sem.id)}
                        className={`px-2.5 py-1 text-xs rounded-lg transition-all font-medium cursor-pointer ${
                          isSelected
                            ? 'bg-indigo-600 text-white font-bold shadow-xs ring-1 ring-indigo-400'
                            : 'bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200/70'
                        }`}
                      >
                        {sem.label}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Visualización Heatmap */}
              <div className="w-full">
                <HeatmapChart
                  data={data.mapa_calor.matriz_por_semana[semanaHeatmap] || data.mapa_calor.matriz_por_semana['todas'] || []}
                  modoInicial="nocturno"
                  permitirModoNocturno={true}
                />
              </div>

              <div className="flex flex-wrap items-center justify-between text-[11px] text-slate-500 pt-2 border-t border-slate-100 gap-2">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-indigo-600" />
                  Horario Nocturno 24h Pecera: <strong>Lunes a Jueves (23:00 a 07:00 h)</strong> | <strong>Viernes (22:00 a 06:00 h)</strong>
                </span>
                <span className="text-slate-400 font-mono text-[10px]">
                  Filtro activo: {data.mapa_calor.semanas_disponibles.find(s => s.id === semanaHeatmap)?.label || 'Todas las semanas'}
                </span>
              </div>
            </div>
          )}

          {/* Gráfico 2 y Gráfico 3: Fases de la Noche y Distribución por Día de la Semana */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            
            {/* Fases de Madrugada */}
            <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs">
              <div className="mb-4 pb-3 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-800">
                  Comportamiento por Fases de la Noche
                </h3>
                <p className="text-xs text-slate-500">
                  Desglose temporal entre tarde-noche, madrugada profunda y transición de cierre
                </p>
              </div>

              <div className="space-y-4">
                {data.fases_madrugada.map((f, i) => (
                  <div key={i} className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/70">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-bold text-slate-700">{f.fase}</span>
                      <span className="text-xs font-bold text-indigo-600">{f.porcentaje}%</span>
                    </div>
                    <div className="w-full bg-slate-200 h-2.5 rounded-full overflow-hidden mb-1.5">
                      <div
                        className="bg-indigo-600 h-2.5 rounded-full"
                        style={{ width: `${Math.min(100, f.porcentaje)}%` }}
                      />
                    </div>
                    <div className="text-[11px] text-slate-500 text-right">
                      {f.ingresos.toLocaleString('es-CL')} accesos registrados
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Días de la Semana Nocturnos */}
            <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs">
              <div className="mb-4 pb-3 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-800">
                  Distribución Nocturna por Día de la Semana
                </h3>
                <p className="text-xs text-slate-500">
                  Volumen de ingresos nocturnos según el día en que se realizó el estudio
                </p>
              </div>

              <div className="space-y-2.5">
                {(data.dias_semana_nocturno || []).map((d, i) => {
                  const barPct = Math.round((d.ingresos / maxIngresoDia) * 100)
                  return (
                    <div key={i} className="flex items-center gap-3 text-xs">
                      <span className="w-20 font-medium text-slate-700 truncate">{d.dia}</span>
                      <div className="flex-1 bg-slate-100 h-3 rounded-full overflow-hidden">
                        <div
                          className="bg-purple-600 h-3 rounded-full"
                          style={{ width: `${Math.max(4, barPct)}%` }}
                        />
                      </div>
                      <span className="w-16 text-right font-semibold text-slate-800">{d.ingresos}</span>
                      <span className="w-12 text-right font-mono text-[11px] text-purple-700">{d.porcentaje}%</span>
                    </div>
                  )
                })}
              </div>
            </div>

          </div>

          {/* Gráfico 4: Segmentación Curricular Nocturna */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Top Carreras */}
            <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs">
              <div className="flex items-center gap-2 mb-3 pb-2.5 border-b border-slate-100">
                <GraduationCap className="w-4 h-4 text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-800">
                  Top Carreras en Horario Nocturno
                </h3>
              </div>
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {data.top_carreras.map((c, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between text-xs p-2.5 rounded-lg bg-slate-50 border border-slate-100"
                  >
                    <div className="truncate max-w-[240px] font-medium text-slate-700" title={c.carrera}>
                      <span className="text-[10px] text-slate-400 mr-1.5 font-bold">#{i + 1}</span>
                      {c.carrera}
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="font-semibold text-slate-800">{c.visitas} vis.</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-100 text-indigo-700 font-mono">
                        {c.porcentaje}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Top Facultades */}
            <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs">
              <div className="flex items-center gap-2 mb-3 pb-2.5 border-b border-slate-100">
                <Building2 className="w-4 h-4 text-purple-600" />
                <h3 className="text-sm font-bold text-slate-800">
                  Distribución por Facultad en Horario Nocturno
                </h3>
              </div>
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {data.top_facultades.map((f, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between text-xs p-2.5 rounded-lg bg-slate-50 border border-slate-100"
                  >
                    <div className="truncate max-w-[240px] font-medium text-slate-700" title={f.facultad}>
                      <span className="text-[10px] text-slate-400 mr-1.5 font-bold">#{i + 1}</span>
                      {f.facultad}
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="font-semibold text-slate-800">{f.visitas} vis.</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-100 text-purple-700 font-mono">
                        {f.porcentaje}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Gráfico 5: Tabla Comparativa entre Períodos / Campañas */}
          {data.comparativa_campanas && data.comparativa_campanas.length > 0 && (
            <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs">
              <div className="flex items-center justify-between gap-2 mb-3 pb-2.5 border-b border-slate-100">
                <div>
                  <h3 className="text-sm font-bold text-slate-800">
                    Comparativa Multicampaña (Casos Históricos vs Campañas Nuevas)
                  </h3>
                  <p className="text-xs text-slate-500">
                    Evolución cuantitativa entre semestres para justificar la continuidad del servicio
                  </p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-3">Campaña / Período</th>
                      <th className="py-2.5 px-3">Vigencia</th>
                      <th className="py-2.5 px-3 text-right">Ingresos Nocturnos</th>
                      <th className="py-2.5 px-3 text-right">Ingresos Diurnos</th>
                      <th className="py-2.5 px-3 text-right">Total Accesos</th>
                      <th className="py-2.5 px-3 text-right">Aporte Delta 24h</th>
                      <th className="py-2.5 px-3 text-right">Alumnos Únicos</th>
                      <th className="py-2.5 px-3 text-right">Horas Nocturnas</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {data.comparativa_campanas.map((c) => (
                      <tr key={c.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-2.5 px-3 font-semibold text-slate-800">{c.descripcion}</td>
                        <td className="py-2.5 px-3 font-mono text-[11px] text-slate-500">
                          {formatFechaCl(c.fecha_inicio)} al {formatFechaCl(c.fecha_fin)}
                        </td>
                        <td className="py-2.5 px-3 text-right font-bold text-indigo-600">
                          {c.ingresos_nocturnos.toLocaleString('es-CL')}
                        </td>
                        <td className="py-2.5 px-3 text-right text-slate-500">
                          {c.ingresos_diurnos.toLocaleString('es-CL')}
                        </td>
                        <td className="py-2.5 px-3 text-right font-medium">
                          {c.total_ingresos.toLocaleString('es-CL')}
                        </td>
                        <td className="py-2.5 px-3 text-right font-bold text-indigo-700 font-mono">
                          {c.porcentaje_delta_24h}%
                        </td>
                        <td className="py-2.5 px-3 text-right text-slate-800">
                          {c.estudiantes_nocturnos_unicos.toLocaleString('es-CL')}
                        </td>
                        <td className="py-2.5 px-3 text-right font-semibold text-purple-700">
                          {c.horas_estudio_nocturnas.toLocaleString('es-CL')} hrs
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        </>
      ) : null}

    </div>
  )
}

