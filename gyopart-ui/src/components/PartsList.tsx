import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../context/AppContext'
import type { Part } from '../types'

export function PartsList({ carId }: { carId: number }) {
  const { state, dispatch } = useApp()
  const [parts, setParts] = useState<Part[]>([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.parts(carId, filter || undefined)
      .then(r => { if (!cancelled) setParts(r.items) })
      .catch(() => { if (!cancelled) setParts([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [carId, filter])

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="px-4 pt-3 pb-2">
        <input
          className="w-full bg-slate-800 border border-slate-700 text-white rounded px-2 py-2 text-sm placeholder-slate-500"
          placeholder="Filter parts..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
      </div>
      {loading && <p className="px-4 text-slate-400 text-sm">Loading...</p>}
      <div className="flex-1 overflow-y-auto px-2">
        {parts.map(p => (
          <button
            key={p.id}
            onClick={() => dispatch({ type: 'SET_PART', payload: p })}
            className={`w-full text-left px-3 py-2 rounded mb-0.5 text-sm transition-colors ${
              state.activePart?.id === p.id
                ? 'bg-amber-500/20 text-amber-300'
                : 'hover:bg-slate-700 text-slate-200'
            }`}
          >
            <span className="block font-medium">{p.title ?? 'Unnamed Part'}</span>
            {p.part_number && <span className="text-slate-500 text-xs">#{p.part_number}</span>}
          </button>
        ))}
        {!loading && parts.length === 0 && (
          <p className="px-3 py-2 text-slate-500 text-sm">No parts found.</p>
        )}
      </div>
    </div>
  )
}
