import { useApp } from './context/AppContext'
import { TopBar } from './components/TopBar'
import { VehiclePicker } from './components/VehiclePicker'
import { PartsList } from './components/PartsList'
import { JunkyardResults } from './components/JunkyardResults'
import { DiagramBrowser } from './components/DiagramBrowser'
import { DiagramView } from './components/DiagramView'
import type { Part } from './types'

const TAB_CLS = 'flex-1 py-2 text-xs font-medium transition-colors'
const TAB_ACTIVE = 'text-amber-400 border-b-2 border-amber-400'
const TAB_INACTIVE = 'text-slate-400 hover:text-slate-200'

export default function App() {
  const { state, dispatch } = useApp()
  const leftTab = state.leftTab
  const activeDiagramId = state.activeDiagramId

  function handleDiagramPartSelect(part: Part) {
    dispatch({ type: 'SET_PART', payload: part })
    dispatch({ type: 'SET_LEFT_TAB', payload: 'parts' })
  }

  function handleVehicleClear() {
    dispatch({ type: 'CLEAR_VEHICLE' })
  }

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
                  onClick={handleVehicleClear}
                  className="text-xs text-amber-500 hover:underline ml-2 flex-shrink-0"
                >
                  Change
                </button>
              </div>

              {/* Tab bar */}
              <div className="flex border-b border-slate-700 flex-shrink-0">
                <button
                  onClick={() => dispatch({ type: 'SET_LEFT_TAB', payload: 'parts' })}
                  className={`${TAB_CLS} ${leftTab === 'parts' ? TAB_ACTIVE : TAB_INACTIVE}`}
                >
                  Parts
                </button>
                <button
                  onClick={() => dispatch({ type: 'SET_LEFT_TAB', payload: 'diagrams' })}
                  className={`${TAB_CLS} ${leftTab === 'diagrams' ? TAB_ACTIVE : TAB_INACTIVE}`}
                >
                  Diagrams
                </button>
              </div>

              {leftTab === 'parts' ? (
                <PartsList carId={state.selectedVehicle.car.id} />
              ) : (
                <DiagramBrowser
                  carId={state.selectedVehicle.car.id}
                  activeDiagramId={activeDiagramId}
                  onDiagramSelect={(id) => dispatch({ type: 'SET_ACTIVE_DIAGRAM', payload: id })}
                />
              )}
            </>
          )}
        </aside>

        {/* Right panel */}
        <main className="flex-1 overflow-hidden bg-slate-950 flex flex-col">
          {leftTab === 'diagrams' && activeDiagramId ? (
            <DiagramView diagramId={activeDiagramId} onPartSelect={handleDiagramPartSelect} />
          ) : (
            <JunkyardResults />
          )}
        </main>
      </div>
    </div>
  )
}
