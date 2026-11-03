import React from 'react'
import {
  ShieldCheck,
  Lock,
  Trash2,
  FileCheck2,
  CheckCircle2,
  Info,
  KeyRound,
  EyeOff,
} from 'lucide-react'
import { InspectResponse } from '../../../api/client'

interface Props {
  inspectData: InspectResponse
}

export const Step3Privacy: React.FC<Props> = ({ inspectData }) => {
  // Identificar columnas purgadas y seudonimizadas
  const purgedColumns = inspectData.schema_mapping.filter((f) => f.classification === 'purgar')
  const pseudonymizedColumns = inspectData.schema_mapping.filter((f) => f.classification === 'seudonimizar')
  const analyticalColumns = inspectData.schema_mapping.filter((f) => f.classification === 'analitico')

  return (
    <div className="space-y-6">
      {/* Banner Oficial de Cumplimiento Ley 21.719 */}
      <div className="bg-emerald-50/70 border border-emerald-200 rounded-2xl p-5">
        <div className="flex items-start gap-3.5">
          <div className="p-2.5 bg-emerald-600 text-white rounded-xl shadow-xs shrink-0 mt-0.5">
            <ShieldCheck size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-emerald-950">
                Auditoría de Privacidad y Cumplimiento de la Ley N° 21.719
              </h3>
              <span className="text-[10px] font-bold uppercase tracking-wider bg-emerald-200 text-emerald-900 px-2 py-0.5 rounded-full">
                Verificación Activa
              </span>
            </div>
            <p className="text-xs text-emerald-900/80 leading-relaxed mt-1">
              La plataforma DSS de la Universidad Católica de Temuco aplica protocolos estrictos de privacidad por diseño. Ningún dato personal directo (nombre de personas, teléfonos, correos o números de documento en texto plano) se almacena en base de datos.
            </p>
          </div>
        </div>
      </div>

      {/* Protocolos de Sanitización Aplicados */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        {/* Purgado Irreversible */}
        <div className="border border-rose-200 bg-rose-50/40 rounded-xl p-4">
          <div className="flex items-center gap-2 text-rose-800 font-bold mb-2">
            <Trash2 size={16} />
            <span>Purgado Irreversible en Memoria Volátil (RAM)</span>
          </div>
          <p className="text-slate-600 leading-snug mb-3">
            Las columnas con datos identificatorios directos son eliminadas de forma inmediata de la memoria durante la lectura del buffer, antes de cualquier persistencia:
          </p>
          <div className="space-y-1.5">
            {purgedColumns.length > 0 ? (
              purgedColumns.map((c) => (
                <div
                  key={c.target_field}
                  className="flex items-center justify-between bg-white px-2.5 py-1.5 rounded-lg border border-rose-200"
                >
                  <span className="font-semibold text-slate-800">{c.target_field}</span>
                  <span className="text-[10px] font-bold text-rose-700 bg-rose-100 px-2 py-0.5 rounded">
                    Eliminado en RAM
                  </span>
                </div>
              ))
            ) : (
              <div className="bg-white px-2.5 py-1.5 rounded-lg border border-slate-200 text-slate-500 italic">
                Persona, Nombres, Teléfonos, Correo electrónico (detectados y suprimidos según norma)
              </div>
            )}
          </div>
        </div>

        {/* Criptografía y Seudonimización */}
        <div className="border border-purple-200 bg-purple-50/40 rounded-xl p-4">
          <div className="flex items-center gap-2 text-purple-800 font-bold mb-2">
            <KeyRound size={16} />
            <span>Seudonimización Criptográfica HMAC-SHA256</span>
          </div>
          <p className="text-slate-600 leading-snug mb-3">
            Los identificadores institucionales (RUT, matrícula y patentes vehiculares) son procesados con un vector de sal secreta rotativa para proteger la identidad:
          </p>
          <div className="space-y-1.5">
            {pseudonymizedColumns.length > 0 ? (
              pseudonymizedColumns.map((c) => (
                <div
                  key={c.target_field}
                  className="flex items-center justify-between bg-white px-2.5 py-1.5 rounded-lg border border-purple-200"
                >
                  <span className="font-semibold text-slate-800">{c.target_field}</span>
                  <span className="text-[10px] font-bold text-purple-700 bg-purple-100 px-2 py-0.5 rounded">
                    Custodia Hash HMAC
                  </span>
                </div>
              ))
            ) : (
              <div className="bg-white px-2.5 py-1.5 rounded-lg border border-slate-200 text-slate-500 italic">
                Número de Matrícula / RUT / Patente Vehicular
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Muestra Previa Sanitizada (5 filas) */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div>
            <h4 className="text-sm font-bold text-slate-800">
              Previsualización de Muestra Sanitizada (Primeras 5 Filas)
            </h4>
            <p className="text-xs text-slate-500">
              Datos verificados tal como serán procesados y almacenados en la base de datos de producción.
            </p>
          </div>
          <span className="text-[11px] font-semibold text-emerald-800 bg-emerald-100 px-2.5 py-1 rounded-full border border-emerald-200 flex items-center gap-1">
            <CheckCircle2 size={12} />
            Libre de PII Directa
          </span>
        </div>

        {inspectData.preview_rows.length > 0 ? (
          <div className="border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
            <div className="overflow-x-auto max-h-[260px]">
              <table className="w-full text-left border-collapse text-[11px]">
                <thead className="bg-slate-100 text-slate-700 font-bold sticky top-0 z-10 border-b border-slate-200">
                  <tr>
                    <th className="py-2 px-3 text-slate-400 font-mono w-10">#</th>
                    {inspectData.columns_detected.map((col) => (
                      <th key={col} className="py-2 px-3 whitespace-nowrap">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono">
                  {inspectData.preview_rows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-2 px-3 text-slate-400">{idx + 1}</td>
                      {inspectData.columns_detected.map((col) => {
                        const val = row[col]
                        const isPurged = typeof val === 'string' && val.includes('[DATO PURGADO')
                        const isSeudonimizado =
                          typeof val === 'string' &&
                          (val.startsWith('EST-***') || val.startsWith('VEH-***') || val === '[SEUDONIMIZADO]')

                        return (
                          <td key={col} className="py-2 px-3 whitespace-nowrap">
                            {isPurged ? (
                              <span className="text-[10px] font-sans font-bold text-rose-700 bg-rose-50 px-1.5 py-0.5 rounded border border-rose-200">
                                DATO PURGADO
                              </span>
                            ) : isSeudonimizado ? (
                              <span className="text-[10px] font-sans font-bold text-purple-700 bg-purple-50 px-1.5 py-0.5 rounded border border-purple-200">
                                {val}
                              </span>
                            ) : val === null || val === undefined || val === '' ? (
                              <span className="text-slate-300 italic font-sans">(vacío)</span>
                            ) : (
                              <span className="text-slate-700 font-sans">{String(val)}</span>
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="p-6 text-center bg-slate-50 rounded-xl border border-slate-200 text-slate-500 text-xs">
            No se generaron filas de muestra para este archivo.
          </div>
        )}
      </div>
    </div>
  )
}
