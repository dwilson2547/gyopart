import { createContext, useContext } from 'react'
import type { GarageVehicle } from '../types'

export interface GarageState {
  vehicles: GarageVehicle[]
  activeId: number | null // car_id of the active vehicle
  zip: string
  radius: number
}

export interface Garage extends GarageState {
  active: GarageVehicle | null
  add: (v: GarageVehicle) => void
  remove: (carId: number) => void
  setActive: (carId: number) => void
  setHome: (zip: string, radius: number) => void
}

export const GarageContext = createContext<Garage | null>(null)

export function useGarage(): Garage {
  const g = useContext(GarageContext)
  if (!g) throw new Error('useGarage outside GarageProvider')
  return g
}

export function vehicleTitle(v: { year: string; make: string; model: string }) {
  return `${v.year} ${v.make} ${v.model}`
}

export function vehicleSubtitle(v: { trim: string | null; engine: string | null }) {
  return [v.trim, v.engine].filter(Boolean).join(' · ')
}
