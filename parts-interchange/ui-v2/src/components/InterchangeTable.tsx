import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { ChevronUp, ChevronDown } from 'lucide-react'
import { useCompatibleCars } from '../hooks/useCompatibleCars'
import { useApp } from '../context/AppContext'
import type { Part } from '../types'

function SortIcon({ col, sortCol, sortDir }: { col: string; sortCol: string; sortDir: 'asc' | 'desc' }) {
  if (sortCol !== col) return <ChevronDown size={12} className="text-slate-600" />
  return sortDir === 'asc' ? <ChevronUp size={12} className="text-amber-500" /> : <ChevronDown size={12} className="text-amber-500" />
}

interface Props { part: Part }

export function InterchangeTable({ part }: Props) {
  const { state } = useApp()
  const { cars, total, hasMore, loading, sortCol, sortDir, filterStr, setSort, setFilter, loadMore } = useCompatibleCars(part.id)

  function toggleSort(col: string) {
    if (sortCol === col) setSort(col, sortDir === 'asc' ? 'desc' : 'asc')
    else setSort(col, 'asc')
  }

  const columns: { key: string; label: string }[] = [
    { key: 'year', label: 'Year' },
    { key: 'make', label: 'Make' },
    { key: 'model', label: 'Model' },
    { key: 'trim', label: 'Trim' },
    { key: 'engine', label: 'Engine' },
  ]

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-3 px-6 py-3 border-b border-slate-800">
        <Input
          value={filterStr}
          onChange={e => setFilter(e.target.value)}
          placeholder="Filter vehicles…"
          className="bg-slate-800 border-slate-700 text-sm h-8 max-w-64"
        />
        <span className="text-xs text-zinc-400 shrink-0">{total} compatible vehicle{total !== 1 ? 's' : ''}</span>
      </div>

      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-950 border-b border-slate-800">
            <tr>
              {columns.map(col => (
                <th key={col.key} className="text-left px-4 py-2 text-zinc-400 font-medium cursor-pointer hover:text-white select-none" onClick={() => toggleSort(col.key)}>
                  <span className="flex items-center gap-1">{col.label}<SortIcon col={col.key} sortCol={sortCol} sortDir={sortDir} /></span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cars.map(car => {
              const isOwn = state.activeCar?.id === car.id
              return (
                <tr key={car.id} className={`border-b border-slate-800 hover:bg-slate-800 transition-colors ${isOwn ? 'bg-amber-500/10 border-l-2 border-l-amber-500' : 'bg-slate-900'}`}>
                  <td className="px-4 py-2 text-white">{car.year.name}</td>
                  <td className="px-4 py-2 text-white">{car.make.name}</td>
                  <td className="px-4 py-2 text-white">{car.model.name}</td>
                  <td className="px-4 py-2 text-zinc-400">{car.trim.name}</td>
                  <td className="px-4 py-2 text-zinc-400">{car.engine.name}</td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {loading && <p className="text-xs text-zinc-500 text-center py-4">Loading…</p>}

        {hasMore && !loading && (
          <div className="flex justify-center py-4">
            <Button variant="outline" size="sm" onClick={loadMore} className="border-slate-700 text-zinc-400">
              Load more
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
