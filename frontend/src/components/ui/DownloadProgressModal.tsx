import React from 'react'
import {
  FileSpreadsheet,
  FileText,
  Image as ImageIcon,
  CheckCircle2,
  AlertCircle,
  X,
  Loader2,
  Download,
  ArrowRight,
  Database,
  Sparkles,
} from 'lucide-react'
import { useDownloadProgress, DownloadFileType } from '../../context/DownloadProgressContext'

export const DownloadProgressModal: React.FC = () => {
  const { descargaActual, estaAbierto, cerrarModal } = useDownloadProgress()

  if (!estaAbierto || !descargaActual) return null

  const { titulo, subtitulo, tipo, estado, progreso, etapaActual, mensajeError, nombreArchivo } =
    descargaActual

  const renderIconoTipo = (t: DownloadFileType) => {
    switch (t) {
      case 'excel':
        return <FileSpreadsheet className="text-emerald-600 dark:text-emerald-400" size={28} />
      case 'csv':
        return <Database className="text-blue-600 dark:text-blue-400" size={28} />
      case 'pdf':
        return <FileText className="text-rose-600 dark:text-rose-400" size={28} />
      case 'imagen':
        return <ImageIcon className="text-amber-600 dark:text-amber-400" size={28} />
      default:
        return <Download className="text-uct-blue-primary" size={28} />
    }
  }

  const getBadgeColor = (t: DownloadFileType) => {
    switch (t) {
      case 'excel':
        return 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800'
      case 'csv':
        return 'bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800'
      case 'pdf':
        return 'bg-rose-50 text-rose-800 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800'
      case 'imagen':
        return 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800'
    }
  }

  const getTipoLabel = (t: DownloadFileType) => {
    switch (t) {
      case 'excel':
        return 'Microsoft Excel (.xlsx Nativo)'
      case 'csv':
        return 'Archivo Delimitado (.csv)'
      case 'pdf':
        return 'Documento Oficial (.pdf)'
      case 'imagen':
        return 'Captura de Alta Resolución (.png)'
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs animate-in fade-in duration-200">
      <div
        className="w-full max-w-lg bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col"
        role="dialog"
        aria-modal="true"
      >
        {/* Cabecera del Modal */}
        <div className="px-6 py-4.5 border-b border-slate-100 dark:border-slate-800/80 flex items-start justify-between gap-3 bg-slate-50/70 dark:bg-slate-800/40">
          <div className="flex items-center gap-3.5 min-w-0">
            <div className="w-12 h-12 rounded-xl bg-white dark:bg-slate-800 shadow-xs border border-slate-200/80 dark:border-slate-700/80 flex items-center justify-center shrink-0">
              {estado === 'completado' ? (
                <CheckCircle2 className="text-emerald-600 dark:text-emerald-400 animate-in zoom-in-75 duration-200" size={30} />
              ) : estado === 'error' ? (
                <AlertCircle className="text-rose-600 dark:text-rose-400 animate-in zoom-in-75 duration-200" size={30} />
              ) : (
                renderIconoTipo(tipo)
              )}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wider ${getBadgeColor(tipo)}`}>
                  {getTipoLabel(tipo)}
                </span>
                {estado === 'procesando' && (
                  <span className="flex items-center gap-1 text-[11px] font-semibold text-uct-blue-primary dark:text-blue-400">
                    <Loader2 size={11} className="animate-spin" />
                    <span>En progreso</span>
                  </span>
                )}
              </div>
              <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mt-1 truncate" title={titulo}>
                {titulo}
              </h3>
              {subtitulo && (
                <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">
                  {subtitulo}
                </p>
              )}
            </div>
          </div>

          {(estado === 'completado' || estado === 'error') && (
            <button
              onClick={cerrarModal}
              className="p-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
              title="Cerrar ventana"
            >
              <X size={18} />
            </button>
          )}
        </div>

        {/* Cuerpo del Modal */}
        <div className="p-6 space-y-5">
          {/* Barra de progreso interactiva */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold">
              <span className="text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                {estado === 'procesando' && <Sparkles size={13} className="text-amber-500 animate-pulse" />}
                {estado === 'completado' && <CheckCircle2 size={13} className="text-emerald-500" />}
                {estado === 'error' && <AlertCircle size={13} className="text-rose-500" />}
                <span>{etapaActual}</span>
              </span>
              <span className={`font-mono text-sm ${estado === 'error' ? 'text-rose-600' : 'text-uct-blue-primary dark:text-blue-400 font-bold'}`}>
                {progreso}%
              </span>
            </div>

            <div className="w-full h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden p-0.5 border border-slate-200/80 dark:border-slate-700/60 shadow-inner">
              <div
                className={`h-full rounded-full transition-all duration-300 ease-out ${
                  estado === 'error'
                    ? 'bg-rose-500'
                    : estado === 'completado'
                    ? 'bg-emerald-500'
                    : 'bg-gradient-to-r from-uct-blue-primary via-blue-500 to-uct-gold'
                }`}
                style={{ width: `${progreso}%` }}
              />
            </div>
          </div>

          {/* Etapas secuenciales */}
          <div className="grid grid-cols-3 gap-2 pt-1 text-[11px]">
            <div
              className={`p-2 rounded-xl border flex flex-col items-center text-center gap-1 transition-all ${
                progreso >= 30
                  ? 'bg-blue-50/60 border-blue-200 text-blue-900 dark:bg-blue-950/30 dark:border-blue-900 dark:text-blue-200'
                  : 'bg-slate-50 border-slate-200/60 text-slate-400 dark:bg-slate-800/40 dark:border-slate-800'
              }`}
            >
              <span className="font-bold">1. Extracción</span>
              <span className="text-[10px] leading-tight">Series y filtros</span>
            </div>

            <div
              className={`p-2 rounded-xl border flex flex-col items-center text-center gap-1 transition-all ${
                progreso >= 70
                  ? 'bg-blue-50/60 border-blue-200 text-blue-900 dark:bg-blue-950/30 dark:border-blue-900 dark:text-blue-200'
                  : 'bg-slate-50 border-slate-200/60 text-slate-400 dark:bg-slate-800/40 dark:border-slate-800'
              }`}
            >
              <span className="font-bold">2. Compilación</span>
              <span className="text-[10px] leading-tight">Formato institucional</span>
            </div>

            <div
              className={`p-2 rounded-xl border flex flex-col items-center text-center gap-1 transition-all ${
                progreso >= 100
                  ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900 dark:bg-emerald-950/30 dark:border-emerald-900 dark:text-emerald-200'
                  : 'bg-slate-50 border-slate-200/60 text-slate-400 dark:bg-slate-800/40 dark:border-slate-800'
              }`}
            >
              <span className="font-bold">3. Descarga</span>
              <span className="text-[10px] leading-tight">Guardado en equipo</span>
            </div>
          </div>

          {/* Detalle o mensaje de error */}
          {estado === 'error' && mensajeError && (
            <div className="p-3.5 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/60 rounded-xl text-xs text-rose-700 dark:text-rose-300">
              <p className="font-bold flex items-center gap-1.5 mb-1">
                <AlertCircle size={14} className="shrink-0" />
                <span>Detalle del error:</span>
              </p>
              <p className="font-mono text-[11px] break-words">{mensajeError}</p>
            </div>
          )}

          {nombreArchivo && (
            <div className="flex items-center justify-between text-[11px] text-slate-500 bg-slate-50 dark:bg-slate-800/50 p-2.5 rounded-xl border border-slate-200/60 dark:border-slate-700/60">
              <span className="font-medium text-slate-600 dark:text-slate-400">Archivo destino:</span>
              <span className="font-mono font-bold text-slate-800 dark:text-slate-200 truncate max-w-[280px]">
                {nombreArchivo}
              </span>
            </div>
          )}
        </div>

        {/* Pie del Modal */}
        <div className="px-6 py-3.5 bg-slate-50/80 dark:bg-slate-800/60 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <span className="text-[11px] text-slate-400">
            DSS UCT • Campus San Francisco
          </span>

          {estado === 'procesando' ? (
            <span className="text-xs text-slate-500 italic flex items-center gap-1.5">
              <Loader2 size={12} className="animate-spin text-uct-blue-primary" />
              <span>Por favor espere...</span>
            </span>
          ) : (
            <button
              type="button"
              onClick={cerrarModal}
              className={`px-4 py-1.5 rounded-xl text-xs font-bold transition shadow-xs cursor-pointer ${
                estado === 'error'
                  ? 'bg-rose-600 hover:bg-rose-700 text-white'
                  : 'bg-uct-blue-primary hover:bg-uct-blue-secondary text-white'
              }`}
            >
              Cerrar
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
