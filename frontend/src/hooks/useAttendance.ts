import { useQuery } from '@tanstack/react-query'
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

const LIVE_INTERVAL = 30_000

export function useAttendanceKpis(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string) {
  return useQuery({
    queryKey: ['attendance-kpis', fechaInicio, fechaFin, filters],
    queryFn: () => fetchAttendanceKpis(fechaInicio, fechaFin, filters),
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  })
}

export function useOccupancyRealtime() {
  return useQuery({
    queryKey: ['occupancy-realtime'],
    queryFn: fetchOccupancyRealtime,
    refetchInterval: LIVE_INTERVAL,
    refetchIntervalInBackground: false,
    staleTime: LIVE_INTERVAL - 5000,
  })
}

export function useAttendanceHourlyFlow(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string) {
  return useQuery({
    queryKey: ['attendance-hourly-flow', fechaInicio, fechaFin, filters],
    queryFn: () => fetchAttendanceHourlyFlow(fechaInicio, fechaFin, filters),
    staleTime: 60_000,
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
    queryFn: () => fetchHeatmap(fechaInicio, fechaFin, espacioId, filters),
    staleTime: 10 * 60_000,
    ...opts,
  })
}

export function useForecastAttendance(sala: string = 'todas') {
  return useQuery({
    queryKey: ['forecast-attendance', sala],
    queryFn: () => fetchForecastAttendance(sala),
    staleTime: 60 * 60_000,
  })
}

export function useAlerts() {
  return useQuery({ queryKey: ['predictive-alerts'], queryFn: fetchAlerts, refetchInterval: 60_000 })
}

export function usePeakValley(fechaInicio?: string, fechaFin?: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['peak-valley', fechaInicio, fechaFin],
    queryFn: () => fetchPeakValley(fechaInicio, fechaFin),
    staleTime: 10 * 60_000,
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
    queryFn: () => fetchWeeklyEvolution(fechaInicio, fechaFin, espacioId, filters),
    staleTime: 10 * 60_000,
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
    queryFn: () => fetchMonthlyVolume(fechaInicio, fechaFin, espacioId, filters),
    staleTime: 10 * 60_000,
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
    queryFn: () => fetchAcademicMilestones(fechaInicio, fechaFin, espacioId, filters),
    staleTime: 10 * 60_000,
    ...opts,
  })
}

export function useDoorsUsage(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['doors-usage', fechaInicio, fechaFin, filters],
    queryFn: () => fetchDoorsUsage(fechaInicio, fechaFin, filters),
    staleTime: 10 * 60_000,
    ...opts,
  })
}

export function useCheckinsDistribution(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['checkins-distribution', fechaInicio, fechaFin, filters],
    queryFn: () => fetchCheckinsDistribution(fechaInicio, fechaFin, filters),
    staleTime: 10 * 60_000,
    ...opts,
  })
}

export function useForecast14Days(espacioId: number = 1, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['forecast-14days', espacioId],
    queryFn: () => fetchForecast14Days(espacioId),
    staleTime: 30 * 60_000,
    ...opts,
  })
}

export function useVisitProfiles(espacioId: number = 1, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['visit-profiles', espacioId],
    queryFn: () => fetchVisitProfiles(espacioId),
    staleTime: 30 * 60_000,
    ...opts,
  })
}

export function useSalasBiblioteca(espacioId: number = 1) {
  return useQuery({
    queryKey: ['salas-biblioteca', espacioId],
    queryFn: () => fetchSalasBiblioteca(espacioId),
    staleTime: 60 * 60_000,
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
    queryFn: () => fetchRoomsComparison(fechaInicio, fechaFin, filters, espacioId),
    staleTime: 10 * 60_000,
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
    queryFn: () => fetchDailyAverageAttendance(fechaInicio, fechaFin, filters, espacioId),
    staleTime: 10 * 60_000,
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
    queryFn: () => fetchCurricularDistribution(fechaInicio, fechaFin, filters, espacioId),
    staleTime: 30 * 60_000,
    ...opts,
  })
}

export function useAvailableFilters(espacioId: number = 1) {
  return useQuery({
    queryKey: ['available-filters', espacioId],
    queryFn: () => fetchAvailableFilters(espacioId),
    staleTime: 30 * 60_000,
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
    queryFn: () => fetchVisitProfilesDonut(fechaInicio, fechaFin, filters, espacioId),
    staleTime: 10 * 60_000,
    ...opts,
  })
}



