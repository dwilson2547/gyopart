import { api } from '../api'
import { useGarage } from '../state/garageContext'
import type { CarDetail } from '../types'
import { useAsync } from './useAsync'

/** The car a page was opened for (?car=): from the garage when it's there, else fetched. */
export function useCarParam(carId: number | null): CarDetail | null {
  const { vehicles } = useGarage()
  const inGarage = vehicles.find(v => v.car_id === carId) ?? null
  const fetched = useAsync(() => api.car(carId!), [carId], carId !== null && !inGarage)
  return inGarage ?? fetched.data
}
