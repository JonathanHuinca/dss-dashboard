import { describe, expect, it } from 'vitest'
import {
  buildLatestWeekPreset,
  calculateDaysDifference,
  formatDayMonthSpanish,
  formatMonthYearSpanish,
  formatShortDate,
  generateMonthPresets,
} from '../dateRange'

describe('dateRange utilidades y presets', () => {
  it('genera presets mensuales de Marzo a Octubre con último día exacto', () => {
    const presets = generateMonthPresets(2026)
    expect(presets).toHaveLength(8)
    expect(presets[0]).toEqual({
      label: 'Mes de Marzo 2026',
      inicio: '2026-03-01',
      fin: '2026-03-31',
    })
    expect(presets[presets.length - 1].fin).toBe('2026-10-31')
  })

  it('construye la última semana de 7 días corridos y calcula diferencias inclusivas', () => {
    const latest = buildLatestWeekPreset('2026-10-14')
    expect(latest.inicio).toBe('2026-10-08')
    expect(latest.fin).toBe('2026-10-14')
    expect(calculateDaysDifference(latest.inicio, latest.fin)).toBe(7)
    expect(calculateDaysDifference('2026-10-14', '2026-10-08')).toBe(0)
  })

  it('formatea fechas cortas, meses y días en español', () => {
    expect(formatShortDate('2026-10-14')).toBe('14 Oct 2026')
    expect(formatMonthYearSpanish('2026-07-01')).toBe('Julio 2026')
    expect(formatDayMonthSpanish('2026-03-05')).toBe('5 Mar')
  })
})
