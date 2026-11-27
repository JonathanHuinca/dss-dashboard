import { describe, expect, it } from 'vitest'
import {
  ZONA_HORARIA_CHILE,
  diferenciaDiasIso,
  formatearFechaHoraChile,
  obtenerFechaHoyChileIso,
  sumarDiasIso,
  ultimoDiaMesIso,
} from '../fechaChile'

describe('fechaChile utilidades', () => {
  it('mantiene America/Santiago como zona horaria oficial', () => {
    expect(ZONA_HORARIA_CHILE).toBe('America/Santiago')
  })

  it('formatea fechas ISO UTC a hora local Chile y respeta fallback', () => {
    expect(formatearFechaHoraChile(null, undefined, 'N/D')).toBe('N/D')
    expect(formatearFechaHoraChile('no-es-fecha')).toBe('no-es-fecha')
    const txt = formatearFechaHoraChile('2026-10-14T15:30:00Z')
    expect(txt).toContain('14')
    expect(txt).toContain('2026')
  })

  it('obtiene ISO YYYY-MM-DD en horario de Chile sin desfase', () => {
    const ref = new Date('2026-10-15T02:00:00Z')
    expect(obtenerFechaHoyChileIso(ref)).toBe('2026-10-14')
  })

  it('opera sumas, diferencias de días y fin de mes en años bisiestos', () => {
    expect(sumarDiasIso('2026-10-14', -6)).toBe('2026-10-08')
    expect(diferenciaDiasIso('2026-10-08', '2026-10-14')).toBe(6)
    expect(ultimoDiaMesIso(2024, 2)).toBe(29)
    expect(ultimoDiaMesIso(2026, 2)).toBe(28)
  })
})
