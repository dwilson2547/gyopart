import { useEffect, useMemo, useState } from 'react'
import { ChevronRight, Search, X } from 'lucide-react'
import { api } from '../api'
import { useAsync } from '../lib/useAsync'
import type { PartHit, TreeCategory } from '../types'
import { ErrorLine, Loading } from './States'

interface Props {
  carId: number
  tree: TreeCategory[]
  subId: number | null
  partId: number | null
  query: string
  onQuery: (q: string) => void
  onSub: (subId: number) => void
  onHit: (hit: PartHit) => void
}

/** Category → subcategory tree, always visible. Typing in the filter nests matching parts under their
 *  category/subcategory instead of listing them flat. */
export function CatalogueTree({ carId, tree, subId, partId, query, onQuery, onSub, onHit }: Props) {
  const [text, setText] = useState(query)
  const [open, setOpen] = useState<Set<number>>(() => {
    const cat = tree.find(c => c.subcategories.some(s => s.id === subId))
    return new Set(cat ? [cat.id] : [])
  })

  // Debounce typing into the URL (?q=), which drives the search.
  useEffect(() => {
    const t = setTimeout(() => { if (text.trim() !== query) onQuery(text.trim()) }, 250)
    return () => clearTimeout(t)
  }, [text, query, onQuery])

  const searching = query.length >= 2
  const search = useAsync(() => api.searchCarParts(carId, query), [carId, query], searching)

  const toggle = (id: number) => setOpen(s => {
    const n = new Set(s)
    if (n.has(id)) n.delete(id)
    else n.add(id)
    return n
  })

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line p-3">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted" />
          <input
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Escape') setText('') }}
            placeholder="Filter parts — name or number"
            aria-label="Filter parts"
            className="w-full rounded-lg border border-line bg-bg py-1.5 pr-8 pl-8 text-sm outline-none placeholder:text-muted focus:border-accent"
          />
          {text && (
            <button onClick={() => setText('')} aria-label="Clear filter"
              className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-0.5 text-muted hover:bg-hover">
              <X className="size-4" />
            </button>
          )}
        </div>
        {text.trim().length === 1 && <p className="mt-1 text-xs text-muted">Type at least 2 characters.</p>}
      </div>

      <nav aria-label="Categories" className="min-h-0 flex-1 overflow-auto px-2 py-2">
        {searching ? (
          search.loading ? <Loading label="Searching…" />
            : search.error ? <ErrorLine message={search.error} onRetry={search.retry} />
              : search.data && <FilteredTree tree={tree} hits={search.data.hits} truncated={search.data.truncated}
                query={query} partId={partId} onHit={onHit} />
        ) : (
          tree.map(cat => {
            const isOpen = open.has(cat.id)
            const hasActive = cat.subcategories.some(s => s.id === subId)
            return (
              <div key={cat.id}>
                <button
                  onClick={() => toggle(cat.id)}
                  aria-expanded={isOpen}
                  className={`flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-hover ${
                    hasActive && !isOpen ? 'text-accent' : ''
                  }`}
                >
                  <ChevronRight className={`size-4 shrink-0 text-muted transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                  <span className="flex-1 font-medium">{cat.label}</span>
                  <span className="text-xs text-muted">{cat.subcategories.length}</span>
                </button>
                {isOpen && (
                  <ul className="mb-1 ml-4 border-l border-line pl-2">
                    {cat.subcategories.map(s => (
                      <li key={s.id}>
                        <button
                          onClick={() => onSub(s.id)}
                          aria-current={s.id === subId ? 'page' : undefined}
                          className={`w-full rounded-lg px-2 py-1 text-left text-sm ${
                            s.id === subId ? 'bg-accent-soft text-accent' : 'hover:bg-hover'
                          }`}
                        >
                          {s.label}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )
          })
        )}
      </nav>
    </div>
  )
}

function FilteredTree({ tree, hits, truncated, query, partId, onHit }: {
  tree: TreeCategory[]; hits: PartHit[]; truncated: boolean; query: string; partId: number | null
  onHit: (h: PartHit) => void
}) {
  // category → subcategory (null = part fits the car but is on none of its diagrams) → hits
  const grouped = useMemo(() => {
    const byCat = new Map<number | null, Map<number | null, PartHit[]>>()
    for (const h of hits) {
      const subs = byCat.get(h.category_id) ?? new Map()
      byCat.set(h.category_id, subs)
      subs.set(h.sub_category_id, [...(subs.get(h.sub_category_id) ?? []), h])
    }
    const catLabel = (id: number | null) => tree.find(c => c.id === id)?.label ?? 'Other'
    const subLabel = (id: number | null) =>
      tree.flatMap(c => c.subcategories).find(s => s.id === id)?.label ?? 'Not on a diagram'
    return [...byCat.entries()]
      .map(([cid, subs]) => ({
        id: cid, label: catLabel(cid),
        subs: [...subs.entries()].map(([sid, hs]) => ({ id: sid, label: subLabel(sid), hits: hs }))
          .sort((a, b) => (a.id === null ? 1 : b.id === null ? -1 : a.label.localeCompare(b.label))),
      }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }, [hits, tree])

  if (!hits.length) {
    return <p className="px-2 py-6 text-center text-sm text-muted">No parts on this vehicle match “{query}”.</p>
  }
  return (
    <div>
      <p className="section-label px-2 pb-1">
        {hits.length}{truncated ? '+' : ''} {hits.length === 1 ? 'match' : 'matches'}
        {truncated && ' — refine to see all'}
      </p>
      {grouped.map(cat => (
        <div key={cat.id ?? 'none'} className="mb-1">
          <div className="flex items-center gap-1.5 px-2 py-1.5 text-sm font-medium">
            <ChevronRight className="size-4 rotate-90 text-muted" />
            <span className="flex-1">{cat.label}</span>
          </div>
          <div className="ml-4 border-l border-line pl-2">
            {cat.subs.map(sub => (
              <div key={sub.id ?? 'none'} className="mb-1">
                <div className="px-2 py-0.5 text-sm text-muted">{sub.label}</div>
                <ul className="ml-2">
                  {sub.hits.map(h => (
                    <li key={`${h.part_id}-${h.diagram_id}`}>
                      <button
                        onClick={() => onHit(h)}
                        className={`flex w-full items-baseline gap-2 rounded-lg px-2 py-1 text-left text-sm ${
                          h.part_id === partId ? 'bg-accent-soft text-accent' : 'hover:bg-hover'
                        }`}
                      >
                        {h.part_index && (
                          <span className="inline-flex size-5 shrink-0 items-center justify-center rounded-full border border-line text-[0.65rem] text-muted">
                            {h.part_index}
                          </span>
                        )}
                        <span className="min-w-0 flex-1">
                          <span className="block truncate">{h.title ?? 'Untitled part'}</span>
                          <span className="block truncate font-mono text-xs text-muted">
                            {h.part_number}{h.matched === 'other' && <span className="font-sans"> · also called “{query}”</span>}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
