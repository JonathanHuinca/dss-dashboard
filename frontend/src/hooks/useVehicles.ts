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
} from '../api/client'

const LIVE_INTERVAL = 60_000

export function useVehicleKpis() {
  return useQuery({ queryKey: ['vehicle-kpis'], queryFn: fetchVehicleKpis, staleTime: 5 * 60_000 })
}

export function useParkingOccupancy() {
  return useQuery({
    queryKey: ['parking-occupancy'],
    queryFn: fetchParkingOccupancy,
    refetchInterval: LIVE_INTERVAL,
    refetchIntervalInBackground: false,
    staleTime: LIVE_INTERVAL - 5000,
  })
}

export function useVehicleHourlyFlow(fechaInicio?: string, fechaFin?: string) {
  return useQuery({
    queryKey: ['vehicle-hourly-flow', fechaInicio, fechaFin],
    queryFn: () => fetchVehicleHourlyFlow(fechaInicio, fechaFin),
    staleTime: 5 * 60_000,
  })
}

export function useFleetComposition() {
  return useQuery({ queryKey: ['fleet-composition'], queryFn: fetchFleetComposition, staleTime: 30 * 60_000 })
}

export function useForecastParking() {
  return useQuery({ queryKey: ['forecast-parking'], queryFn: fetchForecastParking, staleTime: 60 * 60_000 })
}

export function useCameraStats() {
  return useQuery({ queryKey: ['camera-stats'], queryFn: fetchCameraStats, staleTime: 10 * 60_000 })
}

export function useVehicleDailyEvolution() {
  return useQuery({ queryKey: ['vehicle-daily-evolution'], queryFn: fetchVehicleDailyEvolution, staleTime: 10 * 60_000 })
}

export function useVehicleAcademicMilestones() {
  return useQuery({ queryKey: ['vehicle-academic-milestones'], queryFn: fetchVehicleAcademicMilestones, staleTime: 10 * 60_000 })
}

export function useIntercampusMobility() {
  return useQuery({ queryKey: ['intercampus-mobility'], queryFn: fetchIntercampusMobility, staleTime: 10 * 60_000 })
}

export function useBehavioralClusters() {
  return useQuery({ queryKey: ['behavioral-clusters'], queryFn: fetchBehavioralClusters, staleTime: 30 * 60_000 })
}


