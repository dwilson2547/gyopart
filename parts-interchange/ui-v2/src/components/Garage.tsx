import { useApp } from '../context/AppContext'
import { GarageCard } from './GarageCard'

export function Garage() {
  const { state, dispatch } = useApp()

  if (state.garage.length === 0) {
    return <p className="px-4 py-3 text-xs text-zinc-400 text-center">No saved vehicles. Add one above.</p>
  }

  return (
    <div className="flex flex-col gap-2 px-4 py-3">
      {state.garage.map(item => (
        <GarageCard
          key={item.id}
          item={item}
          isActive={state.activeCar?.id === item.id}
          onSelect={() => dispatch({ type: 'SET_ACTIVE_CAR', payload: item })}
          onRemove={() => dispatch({ type: 'REMOVE_FROM_GARAGE', payload: item.id })}
        />
      ))}
    </div>
  )
}
