import { createContext, useContext } from 'react'

export const VehiclePickerContext = createContext<{ open: () => void } | null>(null)

/** Opens the vehicle picker modal (rendered once, by VehiclePickerProvider in the Shell). */
export function useVehiclePicker() {
  const c = useContext(VehiclePickerContext)
  if (!c) throw new Error('useVehiclePicker outside VehiclePickerProvider')
  return c
}
