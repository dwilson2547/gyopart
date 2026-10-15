import { useLocation, useNavigate } from 'react-router'
import { useGarage } from '../state/garageContext'
import type { GarageVehicle } from '../types'

/** Switch to a car: optionally save it to the garage, then show it — a part page keeps the part and
 *  re-checks fit for the new car (?car=), anywhere else opens the car's catalogue. */
export function useChooseCar() {
  const { vehicles, add, setActive } = useGarage()
  const navigate = useNavigate()
  const { pathname, search } = useLocation()
  return (v: GarageVehicle, save: boolean) => {
    if (save) add(v)
    else if (vehicles.some(x => x.car_id === v.car_id)) setActive(v.car_id)
    if (pathname.startsWith('/part/')) {
      const p = new URLSearchParams(search)
      p.set('car', String(v.car_id))
      p.delete('diagram') // a diagram of the previous car
      navigate(`${pathname}?${p}`)
    } else {
      navigate(`/car/${v.car_id}`)
    }
  }
}
