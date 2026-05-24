import { useApp } from './context/AppContext'
import { TopBar } from './components/TopBar'
import { VehiclePicker } from './components/VehiclePicker'
import { PartsList } from './components/PartsList'
import { JunkyardResults } from './components/JunkyardResults'

export default function App() {
  const { state, dispatch } = useApp()

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-white">
      <TopBar />
      <div className="flex flex-1 overflow-hidden pt-14">
        {/* Left rail */}
        <aside className="w-72 flex-shrink-0 bg-slate-900 flex flex-col border-r border-slate-700 overflow-hidden">
          {!state.selectedVehicle ? (
            <VehiclePicker />
          ) : (
            <>
              <div className="flex items-start justify-between px-4 py-3 border-b border-slate-700 flex-shrink-0">
                <div>
                  <p className="text-sm font-semibold text-white">
                    {state.selectedVehicle.yearName} {state.selectedVehicle.makeName}{' '}
                    {state.selectedVehicle.modelName}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {state.selectedVehicle.trimName} · {state.selectedVehicle.engineName}
                  </p>
                </div>
                <button
                  onClick={() => dispatch({ type: 'CLEAR_VEHICLE' })}
                  className="text-xs text-amber-500 hover:underline ml-2 flex-shrink-0"
                >
                  Change
                </button>
              </div>
              <PartsList carId={state.selectedVehicle.car.id} />
            </>
          )}
        </aside>

        {/* Right panel */}
        <main className="flex-1 overflow-hidden bg-slate-950 flex flex-col">
          <JunkyardResults />
        </main>
      </div>
    </div>
  )
}
