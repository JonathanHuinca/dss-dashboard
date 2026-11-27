import { keepPreviousData } from '@tanstack/react-query'

const CINCO_MINUTOS = 1000 * 60 * 5
const TREINTA_MINUTOS = 1000 * 60 * 30

/** Opciones comunes de consultas analíticas: caché de 5 min, retención 30 min y sin parpadeo al cambiar de filtro. */
export function opcionesConsultaAnalitica(staleTime: number = CINCO_MINUTOS) {
  return {
    staleTime,
    gcTime: Math.max(TREINTA_MINUTOS, staleTime),
    placeholderData: keepPreviousData,
  }
}

