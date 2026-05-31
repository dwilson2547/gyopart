import { useApp } from '../context/AppContext'
import { ZipInput } from './ZipInput'
import { YardCard } from './YardCard'

export function JunkyardResults() {
  const { state } = useApp()

  if (!state.activePart) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-slate-500 text-sm">Select a part to search nearby junkyards</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <ZipInput partId={state.activePart.id} />
      <div className="flex-1 overflow-y-auto p-4">
        {state.searching && (
          <p className="text-slate-400 text-sm">Searching...</p>
        )}
        {!state.searching && state.zip && state.results.length === 0 && (
          <p className="text-slate-500 text-sm">
            No yards found within {state.radiusMiles} miles of {state.zip}.
          </p>
        )}
        {state.results.map(yard => (
          <YardCard key={yard.location_id} yard={yard} />
        ))}
      </div>
    </div>
  )
}
