import React, { useState } from 'react'
import {
  X,
  ArrowRight,
  ArrowLeft,
  UploadCloud,
  Layers,
  ShieldCheck,
  Database,
  CheckCircle2,
  RotateCcw,
} from 'lucide-react'
import {
  InspectResponse,
  SchemaFieldMapping,
  ProcessResponse,
  inspectFile,
} from '../../api/client'
import { Step1Upload } from './steps/Step1Upload'
import { Step2Mapping } from './steps/Step2Mapping'
import { Step3Privacy } from './steps/Step3Privacy'
import { Step4Summary } from './steps/Step4Summary'

interface Props {
  isOpen: boolean
  onClose: () => void
  onIngestionCompleted?: () => void
}

export const IngestionWizardModal: React.FC<Props> = ({
  isOpen,
  onClose,
  onIngestionCompleted,
}) => {
  const [currentStep, setCurrentStep] = useState<number>(1)
  const [selectedTipo, setSelectedTipo] = useState<string>('marcajes_torniquete')
  const [selectedEspacioId, setSelectedEspacioId] = useState<number>(1)

  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isInspecting, setIsInspecting] = useState<boolean>(false)
  const [inspectionError, setInspectionError] = useState<string | null>(null)
  const [inspectData, setInspectData] = useState<InspectResponse | null>(null)

  // Opciones de enlace y solapamiento (RF04, RF30)
  const [claveEnlace, setClaveEnlace] = useState<'rut' | 'matricula' | 'crosswalk'>('rut')
  const [modoEnlace, setModoEnlace] = useState<'tolerante' | 'mandatorio'>('tolerante')
  const [modoSolapamiento, setModoSolapamiento] = useState<'merge' | 'overwrite'>('merge')

  const [processResult, setProcessResult] = useState<ProcessResponse | null>(null)

  if (!isOpen) return null

  const handleContextChange = (tipo: string, espacioId: number) => {
    setSelectedTipo(tipo)
    setSelectedEspacioId(espacioId)
    // Si ya había un archivo seleccionado, reinspeccionar con el nuevo tipo
    if (selectedFile) {
      triggerInspection(selectedFile, tipo, espacioId)
    }
  }

  const triggerInspection = async (file: File, tipo: string, espacioId: number) => {
    setIsInspecting(true)
    setInspectionError(null)
    setInspectData(null)
    try {
      const data = await inspectFile(file, tipo, espacioId)
      setInspectData(data)
      if (data.tipo && data.tipo !== selectedTipo) {
        setSelectedTipo(data.tipo)
      }
      // Ajustar clave de enlace inicial si el backend detectó columnas curriculares
      const hasRut = data.columns_detected.some((c) => /rut|run/i.test(c))
      const hasMat = data.columns_detected.some((c) => /matricula/i.test(c))
      if (hasRut && hasMat) setClaveEnlace('crosswalk')
      else if (hasMat) setClaveEnlace('matricula')
      else setClaveEnlace('rut')
    } catch (err: any) {
      setInspectionError(
        err?.response?.data?.detail || err?.message || 'Error procesando la estructura del archivo'
      )
    } finally {
      setIsInspecting(false)
    }
  }

  const handleFileSelect = (file: File) => {
    setSelectedFile(file)
    triggerInspection(file, selectedTipo, selectedEspacioId)
  }

  const handleClearFile = () => {
    setSelectedFile(null)
    setInspectData(null)
    setInspectionError(null)
  }

  const handleUpdateMapping = (updatedMapping: SchemaFieldMapping[]) => {
    if (inspectData) {
      setInspectData({
        ...inspectData,
        schema_mapping: updatedMapping,
      })
    }
  }

  const handleReset = () => {
    setCurrentStep(1)
    setSelectedFile(null)
    setInspectData(null)
    setInspectionError(null)
    setProcessResult(null)
    setModoSolapamiento('merge')
  }

  const handleFinish = () => {
    if (onIngestionCompleted) {
      onIngestionCompleted()
    }
    onClose()
  }

  const stepsList = [
    { num: 1, label: 'Carga y Contexto', icon: UploadCloud },
    { num: 2, label: 'Mapeo Asistido', icon: Layers },
    { num: 3, label: 'Privacidad Ley 21.719', icon: ShieldCheck },
    { num: 4, label: 'Validación y Carga', icon: Database },
  ]

  const canProceed = () => {
    if (currentStep === 1) {
      return selectedFile !== null && inspectData !== null && !isInspecting
    }
    if (currentStep === 2) {
      return inspectData !== null
    }
    if (currentStep === 3) {
      return true
    }
    return false
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-900/60 backdrop-blur-xs">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in duration-200">
        {/* Cabecera del Modal */}
        <div className="px-6 py-4 bg-uct-blue-primary text-white flex items-center justify-between border-b border-white/10 shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider bg-uct-gold text-uct-blue-primary px-2 py-0.5 rounded-full font-mono">
                DSS UCT • Ingesta Inteligente
              </span>
              <span className="text-xs text-white/70">RF03 &amp; RF30</span>
            </div>
            <h2 className="text-base font-bold leading-tight mt-0.5">
              Asistente de Ingesta y Cruce Curricular en 4 Pasos
            </h2>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-xl transition-colors cursor-pointer"
            title="Cerrar modal"
          >
            <X size={20} />
          </button>
        </div>

        {/* Stepper Superior */}
        <div className="px-6 py-3.5 bg-slate-50 border-b border-slate-200 shrink-0">
          <div className="flex items-center justify-between max-w-3xl mx-auto">
            {stepsList.map((s, idx) => {
              const Icon = s.icon
              const isCurrent = currentStep === s.num
              const isCompleted = currentStep > s.num || processResult !== null
              return (
                <React.Fragment key={s.num}>
                  <div className="flex items-center gap-2">
                    <div
                      className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                        isCurrent
                          ? 'bg-uct-blue-primary text-white ring-4 ring-uct-blue-primary/20 shadow-xs'
                          : isCompleted
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-200 text-slate-500'
                      }`}
                    >
                      {isCompleted ? <CheckCircle2 size={14} /> : s.num}
                    </div>
                    <span
                      className={`text-xs font-semibold hidden sm:inline ${
                        isCurrent ? 'text-slate-900 font-bold' : isCompleted ? 'text-emerald-800' : 'text-slate-500'
                      }`}
                    >
                      {s.label}
                    </span>
                  </div>

                  {idx < stepsList.length - 1 && (
                    <div
                      className={`flex-1 h-0.5 mx-3 transition-colors ${
                        currentStep > s.num ? 'bg-emerald-500' : 'bg-slate-200'
                      }`}
                    />
                  )}
                </React.Fragment>
              )
            })}
          </div>
        </div>

        {/* Cuerpo del Paso Activo (Scrollable) */}
        <div className="px-6 py-5 overflow-y-auto flex-1">
          {currentStep === 1 && (
            <Step1Upload
              selectedTipo={selectedTipo}
              selectedEspacioId={selectedEspacioId}
              onContextChange={handleContextChange}
              selectedFile={selectedFile}
              onFileSelect={handleFileSelect}
              onClearFile={handleClearFile}
              isInspecting={isInspecting}
              inspectionError={inspectionError}
            />
          )}

          {currentStep === 2 && inspectData && (
            <Step2Mapping
              inspectData={inspectData}
              onUpdateMapping={handleUpdateMapping}
              claveEnlace={claveEnlace}
              onChangeClaveEnlace={setClaveEnlace}
              modoEnlace={modoEnlace}
              onChangeModoEnlace={setModoEnlace}
            />
          )}

          {currentStep === 3 && inspectData && (
            <Step3Privacy inspectData={inspectData} />
          )}

          {currentStep === 4 && selectedFile && inspectData && (
            <Step4Summary
              file={selectedFile}
              inspectData={inspectData}
              claveEnlace={claveEnlace}
              modoEnlace={modoEnlace}
              modoSolapamiento={modoSolapamiento}
              onChangeModoSolapamiento={setModoSolapamiento}
              onSuccess={(res) => setProcessResult(res)}
            />
          )}
        </div>

        {/* Barra de Navegación Inferior */}
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between shrink-0">
          <div>
            {processResult ? (
              <button
                type="button"
                onClick={handleReset}
                className="px-4 py-2 text-xs font-bold text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 rounded-xl transition-colors flex items-center gap-1.5 cursor-pointer shadow-2xs"
              >
                <RotateCcw size={14} />
                <span>Cargar Nuevo Archivo</span>
              </button>
            ) : (
              <button
                type="button"
                disabled={currentStep === 1}
                onClick={() => setCurrentStep((prev) => Math.max(1, prev - 1))}
                className="px-4 py-2 text-xs font-bold text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 rounded-xl transition-colors flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shadow-2xs"
              >
                <ArrowLeft size={14} />
                <span>Anterior</span>
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={processResult ? handleFinish : onClose}
              className="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-900 bg-transparent rounded-xl transition-colors cursor-pointer"
            >
              {processResult ? 'Cerrar' : 'Cancelar'}
            </button>

            {currentStep < 4 ? (
              <button
                type="button"
                disabled={!canProceed()}
                onClick={() => setCurrentStep((prev) => Math.min(4, prev + 1))}
                className="px-5 py-2 text-xs font-bold text-white bg-uct-blue-primary hover:bg-uct-blue-secondary rounded-xl transition-all shadow-xs flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                <span>Continuar</span>
                <ArrowRight size={14} />
              </button>
            ) : processResult ? (
              <button
                type="button"
                onClick={handleFinish}
                className="px-5 py-2 text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 rounded-xl transition-all shadow-xs flex items-center gap-1.5 cursor-pointer"
              >
                <CheckCircle2 size={14} />
                <span>Finalizar y Actualizar Vistas</span>
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
