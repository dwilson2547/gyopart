import { useApp } from '../context/AppContext'

export function ActiveVehicleBadge() {
  const { state } = useApp()
  if (!state.activeCar) {
    return <span className="text-xs text-slate-600">No vehicle selected</span>
  }
  const { year, make, model, trim, engine } = state.activeCar
  return <span className="text-xs text-zinc-400">{year} {make} {model} · {trim} · {engine}</span>
}
