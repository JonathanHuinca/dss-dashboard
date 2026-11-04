import React, { useState } from 'react'
import {
  X,
  FileSpreadsheet,
  TrendingUp,
  Users,
  Clock,
  ShieldCheck,
  Building2,
  GraduationCap,
  Download,
  Moon,
  Sun,
  Activity,
  Layers,
  Flame,
} from 'lucide-react'
import * as XLSX from 'xlsx'
import { Analisis24hResponse } from '../../api/asistencia'

interface ModalReporte24HorasProps {
  isOpen: boolean
  onClose: () => void
  data: Analisis24hResponse | null
  loading: boolean
  selectedCampanaId?: number
  onSelectCampana: (id: number) => void
}

export const ModalReporte24Horas: React.FC<ModalReporte24HorasProps> = ({
  isOpen,
  onClose,
  data,
  loading,
  selectedCampanaId,
  onSelectCampana,
}) => {
  const [exportando, setExportando] = useState(false)

  if (!isOpen) return null

  const handleExportExcel = () => {
    if (!data) return
    setExportando(true)
    try {
      const wb = XLSX.utils.book_new()

      // Hoja 1: Resumen Ejecutivo
      const resumenRows = [
        ['INFORME EJECUTIVO DE JUSTIFICACIÓN OPERATIVA — RÉGIMEN 24 HORAS'],
        ['Vicerrectoría Académica / Dirección de Biblioteca — Universidad Católica de Temuco'],
        [''],
        ['Parámetro', 'Valor Registrado'],
        ['Campaña Evaluada', data.campana.descripcion],
        ['Recinto / Sala', data.campana.subespacio_label],
        ['Capacidad Nominal de Asientos', data.campana.capacidad_asientos],
        ['Fecha Inicio Campaña', data.campana.fecha_inicio || 'N/A'],
        ['Fecha Término Campaña', data.campana.fecha_fin || 'N/A'],
        [''],
        ['MÉTRICAS COMPARATIVAS DELTA 24 HORAS', ''],
        ['Ingresos Diurnos (08:30 a 20:30 hrs)', data.kpis_comparativa.ingresos_diurnos],
        ['Ingresos Nocturnos Extendidos (20:30 a 07:00 hrs)', data.kpis_comparativa.ingresos_nocturnos],
        ['Total General de Ingresos', data.kpis_comparativa.total_ingresos],
        ['Aporte Nocturno sobre la Demanda (Delta 24h %)', `${data.kpis_comparativa.porcentaje_delta_24h}%`],
        ['Estudiantes Nocturnos Únicos Beneficiados', data.kpis_comparativa.estudiantes_nocturnos_unicos],
        ['Estudiantes Totales Únicos en el Período', data.kpis_comparativa.estudiantes_totales_unicos],
        ['Horas de Estudio Nocturnas Capturadas', `${data.kpis_comparativa.horas_estudio_nocturnas} hrs`],
        ['Permanencia Promedio Nocturna', `${data.kpis_comparativa.permanencia_promedio_nocturna_min} min`],
        ['Máxima Concurrencia Nocturna Simultánea', `${data.pico_nocturno.aforo_maximo} personas`],
        ['Hora Crítica de Concurrencia Nocturna', data.pico_nocturno.hora_pico],
        ['Tasa de Ocupación Máxima sobre Asientos (226)', `${data.pico_nocturno.tasa_ocupacion_asientos_pct}%`],
      ]
      const wsResumen = XLSX.utils.aoa_to_sheet(resumenRows)
      XLSX.utils.book_append_sheet(wb, wsResumen, 'Resumen Ejecutivo')

      // Hoja 2: Fases Madrugada
      const fasesRows = [
        ['DESGLOSE DE AFLUENCIA POR FASES DE NOCHE Y MADRUGADA'],
        ['Fase Horaria', 'Ingresos Registrados', 'Distribución %'],
        ...data.fases_madrugada.map(f => [f.fase, f.ingresos, `${f.porcentaje}%`]),
      ]
      const wsFases = XLSX.utils.aoa_to_sheet(fasesRows)
      XLSX.utils.book_append_sheet(wb, wsFases, 'Fases Madrugada')

      // Hoja 3: Segmentación Curricular Carreras
      const carrerasRows = [
        ['SEGMENTACIÓN CURRICULAR NOCTURNA — TOP CARRERAS'],
        ['Carrera', 'Visitas Nocturnas', 'Estudiantes Únicos', 'Participación %'],
        ...data.top_carreras.map(c => [c.carrera || 'N/A', c.visitas, c.estudiantes, `${c.porcentaje}%`]),
      ]
      const wsCarreras = XLSX.utils.aoa_to_sheet(carrerasRows)
      XLSX.utils.book_append_sheet(wb, wsCarreras, 'Top Carreras Nocturnas')

      // Hoja 4: Segmentación Curricular Facultades
      const facultadesRows = [
        ['SEGMENTACIÓN CURRICULAR NOCTURNA — FACULTADES'],
        ['Facultad', 'Visitas Nocturnas', 'Estudiantes Únicos', 'Participación %'],
        ...data.top_facultades.map(f => [f.facultad || 'N/A', f.visitas, f.estudiantes, `${f.porcentaje}%`]),
      ]
      const wsFacultades = XLSX.utils.aoa_to_sheet(facultadesRows)
      XLSX.utils.book_append_sheet(wb, wsFacultades, 'Facultades Nocturnas')

      const filename = `Justificacion_Operativa_24Horas_${(data.campana.descripcion || 'Biblioteca').replace(/[^a-zA-Z0-9]/g, '_')}.xlsx`
      XLSX.writeFile(wb, filename)
    } finally {
      setExportando(false)
    }
  }

  const kpis = data?.kpis_comparativa
  const pico = data?.pico_nocturno

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
      <div className="relative flex flex-col w-full max-w-5xl max-h-[92vh] bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden">
        
        {/* Cabecera */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-100 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-400">
              <Moon className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">
                Informe Ejecutivo: Justificación Operativa Régimen 24 Horas
              </h2>
              <p className="text-xs text-slate-700 dark:text-slate-300">
                Documento de soporte para Vicerrectoría Académica y Dirección de Biblioteca · Sala 2 Pecera (226 Asientos)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-600 hover:text-slate-800 dark:text-slate-300 dark:hover:text-slate-100 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Cuerpo con Scroll */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          
          {/* Selector de Campaña / Período */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 bg-slate-100/80 dark:bg-slate-800/60 rounded-xl border border-slate-200 dark:border-slate-700">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
              <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                Campaña o Período Evaluado:
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {data?.campanas_disponibles.map(camp => {
                const isSelected = selectedCampanaId === camp.id || (!selectedCampanaId && data.campana.id === camp.id)
                return (
                  <button
                    key={camp.id}
                    onClick={() => onSelectCampana(camp.id)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                      isSelected
                        ? 'bg-indigo-600 text-white shadow-sm ring-2 ring-indigo-500/20'
                        : 'bg-white dark:bg-slate-700 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-600'
                    }`}
                  >
                    {camp.descripcion}
                  </button>
                )
              })}
            </div>
          </div>

          {loading ? (
            <div className="py-16 text-center text-slate-600 dark:text-slate-300 text-sm">
              Cargando métricas de rendimiento operativo...
            </div>
          ) : data ? (
            <>
              {/* Dictamen Ejecutivo para Autoridades */}
              <div className="p-4 rounded-xl border border-indigo-200 dark:border-indigo-900/50 bg-gradient-to-r from-indigo-50/60 to-purple-50/40 dark:from-indigo-950/20 dark:to-purple-950/20">
                <div className="flex items-start gap-3">
                  <ShieldCheck className="w-5 h-5 text-indigo-600 dark:text-indigo-400 mt-0.5 shrink-0" />
                  <div className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
                    <span className="font-bold text-indigo-900 dark:text-indigo-300">
                      Dictamen de Justificación Operativa:
                    </span>{' '}
                    La apertura en régimen continuo nocturno (20:30 a 07:00 hrs) durante períodos de exámenes
                    ha capturado{' '}
                    <strong className="text-slate-900 dark:text-slate-100">
                      {kpis?.ingresos_nocturnos.toLocaleString('es-CL')} accesos
                    </strong>{' '}
                    equivalentes a un aporte directo del{' '}
                    <strong className="text-indigo-700 dark:text-indigo-300">
                      {kpis?.porcentaje_delta_24h}% (Delta 24 Horas)
                    </strong>{' '}
                    del volumen de estudio. Benefició directamente a{' '}
                    <strong className="text-slate-900 dark:text-slate-100">
                      {kpis?.estudiantes_nocturnos_unicos.toLocaleString('es-CL')} estudiantes únicos
                    </strong>{' '}
                    y sumó{' '}
                    <strong className="text-slate-900 dark:text-slate-100">
                      {kpis?.horas_estudio_nocturnas.toLocaleString('es-CL')} horas de estudio
                    </strong>
                    , alcanzando una concurrencia máxima simultánea de{' '}
                    <strong className="text-emerald-700 dark:text-emerald-300">
                      {pico?.aforo_maximo} personas a las {pico?.hora_pico}
                    </strong>{' '}
                    ({pico?.tasa_ocupacion_asientos_pct}% de aprovechamiento de los 226 asientos disponibles de Sala 2),
                    demostrando alta rentabilidad social y pertinencia académica para justificar la continuidad del servicio.
                  </div>
                </div>
              </div>

              {/* Tarjetas de Métricas Clave (Opción A) */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center justify-between text-xs text-slate-700 dark:text-slate-300 mb-1">
                    <span>Delta 24 Horas</span>
                    <TrendingUp className="w-3.5 h-3.5 text-indigo-500" />
                  </div>
                  <div className="text-xl font-bold text-indigo-600 dark:text-indigo-400">
                    {kpis?.porcentaje_delta_24h}%
                  </div>
                  <div className="text-[10px] text-slate-700 dark:text-slate-300 mt-1">
                    {kpis?.ingresos_nocturnos.toLocaleString('es-CL')} de {kpis?.total_ingresos.toLocaleString('es-CL')} accesos
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center justify-between text-xs text-slate-700 dark:text-slate-300 mb-1">
                    <span>Alumnos Nocturnos</span>
                    <Users className="w-3.5 h-3.5 text-blue-500" />
                  </div>
                  <div className="text-xl font-bold text-slate-800 dark:text-slate-100">
                    {kpis?.estudiantes_nocturnos_unicos.toLocaleString('es-CL')}
                  </div>
                  <div className="text-[10px] text-slate-700 dark:text-slate-300 mt-1">
                    Personas únicas en la noche
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center justify-between text-xs text-slate-700 dark:text-slate-300 mb-1">
                    <span>Máxima Concurrencia</span>
                    <Flame className="w-3.5 h-3.5 text-amber-500" />
                  </div>
                  <div className="text-xl font-bold text-amber-600 dark:text-amber-400">
                    {pico?.aforo_maximo} <span className="text-xs font-normal">personas</span>
                  </div>
                  <div className="text-[10px] text-slate-700 dark:text-slate-300 mt-1">
                    {pico?.tasa_ocupacion_asientos_pct}% cupo · {pico?.hora_pico}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center justify-between text-xs text-slate-700 dark:text-slate-300 mb-1">
                    <span>Horas de Estudio</span>
                    <Clock className="w-3.5 h-3.5 text-purple-500" />
                  </div>
                  <div className="text-xl font-bold text-purple-600 dark:text-purple-400">
                    {kpis?.horas_estudio_nocturnas.toLocaleString('es-CL')} <span className="text-xs font-normal">hrs</span>
                  </div>
                  <div className="text-[10px] text-slate-700 dark:text-slate-300 mt-1">
                    Tiempo de estudio efectivo
                  </div>
                </div>
              </div>

              {/* Fases de Madrugada */}
              <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
                    Comportamiento Temporal por Fases de la Noche
                  </h3>
                  <span className="text-[11px] text-slate-700 dark:text-slate-300">
                    Total: {kpis?.ingresos_nocturnos.toLocaleString('es-CL')} registros
                  </span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {data.fases_madrugada.map((f, i) => (
                    <div key={i} className="p-3 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                      <div className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                        {f.fase}
                      </div>
                      <div className="flex items-baseline justify-between mb-2">
                        <span className="text-lg font-bold text-slate-900 dark:text-slate-100">
                          {f.ingresos.toLocaleString('es-CL')}
                        </span>
                        <span className="text-xs font-semibold text-indigo-600 dark:text-indigo-400">
                          {f.porcentaje}%
                        </span>
                      </div>
                      <div className="w-full bg-slate-100 dark:bg-slate-700 h-1.5 rounded-full overflow-hidden">
                        <div
                          className="bg-indigo-600 dark:bg-indigo-500 h-1.5 rounded-full"
                          style={{ width: `${Math.min(100, f.porcentaje)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Segmentación Curricular Nocturna (Opción C) */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                
                {/* Carreras */}
                <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center gap-2 mb-3">
                    <GraduationCap className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                      Top Carreras en Horario Nocturno
                    </h3>
                  </div>
                  <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                    {data.top_carreras.map((c, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between text-xs p-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/60"
                      >
                        <div className="truncate max-w-[210px] font-medium text-slate-700 dark:text-slate-300" title={c.carrera}>
                          <span className="text-[10px] text-slate-600 dark:text-slate-400 mr-1.5">#{i + 1}</span>
                          {c.carrera}
                        </div>
                        <div className="flex items-center gap-2.5 text-right shrink-0">
                          <span className="font-semibold text-slate-800 dark:text-slate-200">
                            {c.visitas} vis.
                          </span>
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
                            {c.porcentaje}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Facultades */}
                <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center gap-2 mb-3">
                    <Building2 className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                      Distribución por Facultad
                    </h3>
                  </div>
                  <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                    {data.top_facultades.map((f, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between text-xs p-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/60"
                      >
                        <div className="truncate max-w-[210px] font-medium text-slate-700 dark:text-slate-300" title={f.facultad}>
                          <span className="text-[10px] text-slate-600 dark:text-slate-400 mr-1.5">#{i + 1}</span>
                          {f.facultad}
                        </div>
                        <div className="flex items-center gap-2.5 text-right shrink-0">
                          <span className="font-semibold text-slate-800 dark:text-slate-200">
                            {f.visitas} vis.
                          </span>
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-50 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400">
                            {f.porcentaje}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

              </div>
            </>
          ) : null}

        </div>

        {/* Pie con Acciones */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50">
          <div className="text-xs text-slate-700 dark:text-slate-300">
            Fuente: Sistema de Control de Acceso CSF04 Pecera · Auditoría Algorítmica UCT
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleExportExcel}
              disabled={exportando || !data}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800 rounded-xl shadow-sm transition-colors disabled:opacity-50"
            >
              <Download className="w-4 h-4" />
              {exportando ? 'Generando Excel...' : 'Exportar Informe Excel (.xlsx)'}
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl transition-colors"
            >
              Cerrar
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
