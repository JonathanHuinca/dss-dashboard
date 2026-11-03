import React, { useState, useRef } from 'react'
import {
  UploadCloud,
  FileSpreadsheet,
  BookOpen,
  Car,
  GraduationCap,
  Calendar,
  Database,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
} from 'lucide-react'

export interface ContextOption {
  id: string
  tipo: string
  espacioId: number
  titulo: string
  subtitulo: string
  icono: React.ElementType
}

const CONTEXT_OPTIONS: ContextOption[] = [
  {
    id: 'marcajes_torniquete_biblio',
    tipo: 'marcajes_torniquete',
    espacioId: 1,
    titulo: 'Marcajes Torniquetes CSF',
    subtitulo: 'Biblioteca CSF02/CSF04 — Eventos individuales por torniquete (HikCentral)',
    icono: BookOpen,
  },
  {
    id: 'asistencia_biblio',
    tipo: 'asistencia',
    espacioId: 1,
    titulo: 'Visitas Consolidadas Biblioteca',
    subtitulo: 'Salas de Estudio — Registro consolidado por visita (Entrada/Salida)',
    icono: BookOpen,
  },
  {
    id: 'vehicular_estac',
    tipo: 'vehicular',
    espacioId: 2,
    titulo: 'Cámaras LPR Vehiculares',
    subtitulo: 'Estacionamiento CSF (Control de matrículas y tránsito)',
    icono: Car,
  },
  {
    id: 'curricular_catalogo',
    tipo: 'curricular',
    espacioId: 1,
    titulo: 'Maestro Curricular',
    subtitulo: 'Catálogo de Estudiantes, Matrículas y Carreras (RF30)',
    icono: GraduationCap,
  },
  {
    id: 'academico_hitos',
    tipo: 'academico',
    espacioId: 1,
    titulo: 'Calendario Académico',
    subtitulo: 'Feriados, semanas de receso, suspensiones y exámenes',
    icono: Calendar,
  },
  {
    id: 'custom_dataset',
    tipo: 'custom',
    espacioId: 1,
    titulo: 'Dataset Personalizado',
    subtitulo: 'Archivos tabulares adicionales para exploración analítica',
    icono: Database,
  },
]

interface Props {
  selectedTipo: string
  selectedEspacioId: number
  onContextChange: (tipo: string, espacioId: number) => void
  selectedFile: File | null
  onFileSelect: (file: File) => void
  onClearFile: () => void
  isInspecting: boolean
  inspectionError: string | null
}

export const Step1Upload: React.FC<Props> = ({
  selectedTipo,
  selectedEspacioId,
  onContextChange,
  selectedFile,
  onFileSelect,
  onClearFile,
  isInspecting,
  inspectionError,
}) => {
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0]
      validateAndPropagate(file)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0]
      validateAndPropagate(file)
    }
  }

  const validateAndPropagate = (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (ext === 'csv' || ext === 'xlsx' || ext === 'xls') {
      onFileSelect(file)
    } else {
      alert('Formato de archivo no admitido. Seleccione un archivo .csv o .xlsx')
    }
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  return (
    <div className="space-y-6">
      {/* 1. Selector de Contexto Institucional */}
      <div>
        <label className="block text-sm font-bold text-slate-800 mb-2">
          1. Seleccione el Tipo de Ingesta y Recinto Objetivo
        </label>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {CONTEXT_OPTIONS.map((opt) => {
            const isSelected = selectedTipo === opt.tipo && selectedEspacioId === opt.espacioId
            const Icon = opt.icono
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => onContextChange(opt.tipo, opt.espacioId)}
                className={`p-3.5 rounded-xl border text-left transition-all flex items-start gap-3 cursor-pointer ${
                  isSelected
                    ? 'border-uct-blue-primary bg-uct-blue-primary/5 shadow-xs ring-2 ring-uct-blue-primary/20'
                    : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                <div
                  className={`p-2 rounded-lg shrink-0 ${
                    isSelected ? 'bg-uct-blue-primary text-white' : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  <Icon size={18} />
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-bold text-slate-900 leading-tight truncate">
                    {opt.titulo}
                  </p>
                  <p className="text-[11px] text-slate-500 leading-snug mt-0.5 line-clamp-2">
                    {opt.subtitulo}
                  </p>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* 2. Zona de Carga / Drag and Drop */}
      <div>
        <label className="block text-sm font-bold text-slate-800 mb-2">
          2. Cargar Archivo Fuente (.csv, .xlsx, .xls)
        </label>

        {!selectedFile ? (
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-2xl p-8 text-center transition-all cursor-pointer ${
              isDragOver
                ? 'border-uct-blue-primary bg-blue-50/60 scale-[0.99]'
                : 'border-slate-300 hover:border-uct-blue-primary/60 hover:bg-slate-50/70'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              className="hidden"
              onChange={handleFileChange}
            />
            <div className="w-14 h-14 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-3 text-slate-500">
              <UploadCloud size={28} />
            </div>
            <p className="text-sm font-bold text-slate-800">
              Arrastre y suelte su archivo aquí, o haga clic para examinar
            </p>
            <p className="text-xs text-slate-500 mt-1">
              Archivos compatibles: Reportes HikCentral de marcajes peatonal, tránsitos vehiculares ANPR o archivos de salas de estudio
            </p>
            <div className="mt-4 flex items-center justify-center gap-2">
              <span className="text-[11px] bg-slate-100 text-slate-600 font-semibold px-2.5 py-1 rounded-md border border-slate-200">
                Límite recomendado: 100 MB
              </span>
              <span className="text-[11px] bg-blue-50 text-blue-700 font-semibold px-2.5 py-1 rounded-md border border-blue-200">
                Detección automática de cabecera
              </span>
            </div>
          </div>
        ) : (
          <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-emerald-100 text-emerald-800 rounded-xl">
                  <FileSpreadsheet size={24} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-bold text-slate-900 truncate max-w-md">
                      {selectedFile.name}
                    </p>
                    <span className="text-[11px] bg-slate-200 text-slate-700 px-2 py-0.5 rounded-full font-mono">
                      {formatFileSize(selectedFile.size)}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Archivo preparado para inspección de estructura y schema matching en memoria
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {isInspecting ? (
                  <div className="flex items-center gap-2 text-xs font-semibold text-uct-blue-primary bg-blue-50 px-3 py-1.5 rounded-lg border border-blue-200">
                    <Loader2 size={14} className="animate-spin" />
                    <span>Inspeccionando estructura...</span>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={onClearFile}
                    className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors cursor-pointer"
                    title="Remover archivo seleccionado"
                  >
                    <X size={18} />
                  </button>
                )}
              </div>
            </div>

            {/* Banner de inspección exitosa o en curso */}
            {isInspecting && (
              <div className="mt-4 pt-4 border-t border-slate-200">
                <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden">
                  <div className="bg-uct-blue-primary h-full w-2/3 animate-pulse rounded-full" />
                </div>
                <p className="text-[11px] text-slate-500 mt-1.5">
                  Procesando bytes en memoria volátil, analizando filas de metadatos y aplicando semáforo de columnas...
                </p>
              </div>
            )}
          </div>
        )}

        {/* Notificación de Error de Inspección */}
        {inspectionError && (
          <div className="mt-3 p-3.5 bg-rose-50 border border-rose-200 rounded-xl flex items-start gap-2.5 text-rose-700 text-xs">
            <AlertCircle size={16} className="shrink-0 mt-0.5" />
            <div>
              <p className="font-bold">Error al inspeccionar la estructura del archivo:</p>
              <p className="mt-0.5">{inspectionError}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
