import React, { useEffect, useState, useRef } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Hash,
  Calendar,
  Layers,
  ArrowRight,
  Loader2,
  RefreshCw,
  Copy,
  Check,
  ShieldAlert,
  GraduationCap,
} from 'lucide-react'
import {
  InspectResponse,
  ValidationResponse,
  ProcessResponse,
  validateIngestion,
  uploadIngestion,
  fetchJobStatus,
  JobStatusResponse,
} from '../../../api/client'

interface Props {
  file: File
  inspectData: InspectResponse
  claveEnlace: 'rut' | 'matricula' | 'crosswalk'
  modoEnlace: 'tolerante' | 'mandatorio'
  modoSolapamiento: 'merge' | 'overwrite'
  onChangeModoSolapamiento: (modo: 'merge' | 'overwrite') => void
  onSuccess: (res: ProcessResponse) => void
}

export const Step4Summary: React.FC<Props> = ({
  file,
  inspectData,
  claveEnlace,
  modoEnlace,
  modoSolapamiento,
  onChangeModoSolapamiento,
  onSuccess,
}) => {
  const [isValidating, setIsValidating] = useState(false)
  const [valData, setValData] = useState<ValidationResponse | null>(null)
  const [valError, setValError] = useState<string | null>(null)

  const [isProcessing, setIsProcessing] = useState(false)
  const [processResult, setProcessResult] = useState<ProcessResponse | null>(null)
  const [processError, setProcessError] = useState<string | null>(null)
  const [copiedHash, setCopiedHash] = useState(false)
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null)
  const pollIntervalRef = useRef<any>(null)

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
      }
    }
  }, [])

  // Ejecutar validación previa al montar
  useEffect(() => {
    let isMounted = true
    const runValidation = async () => {
      setIsValidating(true)
      setValError(null)
      try {
        const res = await validateIngestion(file, inspectData.tipo, inspectData.espacio_id)
        if (isMounted) {
          setValData(res)
          // Si el hash ya fue procesado o hay colisión, sugerir overwrite si el usuario lo desea
          if (res.hash_ya_procesado) {
            onChangeModoSolapamiento('overwrite')
          }
        }
      } catch (err: any) {
        if (isMounted) {
          setValError(err?.response?.data?.detail || err?.message || 'Error validando colisiones en servidor')
        }
      } finally {
        if (isMounted) setIsValidating(false)
      }
    }

    runValidation()
    return () => {
      isMounted = false
    }
  }, [file, inspectData.tipo, inspectData.espacio_id])

  const handleCopyHash = (hash: string) => {
    navigator.clipboard.writeText(hash)
    setCopiedHash(true)
    setTimeout(() => setCopiedHash(false), 2000)
  }

  const handleExecuteIngestion = async () => {
    setIsProcessing(true)
    setProcessError(null)
    setJobStatus(null)

    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }

    try {
      const uploadRes = await uploadIngestion({
        file,
        tipo: inspectData.tipo,
        espacio_id: inspectData.espacio_id,
        modo_solapamiento: modoSolapamiento,
        clave_enlace: claveEnlace,
        modo_enlace: modoEnlace,
      })

      setJobStatus({
        job_id: uploadRes.job_id,
        estado: 'queued',
        registros_ok: 0,
        registros_error: 0,
        error_detail: null,
      })

      // Sondeo cada 2 segundos hasta finalizar el trabajo
      pollIntervalRef.current = setInterval(async () => {
        try {
          const status = await fetchJobStatus(uploadRes.job_id)
          setJobStatus(status)

          if (status.estado === 'completed') {
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current)
              pollIntervalRef.current = null
            }
            setIsProcessing(false)
            const completedResult: ProcessResponse = {
              job_id: status.job_id,
              status: 'completed',
              modo_solapamiento: modoSolapamiento,
              clave_enlace: claveEnlace,
              modo_enlace: modoEnlace,
              registros_procesados: status.registros_ok,
              registros_insertados: status.registros_ok,
              registros_eliminados: 0,
              carreras_catalogadas: status.registros_ok,
              carreras_no_catalogadas: 0,
              file_hash: uploadRes.file_hash || '',
              detalle: `Ingesta masiva finalizada con éxito. ${status.registros_ok.toLocaleString('es-CL')} registros procesados e insertados en base de datos.`,
            }
            setProcessResult(completedResult)
            onSuccess(completedResult)
          } else if (status.estado === 'failed') {
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current)
              pollIntervalRef.current = null
            }
            setIsProcessing(false)
            setProcessError(status.error_detail || 'Error durante la ejecución del pipeline de ingesta.')
          }
        } catch (pollErr: any) {
          console.error('Error al sondear estado de ingesta:', pollErr)
        }
      }, 2000)
    } catch (err: any) {
      setIsProcessing(false)
      setProcessError(err?.response?.data?.detail || err?.message || 'Error al iniciar la transacción de ingesta')
    }
  }

  return (
    <div className="space-y-6">
      {/* Estado de Carga de Validación */}
      {isValidating && (
        <div className="p-8 text-center bg-slate-50 border border-slate-200 rounded-2xl space-y-3">
          <Loader2 size={32} className="animate-spin text-uct-blue-primary mx-auto" />
          <p className="text-sm font-bold text-slate-800">
            Validando Integridad Criptográfica y Colisiones Temporales...
          </p>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Calculando hash SHA-256 en memoria volátil y consultando rangos en SQL Server para el espacio seleccionado.
          </p>
        </div>
      )}

      {/* Error de Validación */}
      {valError && !isValidating && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 space-y-1">
          <div className="flex items-center gap-2 font-bold">
            <AlertTriangle size={16} />
            <span>Fallo al validar colisiones en el backend</span>
          </div>
          <p>{valError}</p>
        </div>
      )}

      {/* Ficha Técnica y Control de Colisiones */}
      {valData && !isValidating && !processResult && (
        <div className="space-y-5">
          {/* Alertas de Colisión o Archivo Repetido */}
          {valData.hash_ya_procesado && (
            <div className="p-4 bg-amber-50 border border-amber-300 rounded-xl text-xs text-amber-900 space-y-1.5">
              <div className="flex items-center gap-2 font-bold text-amber-950">
                <ShieldAlert size={18} className="text-amber-600" />
                <span>Archivo Previamente Procesado (Hash SHA-256 Duplicado)</span>
              </div>
              <p>
                Este archivo exacto ya fue registrado con éxito{' '}
                {valData.trabajo_previo?.fecha && `el ${valData.trabajo_previo.fecha}`}{' '}
                ({valData.trabajo_previo?.registros_ok} registros). Para reingestar con correcciones curriculares, debe seleccionar &quot;Sobrescritura Atómica de Rango&quot;.
              </p>
            </div>
          )}

          {valData.existe_colision && !valData.hash_ya_procesado && (
            <div className="p-4 bg-amber-50/80 border border-amber-200 rounded-xl text-xs text-amber-900 space-y-1.5">
              <div className="flex items-center gap-2 font-bold text-amber-950">
                <AlertTriangle size={18} className="text-amber-600" />
                <span>Solapamiento Temporal Detectado ({valData.registros_existentes} registros existentes)</span>
              </div>
              <p>
                Ya existen registros en la base de datos dentro del período detectado ({valData.fecha_min} al {valData.fecha_max}). Seleccione abajo cómo resolver la colisión.
              </p>
            </div>
          )}

          {/* Ficha Técnica del Archivo */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
              <div className="flex items-center justify-between text-slate-500 font-semibold">
                <span className="flex items-center gap-1.5">
                  <Hash size={14} /> Hash SHA-256 (Firma Digital)
                </span>
                <button
                  type="button"
                  onClick={() => handleCopyHash(valData.file_hash)}
                  className="p-1 hover:bg-slate-200 rounded transition-colors text-slate-600 cursor-pointer"
                  title="Copiar hash completo"
                >
                  {copiedHash ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
                </button>
              </div>
              <p className="font-mono font-bold text-slate-800 text-[11px] truncate">
                {valData.file_hash}
              </p>
            </div>

            <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
              <span className="text-slate-500 font-semibold flex items-center gap-1.5">
                <Calendar size={14} /> Rango Temporal Detectado
              </span>
              <p className="font-bold text-slate-800 text-xs">
                {valData.fecha_min && valData.fecha_max
                  ? `${valData.fecha_min} a ${valData.fecha_max}`
                  : 'Rango no acotado / archivo sin marcas temporales'}
              </p>
            </div>

            <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
              <span className="text-slate-500 font-semibold flex items-center gap-1.5">
                <Layers size={14} /> Total de Filas en Archivo
              </span>
              <p className="font-bold text-slate-800 text-sm">
                {valData.total_filas.toLocaleString()} registros
              </p>
            </div>

            <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
              <span className="text-slate-500 font-semibold flex items-center gap-1.5">
                <GraduationCap size={14} /> Enlace Curricular Detectado
              </span>
              <p className="font-bold text-slate-800 text-xs">
                Clave: <span className="uppercase text-uct-blue-primary">{valData.clave_enlace_detectada}</span> | Coincidencia: {valData.porcentaje_coincidencia_carreras}%
              </p>
            </div>
          </div>

          {/* Estrategia de Resolución de Colisión */}
          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
            <div>
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wide">
                Estrategia de Carga y Resolución de Colisiones
              </h4>
              <p className="text-xs text-slate-500 mt-0.5">
                Defina cómo debe comportarse la transacción en caso de registros coincidentes.
              </p>
            </div>

            <div className="space-y-2 text-xs">
              <label
                className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                  modoSolapamiento === 'merge'
                    ? 'border-uct-blue-primary bg-uct-blue-primary/5 ring-1 ring-uct-blue-primary/30'
                    : 'border-slate-200 bg-white hover:bg-slate-50'
                }`}
              >
                <input
                  type="radio"
                  name="modo_solapamiento"
                  value="merge"
                  checked={modoSolapamiento === 'merge'}
                  onChange={() => onChangeModoSolapamiento('merge')}
                  className="mt-0.5 text-uct-blue-primary focus:ring-uct-blue-primary cursor-pointer"
                />
                <div>
                  <p className="font-bold text-slate-900">
                    Fusión Conservativa / Merge (Modo Aditivo)
                  </p>
                  <p className="text-slate-500 mt-0.5 leading-snug">
                    Conserva los registros existentes en base de datos e inserta únicamente los registros nuevos no duplicados. Si el archivo exacto ya fue subido, rechazará con 409 Conflict.
                  </p>
                </div>
              </label>

              <label
                className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                  modoSolapamiento === 'overwrite'
                    ? 'border-amber-500 bg-amber-50/40 ring-1 ring-amber-400'
                    : 'border-slate-200 bg-white hover:bg-slate-50'
                }`}
              >
                <input
                  type="radio"
                  name="modo_solapamiento"
                  value="overwrite"
                  checked={modoSolapamiento === 'overwrite'}
                  onChange={() => onChangeModoSolapamiento('overwrite')}
                  className="mt-0.5 text-amber-600 focus:ring-amber-500 cursor-pointer"
                />
                <div>
                  <p className="font-bold text-amber-950">
                    Sobrescritura Atómica de Rango (Recarga Retroactiva Enriquecida - RF30)
                  </p>
                  <p className="text-amber-900/80 mt-0.5 leading-snug">
                    Ejecuta una transacción ACID que elimina los datos del rango [{valData.fecha_min || 'inicio'} al {valData.fecha_max || 'fin'}] e inserta esta versión enriquecida con información curricular. Recomendado para actualizar datasets con carreras.
                  </p>
                </div>
              </label>
            </div>
          </div>

          {/* Error de Procesamiento */}
          {processError && (
            <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 space-y-1">
              <div className="flex items-center gap-2 font-bold">
                <AlertTriangle size={16} />
                <span>Error durante la transacción de ingesta:</span>
              </div>
              <p>{processError}</p>
            </div>
          )}

          {/* Panel de Progreso en Tiempo Real con Sondeo cada 2 segundos */}
          {isProcessing && (
            <div className="p-4 bg-uct-blue-primary/5 border border-uct-blue-primary/20 rounded-xl space-y-2.5">
              <div className="flex items-center justify-between text-xs font-semibold text-uct-blue-primary">
                <span className="flex items-center gap-2">
                  <Loader2 size={16} className="animate-spin text-uct-blue-primary" />
                  {jobStatus?.estado === 'queued'
                    ? 'En cola de espera (límite de 1 ingesta simultánea activa)...'
                    : 'Procesando pipeline masivo por lotes en segundo plano...'}
                </span>
                <span className="font-mono text-slate-700 bg-white px-2 py-0.5 rounded border border-slate-200">
                  {jobStatus?.registros_ok
                    ? `${jobStatus.registros_ok.toLocaleString('es-CL')} registros`
                    : 'Iniciando...'}
                </span>
              </div>
              <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden">
                <div
                  className="bg-uct-blue-primary h-full transition-all duration-500 rounded-full w-full animate-pulse"
                />
              </div>
              <div className="flex items-center justify-between text-[11px] text-slate-500">
                <span>Sondeo cada 2s activo (liberación de memoria por lote de 10.000)</span>
                {jobStatus?.job_id && (
                  <span className="font-mono text-[10px]">Job: {jobStatus.job_id.slice(0, 8)}</span>
                )}
              </div>
            </div>
          )}

          {/* Botón de Ejecución */}
          <div className="pt-2">
            <button
              type="button"
              disabled={isProcessing}
              onClick={handleExecuteIngestion}
              className="w-full py-3 bg-uct-blue-primary hover:bg-uct-blue-secondary text-white font-bold text-sm rounded-xl transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
            >
              {isProcessing ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  <span>
                    {jobStatus?.estado === 'queued'
                      ? 'En cola de espera...'
                      : `Procesando Ingesta (${jobStatus?.registros_ok.toLocaleString('es-CL') || 0} registros)...`}
                  </span>
                </>
              ) : (
                <>
                  <Database size={18} />
                  <span>Iniciar Ingesta Masiva Definitiva</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Pantalla de Éxito / Resultado de la Ingesta */}
      {processResult && (
        <div className="p-6 bg-emerald-50/80 border border-emerald-200 rounded-2xl text-center space-y-4">
          <div className="w-14 h-14 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center mx-auto shadow-xs">
            <CheckCircle2 size={32} />
          </div>
          <div>
            <h3 className="text-base font-bold text-emerald-950">
              Ingesta Procesada Exitosamente
            </h3>
            <p className="text-xs text-emerald-800 mt-1 max-w-md mx-auto">
              {processResult.detalle}
            </p>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs pt-3 border-t border-emerald-200/80">
            <div className="bg-white p-3 rounded-xl border border-emerald-200">
              <span className="text-slate-500 font-semibold block">Insertados</span>
              <span className="text-base font-bold text-emerald-700">
                {processResult.registros_insertados.toLocaleString()}
              </span>
            </div>
            <div className="bg-white p-3 rounded-xl border border-emerald-200">
              <span className="text-slate-500 font-semibold block">Eliminados Previos</span>
              <span className="text-base font-bold text-slate-700">
                {processResult.registros_eliminados.toLocaleString()}
              </span>
            </div>
            <div className="bg-white p-3 rounded-xl border border-emerald-200">
              <span className="text-slate-500 font-semibold block">Con Carrera</span>
              <span className="text-base font-bold text-uct-blue-primary">
                {processResult.carreras_catalogadas.toLocaleString()}
              </span>
            </div>
            <div className="bg-white p-3 rounded-xl border border-emerald-200">
              <span className="text-slate-500 font-semibold block">Sin Carrera</span>
              <span className="text-base font-bold text-slate-600">
                {processResult.carreras_no_catalogadas.toLocaleString()}
              </span>
            </div>
          </div>

          <div className="pt-2 text-[11px] text-slate-500 font-mono">
            Job ID: {processResult.job_id} | Hash: {processResult.file_hash.slice(0, 16)}...
          </div>
        </div>
      )}
    </div>
  )
}
