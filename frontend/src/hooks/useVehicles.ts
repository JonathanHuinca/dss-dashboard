import { useQuery, keepPreviousData } from '@tanstack/react-query'
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
import { opcionesConsultaAnalitica } from './opcionesConsulta'

const LIVE_INTERVAL = 60_000

export function useVehicleKpis(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string, sector?: string) {
  return useQuery({
    queryKey: ['vehicle-kpis', fechaInicio, fechaFin, filters, sector],
    queryFn: ({ signal }) => fetchVehicleKpis(fechaInicio, fechaFin, filters, sector, signal),
    ...opcionesConsultaAnalitica(),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  })
}


export function useParkingOccupancy(sector?: string) {
  return useQuery({
    queryKey: ['parking-occupancy', sector],
    queryFn: ({ signal }) => fetchParkingOccupancy(sector, signal),
    refetchInterval: LIVE_INTERVAL,
    refetchIntervalInBackground: false,
    staleTime: LIVE_INTERVAL - 5000,
    placeholderData: keepPreviousData,
  })
}

export function useVehicleHourlyFlow(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string, sector?: string) {
  return useQuery({
    queryKey: ['vehicle-hourly-flow', fechaInicio, fechaFin, filters, sector],
    queryFn: ({ signal }) => fetchVehicleHourlyFlow(fechaInicio, fechaFin, filters, sector, signal),
    ...opcionesConsultaAnalitica(),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  })
}

export function useFleetComposition(fechaInicio?: string, fechaFin?: string, sector?: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['fleet-composition', fechaInicio, fechaFin, sector],
    queryFn: ({ signal }) => fetchFleetComposition(fechaInicio, fechaFin, sector, signal),
    ...opcionesConsultaAnalitica(30 * 60_000),
    ...opts,
  })
}

export function useForecastParking(opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['forecast-parking'],
    queryFn: ({ signal }) => fetchForecastParking(signal),
    ...opcionesConsultaAnalitica(60 * 60_000),
    ...opts,
  })
}

export function useCameraStats(fechaInicio?: string, fechaFin?: string, filters?: DataFilters | string, sector?: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['camera-stats', fechaInicio, fechaFin, filters, sector],
    queryFn: ({ signal }) => fetchCameraStats(fechaInicio, fechaFin, filters, sector, signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useVehicleDailyEvolution(fechaInicio?: string, fechaFin?: string, sector?: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['vehicle-daily-evolution', fechaInicio, fechaFin, sector],
    queryFn: ({ signal }) => fetchVehicleDailyEvolution(fechaInicio, fechaFin, sector, signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useVehicleAcademicMilestones(opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['vehicle-academic-milestones'],
    queryFn: ({ signal }) => fetchVehicleAcademicMilestones(signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useIntercampusMobility(opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['intercampus-mobility'],
    queryFn: ({ signal }) => fetchIntercampusMobility(signal),
    ...opcionesConsultaAnalitica(),
    ...opts,
  })
}

export function useBehavioralClusters(opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['behavioral-clusters'],
    queryFn: ({ signal }) => fetchBehavioralClusters(signal),
    ...opcionesConsultaAnalitica(30 * 60_000),
    ...opts,
  })
}
