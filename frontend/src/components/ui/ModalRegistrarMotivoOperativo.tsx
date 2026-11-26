import React, { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ClipboardEdit, X, Save, AlertCircle } from 'lucide-react'
import { crearContingencia, type ContingenciaCrear } from '../../api/client'
import { obtenerFechaHoyChileIso } from '../../utils/fechaChile'

export interface Props {
  abierto: boolean
  onClose: () => void
  espacioId: 1 | 2
  subespacioInicial?: string
  fechaInicial?: string
  etiquetaRecinto?: string
}

interface CatalogoMotivo {
  valor: string
  etiqueta: string
  cierreDefault: boolean
  tituloBase: string
  notaMl: string
}

const CATALOGO_MOTIVOS: CatalogoMotivo[] = [
  {
    valor: 'falla_sensor',
    etiqueta: 'Falla de torniquete / sensor / sincronización',
    cierreDefault: false,
    tituloBase: 'Falla de lectura o sincronización',
    notaMl: 'Excluye este tramo del entrenamiento ML para evitar distorsionar la demanda esperada.',
  },
  {
    valor: 'apertura_manual',
    etiqueta: 'Apertura manual sin marcaje de tarjeta/patente',
    cierreDefault: false,
    tituloBase: 'Apertura manual sin registro',
    notaMl: 'Excluye este tramo del entrenamiento ML al existir ingresos reales sin registro.',
  },
  {
    valor: 'mantencion_cierre',
    etiqueta: 'Cierre imprevisto o mantención de sala/sector',
    cierreDefault: true,
    tituloBase: 'Cierre por mantención / operativo',
    notaMl: 'Marca suspensión operativa en calendario y excluye la franja del entrenamiento ML.',
  },
  {
    valor: 'sin_demanda',
    etiqueta: 'Recinto abierto con 0 visitantes confirmados',
    cierreDefault: false,
    tituloBase: 'Jornada abierta sin afluencia',
    notaMl: 'Registra demanda nula real; el modelo ML aprende de este comportamiento.',
  },
  {
    valor: 'suspension_sala',
    etiqueta: 'Suspensión puntual de sala / sector',
    cierreDefault: true,
    tituloBase: 'Suspensión puntual de actividades',
    notaMl: 'Marca suspensión de actividades en calendario y excluye la franja del entrenamiento ML.',
  },
  {
    valor: 'otro',
    etiqueta: 'Otra observación operativa',
    cierreDefault: false,
    tituloBase: 'Observación operativa',
    notaMl: 'Anotación informativa en el gráfico sin marcar cierre automático.',
  },
]

const ETIQUETAS_SUBESPACIO: Record<string, string> = {
  todos: '',
  sala_1: 'Sala 1 (CSF02)',
  sala_2: 'Sala 2 (CSF04 Pecera)',
  CSF11: 'Sector CSF11',
  CSF21: 'Sector CSF21',
  CHS01: 'Sector CHS01',
}

const construirTituloSugerido = (tipo: string, subespacio: string, etiquetaRecinto?: string) => {
  const cat = CATALOGO_MOTIVOS.find((m) => m.valor === tipo) || CATALOGO_MOTIVOS[0]
  const alcance = ETIQUETAS_SUBESPACIO[subespacio] || etiquetaRecinto || ''
  return alcance ? `${cat.tituloBase} — ${alcance}` : cat.tituloBase
}

export const ModalRegistrarMotivoOperativo: React.FC<Props> = ({
  abierto,
  onClose,
  espacioId,
  subespacioInicial = 'todos',
  fechaInicial,
  etiquetaRecinto,
}) => {
  const queryClient = useQueryClient()
  const hoyIso = obtenerFechaHoyChileIso()
  const fechaBase = (fechaInicial && fechaInicial.slice(0, 10)) || hoyIso
  const subBase = subespacioInicial || 'todos'

  const [tipo, setTipo] = useState<string>('falla_sensor')
  const [subespacio, setSubespacio] = useState<string>(subBase)
  const [fechaInicio, setFechaInicio] = useState<string>(fechaBase)
  const [fechaFin, setFechaFin] = useState<string>(fechaBase)
  const [horaInicio, setHoraInicio] = useState<string>('')
  const [horaFin, setHoraFin] = useState<string>('')
  const [titulo, setTitulo] = useState<string>(() => construirTituloSugerido('falla_sensor', subBase, etiquetaRecinto))
  const [tituloEditado, setTituloEditado] = useState<boolean>(false)
  const [descripcion, setDescripcion] = useState<string>('')
  const [implicaCierreTotal, setImplicaCierreTotal] = useState<boolean>(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  useEffect(() => {
    if (!abierto) return
    const f = (fechaInicial && fechaInicial.slice(0, 10)) || hoyIso
    const s = subespacioInicial || 'todos'
    setTipo('falla_sensor')
    setSubespacio(s)
    setFechaInicio(f)
    setFechaFin(f)
    setHoraInicio('')
    setHoraFin('')
    setTitulo(construirTituloSugerido('falla_sensor', s, etiquetaRecinto))
    setTituloEditado(false)
    setDescripcion('')
    setImplicaCierreTotal(false)
    setErrorMsg(null)
  }, [abierto, espacioId, subespacioInicial, fechaInicial, etiquetaRecinto])

  const guardarMutation = useMutation({
    mutationFn: (payload: ContingenciaCrear) => crearContingencia(payload),
    onSuccess: () => {
      const claves = [
        'calendario-resumen-anual',
        'contingencias',
        'calendar-events',
        'calendar-status',
        'attendance-presence-curve',
        'attendance-kpis',
        'occupancy-realtime',
        'hourly-flow',
        'vehicle-presence-curve',
        'vehicle-hourly-flow',
        'vehicle-kpis',
        'forecast-attendance',
        'forecast-parking',
      ]
      claves.forEach((k) => queryClient.invalidateQueries({ queryKey: [k] }))
      onClose()
    },
    onError: (err: any) => {
      setErrorMsg(err?.response?.data?.detail || 'No se pudo registrar el motivo operativo.')
    },
  })

  if (!abierto) return null

  const catActiva = CATALOGO_MOTIVOS.find((m) => m.valor === tipo) || CATALOGO_MOTIVOS[0]

  const handleCambioTipo = (nuevoTipo: string) => {
    setTipo(nuevoTipo)
    const cat = CATALOGO_MOTIVOS.find((m) => m.valor === nuevoTipo)
    if (cat) {
      setImplicaCierreTotal(cat.cierreDefault)
      if (!tituloEditado) {
        setTitulo(construirTituloSugerido(nuevoTipo, subespacio, etiquetaRecinto))
      }
    }
  }

  const handleCambioSubespacio = (nuevoSub: string) => {
    setSubespacio(nuevoSub)
    if (!tituloEditado) {
      setTitulo(construirTituloSugerido(tipo, nuevoSub, etiquetaRecinto))
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!titulo.trim()) {
      setErrorMsg('Debe indicar un título breve para el registro.')
      return
    }
    if (fechaFin < fechaInicio) {
      setErrorMsg('La fecha de término no puede ser anterior a la de inicio.')
      return
    }
    setErrorMsg(null)
    guardarMutation.mutate({
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
      tipo,
      titulo: titulo.trim(),
      descripcion: descripcion.trim() || null,
      espacio_id: espacioId,
      subespacio: subespacio || 'todos',
      hora_inicio: horaInicio || null,
      hora_fin: horaFin || null,
      carreras_afectadas: 'Todas',
      implica_cierre_total: implicaCierreTotal,
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-lg w-full overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/60">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-amber-50 text-amber-700 rounded-lg border border-amber-200">
              <ClipboardEdit size={17} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Registrar motivo u observación operativa</h3>
              <span className="text-[11px] text-slate-500">
                {espacioId === 1 ? 'Biblioteca Campus San Francisco' : 'Estacionamiento Campus San Francisco'}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-600 rounded-lg transition cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-3.5 text-xs">
          {errorMsg && (
            <div className="p-2.5 bg-rose-50 text-rose-700 rounded-xl border border-rose-200 flex items-center gap-2">
              <AlertCircle size={14} className="shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          <div>
            <label className="block font-semibold text-slate-700 mb-1">Motivo clasificado</label>
            <select
              value={tipo}
              onChange={(e) => handleCambioTipo(e.target.value)}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-amber-200 focus:outline-none"
            >
              {CATALOGO_MOTIVOS.map((m) => (
                <option key={m.valor} value={m.valor}>
                  {m.etiqueta}
                </option>
              ))}
            </select>
            <p className="text-[11px] text-slate-500 mt-1">{catActiva.notaMl}</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Sala / Sector afectado</label>
              <select
                value={subespacio}
                onChange={(e) => handleCambioSubespacio(e.target.value)}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-amber-200 focus:outline-none"
              >
                {espacioId === 1 ? (
                  <>
                    <option value="todos">Biblioteca Completa (Todas las Salas)</option>
                    <option value="sala_1">Sala 1: CSF02 (2° Piso)</option>
                    <option value="sala_2">Sala 2: CSF04 Pecera (1° Piso)</option>
                  </>
                ) : (
                  <>
                    <option value="todos">Estacionamiento Completo</option>
                    <option value="CSF11">Sector CSF11 — Edificio 11</option>
                    <option value="CSF21">Sector CSF21 — Edificio 21</option>
                    <option value="CHS01">Sector CHS01 — Hosp. Simulación</option>
                  </>
                )}
              </select>
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Título corto</label>
              <input
                type="text"
                required
                value={titulo}
                onChange={(e) => {
                  setTitulo(e.target.value)
                  setTituloEditado(true)
                }}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-amber-200 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Fecha inicio</label>
              <input
                type="date"
                required
                value={fechaInicio}
                onChange={(e) => setFechaInicio(e.target.value)}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-amber-200 focus:outline-none"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Fecha término</label>
              <input
                type="date"
                required
                value={fechaFin}
                onChange={(e) => setFechaFin(e.target.value)}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-amber-200 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Hora inicio (opcional)</label>
              <input
                type="time"
                value={horaInicio}
                onChange={(e) => setHoraInicio(e.target.value)}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-amber-200 focus:outline-none"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Hora término (opcional)</label>
              <input
                type="time"
                value={horaFin}
                onChange={(e) => setHoraFin(e.target.value)}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-amber-200 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="block font-semibold text-slate-700 mb-1">Detalle / Qué ocurrió</label>
            <textarea
              rows={2}
              placeholder="Ej. Torniquete de Sala 2 desconectado durante la jornada o puerta liberada manualmente..."
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-800 focus:bg-white focus:ring-2 focus:ring-amber-200 focus:outline-none resize-none"
            />
          </div>

          <label className="flex items-center gap-2 p-2.5 bg-slate-50 rounded-xl border border-slate-200 cursor-pointer">
            <input
              type="checkbox"
              checked={implicaCierreTotal}
              onChange={(e) => setImplicaCierreTotal(e.target.checked)}
              className="rounded text-amber-600 focus:ring-amber-500 h-4 w-4 cursor-pointer"
            />
            <span className="text-slate-700 font-medium">
              El recinto / sala permaneció cerrado o sin acceso durante ese período
            </span>
          </label>

          <div className="pt-2 border-t border-slate-100 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-2 font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition cursor-pointer"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={guardarMutation.isPending}
              className="flex items-center gap-1.5 px-4 py-2 bg-uct-blue-primary text-white rounded-xl font-semibold hover:bg-uct-navy transition shadow-xs cursor-pointer disabled:opacity-50"
            >
              <Save size={14} />
              <span>{guardarMutation.isPending ? 'Guardando...' : 'Guardar registro'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
