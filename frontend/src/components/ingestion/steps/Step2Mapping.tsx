import React from 'react'
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  Link,
  ShieldAlert,
  ArrowRight,
  Sparkles,
} from 'lucide-react'
import { InspectResponse, SchemaFieldMapping } from '../../../api/client'

interface Props {
  inspectData: InspectResponse
  onUpdateMapping: (updatedMapping: SchemaFieldMapping[]) => void
  claveEnlace: 'rut' | 'matricula' | 'crosswalk'
  onChangeClaveEnlace: (clave: 'rut' | 'matricula' | 'crosswalk') => void
  modoEnlace: 'tolerante' | 'mandatorio'
  onChangeModoEnlace: (modo: 'tolerante' | 'mandatorio') => void
}

export const Step2Mapping: React.FC<Props> = ({
  inspectData,
  onUpdateMapping,
  claveEnlace,
  onChangeClaveEnlace,
  modoEnlace,
  onChangeModoEnlace,
}) => {
  const handleColumnSelectChange = (targetField: string, newMatchedColumn: string) => {
    const updated = inspectData.schema_mapping.map((m) => {
      if (m.target_field === targetField) {
        const val = newMatchedColumn === '' ? null : newMatchedColumn
        let newStatus: 'verde' | 'amarillo' | 'rojo' = 'verde'
        if (!val) {
          newStatus = m.required ? 'rojo' : 'amarillo'
        } else if (val.toLowerCase() !== m.target_field.toLowerCase()) {
          newStatus = 'amarillo'
        }
        return {
          ...m,
          matched_column: val,
          status: newStatus,
        }
      }
      return m
    })
    onUpdateMapping(updated)
  }

  const getStatusBadge = (status: 'verde' | 'amarillo' | 'rojo', isRequired: boolean) => {
    switch (status) {
      case 'verde':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 size={12} />
            Exacto
          </span>
        )
      case 'amarillo':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
            <AlertTriangle size={12} />
            Sugerido
          </span>
        )
      case 'rojo':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
            <XCircle size={12} />
            {isRequired ? 'Faltante Requerido' : 'No Mapeado'}
          </span>
        )
    }
  }

  const getClassificationBadge = (classification: string) => {
    switch (classification) {
      case 'purgar':
        return (
          <span className="text-[10px] font-bold uppercase tracking-wider bg-rose-50 text-rose-700 px-2 py-0.5 rounded border border-rose-200">
            Purgar (PII)
          </span>
        )
      case 'seudonimizar':
        return (
          <span className="text-[10px] font-bold uppercase tracking-wider bg-purple-50 text-purple-700 px-2 py-0.5 rounded border border-purple-200">
            Seudonimizar
          </span>
        )
      default:
        return (
          <span className="text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-600 px-2 py-0.5 rounded border border-slate-200">
            Analítico
          </span>
        )
    }
  }

  const isAttendanceOrCurricular =
    inspectData.tipo === 'asistencia' ||
    inspectData.tipo === 'marcajes_torniquete' ||
    inspectData.tipo === 'curricular'

  return (
    <div className="space-y-6">
      {/* Resumen de Estructura Detectada */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-200 text-xs">
        <div>
          <p className="text-slate-500 font-semibold">Cabecera Detectada</p>
          <p className="font-bold text-slate-800 text-sm mt-0.5">
            Fila {inspectData.header_row_index + 1} (Índice 0-based: {inspectData.header_row_index})
          </p>
        </div>
        <div>
          <p className="text-slate-500 font-semibold">Total Filas Estimadas</p>
          <p className="font-bold text-slate-800 text-sm mt-0.5">
            {inspectData.total_rows_estimated.toLocaleString()} registros
          </p>
        </div>
        <div>
          <p className="text-slate-500 font-semibold">Columnas en Archivo</p>
          <p className="font-bold text-slate-800 text-sm mt-0.5">
            {inspectData.columns_detected.length} columnas detectadas
          </p>
        </div>
      </div>

      {/* Tabla de Mapeo Asistido con Semáforo */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div>
            <h3 className="text-sm font-bold text-slate-800">
              Mapeo de Columnas (Esquema Institucional vs. Archivo Fuente)
            </h3>
            <p className="text-xs text-slate-500">
              El motor asistido empareja automáticamente los campos requeridos. Puede ajustar manualmente las asignaciones si difieren.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="flex items-center gap-1 text-emerald-700 font-semibold">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" /> Exacto
            </span>
            <span className="flex items-center gap-1 text-amber-700 font-semibold">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" /> Sugerido
            </span>
            <span className="flex items-center gap-1 text-rose-700 font-semibold">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" /> Faltante
            </span>
          </div>
        </div>

        <div className="border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
          <div className="overflow-x-auto max-h-[340px]">
            <table className="w-full text-left border-collapse text-xs">
              <thead className="bg-slate-100 text-slate-700 font-bold sticky top-0 z-10 border-b border-slate-200">
                <tr>
                  <th className="py-2.5 px-3">Campo Objetivo Requerido</th>
                  <th className="py-2.5 px-3">Clasificación Ley 21.719</th>
                  <th className="py-2.5 px-3">Estado</th>
                  <th className="py-2.5 px-3">Columna en Archivo Fuente</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {inspectData.schema_mapping.map((field) => (
                  <tr key={field.target_field} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-slate-800">{field.target_field}</span>
                        {field.required && (
                          <span className="text-[10px] text-rose-600 font-semibold">*Obligatorio</span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-500 mt-0.5">{field.description}</p>
                    </td>

                    <td className="py-2.5 px-3">
                      {getClassificationBadge(field.classification)}
                    </td>

                    <td className="py-2.5 px-3 whitespace-nowrap">
                      {getStatusBadge(field.status, field.required)}
                    </td>

                    <td className="py-2.5 px-3">
                      <select
                        value={field.matched_column || ''}
                        onChange={(e) => handleColumnSelectChange(field.target_field, e.target.value)}
                        className={`w-full max-w-xs text-xs py-1.5 px-2.5 border rounded-lg bg-white focus:outline-none focus:ring-2 cursor-pointer ${
                          field.status === 'verde'
                            ? 'border-emerald-300 focus:ring-emerald-200 text-emerald-900 font-medium'
                            : field.status === 'amarillo'
                            ? 'border-amber-300 focus:ring-amber-200 text-amber-900 font-medium'
                            : 'border-rose-300 focus:ring-rose-200 text-rose-900 font-medium'
                        }`}
                      >
                        <option value="">(Sin asignar / Omitir columna)</option>
                        {inspectData.columns_detected.map((col) => (
                          <option key={col} value={col}>
                            {col}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Sección de Enlace Curricular Flexible (RF30) */}
      {isAttendanceOrCurricular && (
        <div className="p-4 bg-blue-50/60 border border-blue-200 rounded-xl space-y-4">
          <div className="flex items-start gap-2.5">
            <div className="p-1.5 bg-uct-blue-primary text-white rounded-lg shrink-0 mt-0.5">
              <Link size={16} />
            </div>
            <div>
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wide">
                Configuración de Enlace Curricular Flexible (RF30)
              </h4>
              <p className="text-xs text-slate-600 mt-0.5">
                Permite asociar carreras y facultades académicas a los eventos de marcaje institucional mediante RUT o Matrícula universitaria.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-blue-200/70">
            {/* Clave de Cruce */}
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">
                Clave de Cruce Académico
              </label>
              <div className="space-y-1.5 text-xs">
                <label className="flex items-center gap-2 p-2 rounded-lg bg-white border border-blue-200 cursor-pointer hover:bg-blue-50/40">
                  <input
                    type="radio"
                    name="clave_enlace"
                    value="rut"
                    checked={claveEnlace === 'rut'}
                    onChange={() => onChangeClaveEnlace('rut')}
                    className="text-uct-blue-primary focus:ring-uct-blue-primary cursor-pointer"
                  />
                  <div>
                    <span className="font-bold text-slate-800">RUT Nacional</span>
                    <p className="text-[11px] text-slate-500">Cruce mediante seudonimización con hash de RUT</p>
                  </div>
                </label>

                <label className="flex items-center gap-2 p-2 rounded-lg bg-white border border-blue-200 cursor-pointer hover:bg-blue-50/40">
                  <input
                    type="radio"
                    name="clave_enlace"
                    value="matricula"
                    checked={claveEnlace === 'matricula'}
                    onChange={() => onChangeClaveEnlace('matricula')}
                    className="text-uct-blue-primary focus:ring-uct-blue-primary cursor-pointer"
                  />
                  <div>
                    <span className="font-bold text-slate-800">Matrícula Institucional (10 dígitos)</span>
                    <p className="text-[11px] text-slate-500">Cruce directo con el registro estudiantil</p>
                  </div>
                </label>

                <label className="flex items-center gap-2 p-2 rounded-lg bg-white border border-blue-200 cursor-pointer hover:bg-blue-50/40">
                  <input
                    type="radio"
                    name="clave_enlace"
                    value="crosswalk"
                    checked={claveEnlace === 'crosswalk'}
                    onChange={() => onChangeClaveEnlace('crosswalk')}
                    className="text-uct-blue-primary focus:ring-uct-blue-primary cursor-pointer"
                  />
                  <div>
                    <span className="font-bold text-slate-800">Tabla de Equivalencias (Híbrido)</span>
                    <p className="text-[11px] text-slate-500">Prioriza RUT y resuelve colisiones mediante Matrícula</p>
                  </div>
                </label>
              </div>
            </div>

            {/* Modo de Tolerancia */}
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">
                Política de Validación Curricular
              </label>
              <div className="space-y-1.5 text-xs">
                <label className="flex items-center gap-2 p-2 rounded-lg bg-white border border-blue-200 cursor-pointer hover:bg-blue-50/40">
                  <input
                    type="radio"
                    name="modo_enlace"
                    value="tolerante"
                    checked={modoEnlace === 'tolerante'}
                    onChange={() => onChangeModoEnlace('tolerante')}
                    className="text-uct-blue-primary focus:ring-uct-blue-primary cursor-pointer"
                  />
                  <div>
                    <span className="font-bold text-slate-800">Modo Tolerante (Recomendado)</span>
                    <p className="text-[11px] text-slate-500">
                      Permite ingestar marcajes sin carrera asignando el valor &quot;Sin carrera catalogada&quot;.
                    </p>
                  </div>
                </label>

                <label className="flex items-center gap-2 p-2 rounded-lg bg-white border border-blue-200 cursor-pointer hover:bg-blue-50/40">
                  <input
                    type="radio"
                    name="modo_enlace"
                    value="mandatorio"
                    checked={modoEnlace === 'mandatorio'}
                    onChange={() => onChangeModoEnlace('mandatorio')}
                    className="text-uct-blue-primary focus:ring-uct-blue-primary cursor-pointer"
                  />
                  <div>
                    <span className="font-bold text-slate-800">Modo Mandatorio (Estricto)</span>
                    <p className="text-[11px] text-slate-500">
                      Exige 100% de cruce académico. Cancela la transacción si detecta registros huérfanos.
                    </p>
                  </div>
                </label>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
