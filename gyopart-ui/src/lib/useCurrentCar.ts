import { matchPath, useLocation } from 'react-router'
import { useGarage } from '../state/garageContext'
import type { CarDetail } from '../types'
import { useCarParam } from './useCarParam'

/** The car being browsed: /car/:id, or ?car= on a part page; anywhere else the garage's active car. */
export function useCurrentCar(): CarDetail | null {
  const { pathname, search } = useLocation()
  const { active } = useGarage()
  const raw = matchPath('/car/:carId', pathname)?.params.carId
    ?? (pathname.startsWith('/part/') ? new URLSearchParams(search).get('car') : null)
  const id = raw && /^\d+$/.test(raw) ? Number(raw) : null
  const car = useCarParam(id)
  return id === null ? active : car
}
