import { useQuery, keepPreviousData } from '@tanstack/react-query'
import {
  fetchAttendanceKpis,
  fetchOccupancyRealtime,
  fetchAttendanceHourlyFlow,
  fetchHeatmap,
  fetchForecastAttendance,
  fetchAlerts,
  fetchPeakValley,
  fetchWeeklyEvolution,
  fetchMonthlyVolume,
  fetchAcademicMilestones,
  fetchDoorsUsage,
  fetchCheckinsDistribution,
  fetchForecast14Days,
  fetchVisitProfiles,
  fetchSalasBiblioteca,
  fetchRoomsComparison,
  fetchDailyAverageAttendance,
  fetchCurricularDistribution,
  fetchAvailableFilters,
  fetchVisitProfilesDonut,
  DataFilters,
} from '../api/client'
import { opcionesConsultaAnalitica } from './opcionesConsulta'

const LIVE_INTERVAL = 30_000

export function useAttendanceKpis(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string) {
  return useQuery({
    queryKey: ['attendance-kpis', fechaInicio, fechaFin, filters],
    queryFn: ({ signal }) => fetchAttendanceKpis(fechaInicio, fechaFin, filters, signal),
    ...opcionesConsultaAnalitica(),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  })
}

export function useOccupancyRealtime() {
  return useQuery({
    queryKey: ['occupancy-realtime'],
    queryFn: ({ signal }) => fetchOccupancyRealtime(signal),
    refetchInterval: LIVE_INTERVAL,
    refetchIntervalInBackground: false,
    staleTime: LIVE_INTERVAL - 5000,
    placeholderData: keepPreviousData,
  })
}

export function useAttendanceHourlyFlow(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string) {
  return useQuery({
    queryKey: ['attendance-hourly-flow', fechaInicio, fechaFin, filters],
    queryFn: ({ signal }) => fetchAttendanceHourlyFlow(fechaInicio, fechaFin, filters, signal),
    ...opcionesConsultaAnalitica(),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  })
}


export function useHeatmap(
  fechaInicio?: string,
  fechaFin?: string,
  espacioId: number = 1,
  filters?: DataFilters | string,
  opts?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ['heatmap', espacioId, fechaInicio, fechaFin, filters],
    queryFn: ({ signal }) => fetchHeatmap(fechaInicio, fechaFin, espacioId, filters, signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useForecastAttendance(sala: string = 'todas') {
  return useQuery({
    queryKey: ['forecast-attendance', sala],
    queryFn: ({ signal }) => fetchForecastAttendance(sala, signal),
    ...opcionesConsultaAnalitica(60 * 60_000),
  })
}

export function useAlerts() {
  return useQuery({
    queryKey: ['predictive-alerts'],
    queryFn: ({ signal }) => fetchAlerts(signal),
    refetchInterval: 60_000,
  })
}

export function usePeakValley(fechaInicio?: string, fechaFin?: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['peak-valley', fechaInicio, fechaFin],
    queryFn: ({ signal }) => fetchPeakValley(fechaInicio, fechaFin, signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useWeeklyEvolution(
  fechaInicio?: string,
  fechaFin?: string,
  espacioId: number = 1,
  filters?: DataFilters | string,
  opts?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ['weekly-evolution', espacioId, fechaInicio, fechaFin, filters],
    queryFn: ({ signal }) => fetchWeeklyEvolution(fechaInicio, fechaFin, espacioId, filters, signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useMonthlyVolume(
  fechaInicio?: string,
  fechaFin?: string,
  espacioId: number = 1,
  filters?: DataFilters | string,
  opts?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ['monthly-volume', espacioId, fechaInicio, fechaFin, filters],
    queryFn: ({ signal }) => fetchMonthlyVolume(fechaInicio, fechaFin, espacioId, filters, signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useAcademicMilestones(
  fechaInicio?: string,
  fechaFin?: string,
  espacioId: number = 1,
  filters?: DataFilters | string,
  opts?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ['academic-milestones', espacioId, fechaInicio, fechaFin, filters],
    queryFn: ({ signal }) => fetchAcademicMilestones(fechaInicio, fechaFin, espacioId, filters, signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useDoorsUsage(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['doors-usage', fechaInicio, fechaFin, filters],
    queryFn: ({ signal }) => fetchDoorsUsage(fechaInicio, fechaFin, filters, signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useCheckinsDistribution(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['checkins-distribution', fechaInicio, fechaFin, filters],
    queryFn: ({ signal }) => fetchCheckinsDistribution(fechaInicio, fechaFin, filters, signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useForecast14Days(espacioId: number = 1, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['forecast-14days', espacioId],
    queryFn: ({ signal }) => fetchForecast14Days(espacioId, signal),
    ...opcionesConsultaAnalitica(30 * 60_000),
    ...opts,
  })
}

export function useVisitProfiles(espacioId: number = 1, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['visit-profiles', espacioId],
    queryFn: ({ signal }) => fetchVisitProfiles(espacioId, signal),
    ...opcionesConsultaAnalitica(30 * 60_000),
    ...opts,
  })
}

export function useSalasBiblioteca(espacioId: number = 1) {
  return useQuery({
    queryKey: ['salas-biblioteca', espacioId],
    queryFn: ({ signal }) => fetchSalasBiblioteca(espacioId, signal),
    ...opcionesConsultaAnalitica(60 * 60_000),
  })
}

export function useRoomsComparison(
  fechaInicio?: string,
  fechaFin?: string,
  filters?: DataFilters | string,
  espacioId: number = 1,
  opts?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ['rooms-comparison', fechaInicio, fechaFin, filters, espacioId],
    queryFn: ({ signal }) => fetchRoomsComparison(fechaInicio, fechaFin, filters, espacioId, signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useDailyAverageAttendance(
  fechaInicio?: string,
  fechaFin?: string,
  filters?: DataFilters | string,
  espacioId: number = 1,
  opts?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ['daily-average-attendance', fechaInicio, fechaFin, filters, espacioId],
    queryFn: ({ signal }) => fetchDailyAverageAttendance(fechaInicio, fechaFin, filters, espacioId, signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useCurricularDistribution(
  fechaInicio?: string,
  fechaFin?: string,
  filters?: DataFilters,
  espacioId: number = 1,
  opts?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: ['curricular-distribution', fechaInicio, fechaFin, filters, espacioId],
    queryFn: ({ signal }) => fetchCurricularDistribution(fechaInicio, fechaFin, filters, espacioId, signal),
    ...opcionesConsultaAnalitica(30 * 60_000),
    ...opts,
  })
}

export function useAvailableFilters(espacioId: number = 1) {
  return useQuery({
    queryKey: ['available-filters', espacioId],
    queryFn: ({ signal }) => fetchAvailableFilters(espacioId, signal),
    ...opcionesConsultaAnalitica(30 * 60_000),
  })
}

export function useVisitProfilesDonut(
  fechaInicio?: string,
  fechaFin?: string,
  filters?: DataFilters | string,
  espacioId: number = 1,
  opts?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ['visit-profiles-donut', fechaInicio, fechaFin, filters, espacioId],
    queryFn: ({ signal }) => fetchVisitProfilesDonut(fechaInicio, fechaFin, filters, espacioId, signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}
