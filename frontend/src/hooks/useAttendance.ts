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
} from '../api/client'

const LIVE_INTERVAL = 30_000

export function useAttendanceKpis() {
  return useQuery({ queryKey: ['attendance-kpis'], queryFn: fetchAttendanceKpis, staleTime: 5 * 60_000 })
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

export function useAttendanceHourlyFlow(fechaInicio?: string, fechaFin?: string) {
  return useQuery({
    queryKey: ['attendance-hourly-flow', fechaInicio, fechaFin],
    queryFn: () => fetchAttendanceHourlyFlow(fechaInicio, fechaFin),
    staleTime: 5 * 60_000,
  })
}

export function useHeatmap() {
  return useQuery({ queryKey: ['heatmap'], queryFn: fetchHeatmap, staleTime: 60 * 60_000 })
}

export function useForecastAttendance() {
  return useQuery({ queryKey: ['forecast-attendance'], queryFn: fetchForecastAttendance, staleTime: 60 * 60_000 })
}

export function useAlerts() {
  return useQuery({ queryKey: ['predictive-alerts'], queryFn: fetchAlerts, refetchInterval: 60_000 })
}

export function usePeakValley() {
  return useQuery({ queryKey: ['peak-valley'], queryFn: fetchPeakValley, staleTime: 10 * 60_000 })
}

export function useWeeklyEvolution() {
  return useQuery({ queryKey: ['weekly-evolution'], queryFn: fetchWeeklyEvolution, staleTime: 10 * 60_000 })
}

export function useMonthlyVolume() {
  return useQuery({ queryKey: ['monthly-volume'], queryFn: fetchMonthlyVolume, staleTime: 10 * 60_000 })
}

export function useAcademicMilestones() {
  return useQuery({ queryKey: ['academic-milestones'], queryFn: fetchAcademicMilestones, staleTime: 10 * 60_000 })
}

export function useDoorsUsage() {
  return useQuery({ queryKey: ['doors-usage'], queryFn: fetchDoorsUsage, staleTime: 10 * 60_000 })
}

export function useCheckinsDistribution() {
  return useQuery({ queryKey: ['checkins-distribution'], queryFn: fetchCheckinsDistribution, staleTime: 10 * 60_000 })
}

export function useForecast14Days(espacioId: number = 1) {
  return useQuery({
    queryKey: ['forecast-14days', espacioId],
    queryFn: () => fetchForecast14Days(espacioId),
    staleTime: 30 * 60_000,
  })
}

export function useVisitProfiles(espacioId: number = 1) {
  return useQuery({
    queryKey: ['visit-profiles', espacioId],
    queryFn: () => fetchVisitProfiles(espacioId),
    staleTime: 30 * 60_000,
  })
}


