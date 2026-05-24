import { useApp } from '../context/AppContext'
import { VehiclePicker } from './VehiclePicker'
import { Garage } from './Garage'
import { PartsList } from './PartsList'

interface Props {
  constrainGarage?: boolean
}

export function LeftRailContent({ constrainGarage = false }: Props) {
  const { state } = useApp()
  return (
    <>
      <div className="shrink-0 border-b border-slate-800">
        <p className="px-4 pt-3 pb-1 text-xs font-semibold text-zinc-500 uppercase tracking-wider">Vehicle</p>
        <VehiclePicker />
      </div>
      <div className={`shrink-0 border-b border-slate-800 ${constrainGarage ? 'max-h-48 overflow-y-auto' : ''}`}>
        <p className="px-4 pt-3 pb-1 text-xs font-semibold text-zinc-500 uppercase tracking-wider">Garage</p>
        <Garage />
      </div>
      {state.activeCar && (
        <div className="flex-1 overflow-hidden flex flex-col">
          <p className="px-4 pt-3 pb-1 text-xs font-semibold text-zinc-500 uppercase tracking-wider shrink-0">Parts</p>
          <div className="flex-1 overflow-hidden">
            <PartsList />
          </div>
        </div>
      )}
    </>
  )
}
