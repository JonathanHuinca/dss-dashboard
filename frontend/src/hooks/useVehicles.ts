import { useQuery } from '@tanstack/react-query'
import {
  fetchVehicleKpis,
  fetchParkingOccupancy,
  fetchVehicleHourlyFlow,
  fetchFleetComposition,
  fetchForecastParking,
  fetchCameraStats,
  fetchVehicleDailyEvolution,
  fetchVehicleAcademicMilestones,
  fetchIntercampusMobility,
  fetchBehavioralClusters,
  DataFilters,
} from '../api/client'

const LIVE_INTERVAL = 60_000

export function useVehicleKpis(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string, sector?: string) {
  return useQuery({
    queryKey: ['vehicle-kpis', fechaInicio, fechaFin, filters, sector],
    queryFn: () => fetchVehicleKpis(fechaInicio, fechaFin, filters, sector),
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  })
}


export function useParkingOccupancy(sector?: string) {
  return useQuery({
    queryKey: ['parking-occupancy', sector],
    queryFn: () => fetchParkingOccupancy(sector),
    refetchInterval: LIVE_INTERVAL,
    refetchIntervalInBackground: false,
    staleTime: LIVE_INTERVAL - 5000,
  })
}

export function useVehicleHourlyFlow(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string, sector?: string) {
  return useQuery({
    queryKey: ['vehicle-hourly-flow', fechaInicio, fechaFin, filters, sector],
    queryFn: () => fetchVehicleHourlyFlow(fechaInicio, fechaFin, filters, sector),
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  })
}

export function useFleetComposition(fechaInicio?: string, fechaFin?: string, sector?: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['fleet-composition', fechaInicio, fechaFin, sector],
    queryFn: () => fetchFleetComposition(fechaInicio, fechaFin, sector),
    staleTime: 30 * 60_000,
    ...opts,
  })
}

export function useForecastParking(opts?: { enabled?: boolean }) {
  return useQuery({ queryKey: ['forecast-parking'], queryFn: fetchForecastParking, staleTime: 60 * 60_000, ...opts })
}

export function useCameraStats(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string, sector?: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['camera-stats', fechaInicio, fechaFin, filters, sector],
    queryFn: () => fetchCameraStats(fechaInicio, fechaFin, filters, sector),
    staleTime: 10 * 60_000,
    ...opts,
  })
}

export function useVehicleDailyEvolution(fechaInicio?: string, fechaFin?: string, sector?: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['vehicle-daily-evolution', fechaInicio, fechaFin, sector],
    queryFn: () => fetchVehicleDailyEvolution(fechaInicio, fechaFin, sector),
    staleTime: 10 * 60_000,
    ...opts,
  })
}

export function useVehicleAcademicMilestones(opts?: { enabled?: boolean }) {
  return useQuery({ queryKey: ['vehicle-academic-milestones'], queryFn: fetchVehicleAcademicMilestones, staleTime: 10 * 60_000, ...opts })
}

export function useIntercampusMobility(opts?: { enabled?: boolean }) {
  return useQuery({ queryKey: ['intercampus-mobility'], queryFn: fetchIntercampusMobility, staleTime: 10 * 60_000, ...opts })
}

export function useBehavioralClusters(opts?: { enabled?: boolean }) {
  return useQuery({ queryKey: ['behavioral-clusters'], queryFn: fetchBehavioralClusters, staleTime: 30 * 60_000, ...opts })
}


