import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { load, save } from '../lib/storage'
import type { GarageVehicle } from '../types'
import { GarageContext, type Garage, type GarageState } from './garageContext'

const KEY = 'gyopart-garage'
const DEFAULTS: GarageState = {
  vehicles: [], activeId: null, zip: '48314', radius: 50, homeYard: 'US Auto Supply — Sterling Heights',
}

/** The user's vehicles, active vehicle and home ZIP/radius — kept in localStorage (single-user app). */
export function GarageProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GarageState>(() => ({ ...DEFAULTS, ...load<Partial<GarageState>>(KEY, {}) }))
  useEffect(() => save(KEY, state), [state])

  const add = useCallback((v: GarageVehicle) => setState(s => ({
    ...s,
    // the same car added again replaces the old entry (e.g. now with a VIN)
    vehicles: [v, ...s.vehicles.filter(x => x.car_id !== v.car_id)],
    activeId: v.car_id,
  })), [])
  const remove = useCallback((carId: number) => setState(s => {
    const vehicles = s.vehicles.filter(x => x.car_id !== carId)
    return { ...s, vehicles, activeId: s.activeId === carId ? (vehicles[0]?.car_id ?? null) : s.activeId }
  }), [])
  const setActive = useCallback((carId: number) => setState(s => ({ ...s, activeId: carId })), [])
  const setHome = useCallback((zip: string, radius: number) => setState(s => ({ ...s, zip, radius })), [])
  const setHomeYard = useCallback((homeYard: string) => setState(s => ({ ...s, homeYard })), [])

  const value = useMemo<Garage>(() => ({
    ...state,
    active: state.vehicles.find(v => v.car_id === state.activeId) ?? null,
    add, remove, setActive, setHome, setHomeYard,
  }), [state, add, remove, setActive, setHome, setHomeYard])
  return <GarageContext.Provider value={value}>{children}</GarageContext.Provider>
}
