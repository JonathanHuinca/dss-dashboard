export interface DateRange {
  label: string
  inicio?: string
  fin?: string
}

export const DATE_PRESETS: DateRange[] = [
  { label: 'Última semana registrada (Ago 10 - Ago 17)', inicio: '2026-08-10', fin: '2026-08-17' },
  { label: 'Semana de Exámenes (Jul 06 - Jul 13)', inicio: '2026-07-06', fin: '2026-07-13' },
  { label: 'Mes de Junio 2026', inicio: '2026-06-01', fin: '2026-06-30' },
  { label: 'Mes de Mayo 2026', inicio: '2026-05-01', fin: '2026-05-31' },
  { label: 'Mes de Abril 2026', inicio: '2026-04-01', fin: '2026-04-30' },
  { label: 'Inicio Semestre (Mar 16 - Mar 31)', inicio: '2026-03-16', fin: '2026-03-31' },
  { label: 'Historial Semestre Completo (Mar - Ago)', inicio: '2026-03-01', fin: '2026-08-17' },
]
