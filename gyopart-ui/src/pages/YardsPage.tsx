import { useState } from 'react'
import { Link } from 'react-router'
import { ChevronRight, Search, Star, Warehouse, X } from 'lucide-react'
import { api } from '../api'
import { Empty, ErrorLine, Loading } from '../components/States'
import { relativeDay } from '../lib/format'
import { useAsync } from '../lib/useAsync'
import { useGarage } from '../state/garageContext'
import type { YardSummary } from '../types'

/** Workflow 7, part 1: every yard — home yard first, then nearest — each linking to its inventory. */
export function YardsPage() {
  const { zip, homeYard } = useGarage()
  const yards = useAsync(() => api.yards(zip), [zip])
  const [filter, setFilter] = useState('')
  const [showEmpty, setShowEmpty] = useState(false)

  if (yards.loading) return <Loading label="Loading yards…" />
  if (yards.error) return <ErrorLine message={`Yard inventory is unavailable right now (${yards.error}).`} onRetry={yards.retry} />

  const q = filter.trim().toLowerCase()
  const all = (yards.data ?? [])
    .filter(y => !q || [y.name, y.city, y.state, y.chain].some(s => s?.toLowerCase().includes(q)))
    .sort((a, b) => Number(b.name === homeYard) - Number(a.name === homeYard))
  const stocked = all.filter(y => y.vehicle_count > 0)
  const empty = all.filter(y => y.vehicle_count === 0)

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 px-4 py-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold"><Warehouse className="size-5 text-muted" /> Yards</h1>
          <p className="text-sm text-muted">{stocked.length} yards with inventory · distances from {zip}</p>
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted" />
          <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter by name or city" aria-label="Filter yards"
            className="w-full rounded-lg border border-line bg-surface py-1.5 pr-8 pl-8 text-sm outline-none placeholder:text-muted focus:border-accent" />
          {filter && (
            <button onClick={() => setFilter('')} aria-label="Clear filter"
              className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-0.5 text-muted hover:bg-hover"><X className="size-4" /></button>
          )}
        </div>
      </div>

      {all.length === 0 ? (
        <Empty icon={Warehouse} title={q ? `No yards match “${filter.trim()}”.` : 'No yards yet.'}
          hint={q ? undefined : 'Yards appear once their scraper has run.'} />
      ) : (
        <>
          <ul className="flex flex-col gap-2" aria-label="Yards with inventory">
            {stocked.map(y => <YardRow key={y.location_id} y={y} isHome={y.name === homeYard} />)}
          </ul>
          {empty.length > 0 && (
            <div>
              <button onClick={() => setShowEmpty(s => !s)} className="text-sm text-muted hover:text-text">
                {showEmpty ? 'Hide' : 'Show'} {empty.length} yard{empty.length === 1 ? '' : 's'} with no vehicles on record
              </button>
              {showEmpty && (
                <ul className="mt-2 flex flex-col gap-2 opacity-70">
                  {empty.map(y => <YardRow key={y.location_id} y={y} isHome={y.name === homeYard} />)}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function YardRow({ y, isHome }: { y: YardSummary; isHome: boolean }) {
  return (
    <li>
      <Link to={`/yards/${y.location_id}`}
        className={`flex items-center gap-3 rounded-xl border bg-surface px-4 py-3 hover:border-accent ${isHome ? 'border-accent' : 'border-line'}`}>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 font-medium">
            {y.name}
            {isHome && <span className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs whitespace-nowrap text-white"><Star className="size-3 fill-current" /> Home yard</span>}
          </p>
          <p className="truncate text-sm text-muted">
            {[y.city, y.state].filter(Boolean).join(', ') || 'Location unknown'}
            {y.distance_miles != null && <> · {y.distance_miles < 1 ? 'under 1' : Math.round(y.distance_miles)} mi</>}
            {y.last_seen_at && <> · checked {relativeDay(y.last_seen_at)}</>}
          </p>
        </div>
        <div className="text-right text-sm">
          <p className="font-medium">{y.vehicle_count.toLocaleString()} vehicles</p>
          {y.new_this_week > 0 && <p className="text-xs text-ok">+{y.new_this_week} this week</p>}
        </div>
        <ChevronRight className="size-4 shrink-0 text-muted" />
      </Link>
    </li>
  )
}
