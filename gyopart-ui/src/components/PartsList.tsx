import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context/AppContext'
import type { Part } from '../types'

export function PartsList({ carId }: { carId: number }) {
  const { state, dispatch } = useApp()
  const [parts, setParts] = useState<Part[]>([])
  const [total, setTotal] = useState(0)
  const [filter, setFilter] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)

  function handleFilterChange(value: string) {
    setFilter(value)
    setPage(1)
  }

  useEffect(() => {
    let cancelled = false
    const timer = setTimeout(() => {
      setLoading(true)
      api.parts(carId, filter || undefined, page)
        .then(r => { if (!cancelled) { setParts(r.items); setTotal(r.total) } })
        .catch(() => { if (!cancelled) { setParts([]); setTotal(0) } })
        .finally(() => { if (!cancelled) setLoading(false) })
    }, 300)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [carId, filter, page])

  const perPage = 25
  const totalPages = Math.ceil(total / perPage)
  const from = total === 0 ? 0 : (page - 1) * perPage + 1
  const to = Math.min(page * perPage, total)

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="px-4 pt-3 pb-2">
        <input
          aria-label="Filter parts"
          className="w-full bg-slate-800 border border-slate-700 text-white rounded px-2 py-2 text-sm placeholder-slate-500"
          placeholder="Filter parts..."
          value={filter}
          onChange={e => handleFilterChange(e.target.value)}
        />
        {total > 0 && (
          <p className="text-xs text-slate-500 mt-1" data-testid="parts-count">
            Showing {from}–{to} of {total.toLocaleString()} parts
          </p>
        )}
      </div>
      {loading && <p className="px-4 text-slate-400 text-sm">Loading...</p>}
      <div id="parts-list" className="flex-1 overflow-y-auto px-2">
        {parts.map(p => {
          const isActive = state.activePart?.id === p.id
          return (
            <button
              key={p.id}
              data-testid="part-row"
              onClick={() => isActive ? dispatch({ type: 'CLEAR_PART' }) : dispatch({ type: 'SET_PART', payload: p })}
              className={`w-full text-left px-3 py-2 rounded mb-0.5 text-sm transition-colors ${
                isActive
                  ? 'bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/40'
                  : 'hover:bg-slate-700 text-slate-200'
              }`}
            >
              <span className="block font-medium">{p.title ?? 'Unnamed Part'}</span>
              {p.part_number && <span className="text-slate-500 text-xs">#{p.part_number}</span>}
              {p.other_names && (
                <span className="block text-slate-500 text-xs truncate">{p.other_names}</span>
              )}
            </button>
          )
        })}
        {!loading && parts.length === 0 && (
          <p className="px-3 py-2 text-slate-500 text-sm">No parts found.</p>
        )}
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-2 border-t border-slate-700 flex-shrink-0" data-testid="pagination">
          <button
            data-testid="prev-page"
            disabled={page === 1}
            onClick={() => setPage(p => p - 1)}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronLeft size={14} /> Prev
          </button>
          <span className="text-xs text-slate-500" data-testid="page-indicator">Page {page} of {totalPages}</span>
          <button
            data-testid="next-page"
            disabled={page === totalPages}
            onClick={() => setPage(p => p + 1)}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Next <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  )
}
