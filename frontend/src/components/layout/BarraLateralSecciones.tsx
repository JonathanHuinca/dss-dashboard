import React, { useState, useEffect } from 'react'
import {
  ChevronRight,
  ChevronLeft,
  Layers,
  LayoutGrid,
  Check,
  ArrowUp,
  ArrowDown,
} from 'lucide-react'
import { useAssistant } from '../../context/AssistantContext'

export interface SeccionModuloItem {
  id: string
  numero: number
  titulo: string
  subtitulo: string
  icono: React.ElementType
  cantidadGraficos: number
}

export interface PropiedadesBarraLateralSecciones {
  tituloModulo: string
  secciones: SeccionModuloItem[]
  seccionActiva: string | 'todas'
  alCambiarSeccion: (seccionId: string | 'todas') => void
  alAlternarApertura?: (abierta: boolean) => void
}

const CLAVE_STORAGE_BARRA = 'uct_barra_lateral_abierta'

export function BarraLateralSecciones({
  tituloModulo,
  secciones,
  seccionActiva,
  alCambiarSeccion,
  alAlternarApertura,
}: PropiedadesBarraLateralSecciones) {
  const { isOpen: asistenteAbierto } = useAssistant()

  const [barraAbierta, setBarraAbierta] = useState<boolean>(() => {
    if (typeof window === 'undefined') return true
    try {
      const guardado = localStorage.getItem(CLAVE_STORAGE_BARRA)
      return guardado !== null ? guardado === 'true' : true
    } catch {
      return true
    }
  })

  const abiertaEfectiva = barraAbierta && !asistenteAbierto

  useEffect(() => {
    alAlternarApertura?.(abiertaEfectiva)
  }, [abiertaEfectiva, alAlternarApertura])

  const alternarBarraLateral = () => {
    setBarraAbierta(prev => {
      const nuevoEstado = !prev
      try {
        localStorage.setItem(CLAVE_STORAGE_BARRA, String(nuevoEstado))
      } catch { }
      return nuevoEstado
    })
  }

  const indiceActual = secciones.findIndex(s => s.id === seccionActiva)
  const totalGraficosModulo = secciones.reduce((acc, s) => acc + s.cantidadGraficos, 0)

  const irSeccionAnterior = () => {
    if (secciones.length === 0) return
    if (seccionActiva === 'todas' || indiceActual <= 0) {
      alCambiarSeccion(secciones[secciones.length - 1].id)
    } else {
      alCambiarSeccion(secciones[indiceActual - 1].id)
    }
  }

  const irSeccionSiguiente = () => {
    if (secciones.length === 0) return
    if (seccionActiva === 'todas' || indiceActual === -1 || indiceActual >= secciones.length - 1) {
      alCambiarSeccion(secciones[0].id)
    } else {
      alCambiarSeccion(secciones[indiceActual + 1].id)
    }
  }

  if (asistenteAbierto) {
    return null
  }

  return (
    <aside
      aria-label={`Navegación de secciones de ${tituloModulo}`}
      className="fixed left-0 top-28 z-30 flex items-start pointer-events-none"
    >
      {/* Pestaña compacta cuando la barra lateral está oculta/plegada */}
      {!abiertaEfectiva && (
        <button
          type="button"
          onClick={alternarBarraLateral}
          title="Mostrar panel de secciones del módulo"
          className="pointer-events-auto flex flex-col items-center gap-2 py-3.5 px-2 bg-[#003865] hover:bg-[#00284d] text-white rounded-r-2xl shadow-lg border border-l-0 border-[#C59B27]/50 transition-all cursor-pointer group"
        >
          <ChevronRight size={16} className="text-[#C59B27] group-hover:translate-x-0.5 transition-transform" />
          <Layers size={15} className="text-white/90" />
          <span
            className="text-[10px] font-bold uppercase tracking-widest text-white/95 py-1"
            style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}
          >
            Secciones ({secciones.length})
          </span>
        </button>
      )}

      {/* Panel expandido de ~260px */}
      {abiertaEfectiva && (
        <div className="pointer-events-auto w-[264px] max-h-[calc(100vh-8.5rem)] flex flex-col bg-white/95 backdrop-blur-md border border-l-0 border-slate-200/90 rounded-r-2xl shadow-xl overflow-hidden transition-all">
          {/* Cabecera institucional UCT */}
          <div className="bg-gradient-to-r from-[#003865] to-[#004b87] px-3.5 py-3 text-white flex items-center justify-between border-b border-[#C59B27]/40">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-6 h-6 rounded-lg bg-[#C59B27]/20 border border-[#C59B27]/40 flex items-center justify-center shrink-0">
                <Layers size={13} className="text-[#C59B27]" />
              </div>
              <div className="truncate">
                <span className="block text-[10px] uppercase tracking-wider text-[#C59B27] font-bold leading-none">
                  Secciones del Módulo
                </span>
                <h4 className="text-xs font-bold text-white truncate mt-0.5">
                  {tituloModulo}
                </h4>
              </div>
            </div>
            <button
              type="button"
              onClick={alternarBarraLateral}
              title="Ocultar barra lateral de secciones"
              className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors cursor-pointer shrink-0"
            >
              <ChevronLeft size={15} />
            </button>
          </div>

          {/* Botón superior: Ver Todas las Secciones */}
          <div className="p-2.5 border-b border-slate-100 bg-slate-50/70">
            <button
              type="button"
              onClick={() => alCambiarSeccion('todas')}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                seccionActiva === 'todas'
                  ? 'bg-[#003865] text-white shadow-xs ring-1 ring-[#C59B27]/50'
                  : 'bg-white text-slate-700 hover:bg-slate-100 border border-slate-200/80'
              }`}
            >
              <span className="flex items-center gap-2">
                <LayoutGrid size={14} className={seccionActiva === 'todas' ? 'text-[#C59B27]' : 'text-[#003865]'} />
                <span>Ver Todas las Secciones</span>
              </span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded-md font-mono font-bold ${
                  seccionActiva === 'todas'
                    ? 'bg-[#C59B27] text-slate-950'
                    : 'bg-slate-100 text-slate-600'
                }`}
              >
                {totalGraficosModulo}
              </span>
            </button>
          </div>

          {/* Lista de secciones del módulo */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {secciones.map(item => {
              const IconoSeccion = item.icono
              const estaActiva = seccionActiva === item.id
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => alCambiarSeccion(item.id)}
                  className={`w-full text-left px-2.5 py-2 rounded-xl transition-all cursor-pointer border flex items-start gap-2.5 group ${
                    estaActiva
                      ? 'bg-[#003865]/8 border-[#003865]/30 shadow-2xs'
                      : 'bg-white hover:bg-slate-50 border-transparent hover:border-slate-200/70'
                  }`}
                >
                  <div
                    className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 mt-0.5 text-[11px] font-bold transition-colors ${
                      estaActiva
                        ? 'bg-[#003865] text-[#C59B27]'
                        : 'bg-slate-100 text-slate-600 group-hover:bg-[#003865]/10 group-hover:text-[#003865]'
                    }`}
                  >
                    {estaActiva ? <Check size={12} /> : item.numero}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <span
                        className={`text-xs font-bold truncate ${
                          estaActiva ? 'text-[#003865]' : 'text-slate-700 group-hover:text-slate-900'
                        }`}
                      >
                        {item.titulo}
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono font-semibold shrink-0 ${
                          estaActiva
                            ? 'bg-[#003865] text-white'
                            : 'bg-slate-100 text-slate-500'
                        }`}
                        title={`${item.cantidadGraficos} visualizaciones en esta sección`}
                      >
                        {item.cantidadGraficos}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 mt-0.5">
                      <IconoSeccion
                        size={11}
                        className={estaActiva ? 'text-[#C59B27] shrink-0' : 'text-slate-400 shrink-0'}
                      />
                      <p className="text-[10px] text-slate-500 truncate">
                        {item.subtitulo}
                      </p>
                    </div>
                  </div>
                </button>
              )
            })}
          </div>

          {/* Controles rápidos Anterior / Siguiente */}
          <div className="px-2.5 py-2 bg-slate-50 border-t border-slate-200/80 flex items-center justify-between gap-1.5">
            <button
              type="button"
              onClick={irSeccionAnterior}
              className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 rounded-lg bg-white hover:bg-slate-100 border border-slate-200/80 text-[11px] font-semibold text-slate-700 transition-colors cursor-pointer"
              title="Ir a la sección anterior"
            >
              <ArrowUp size={12} className="text-[#003865]" />
              <span>Anterior</span>
            </button>
            <button
              type="button"
              onClick={irSeccionSiguiente}
              className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 rounded-lg bg-white hover:bg-slate-100 border border-slate-200/80 text-[11px] font-semibold text-slate-700 transition-colors cursor-pointer"
              title="Ir a la sección siguiente"
            >
              <span>Siguiente</span>
              <ArrowDown size={12} className="text-[#003865]" />
            </button>
          </div>
        </div>
      )}
    </aside>
  )
}

