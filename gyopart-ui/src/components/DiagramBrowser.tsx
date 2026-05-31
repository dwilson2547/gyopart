import { useEffect, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { api } from '../api'
import type { Category, Diagram } from '../types'

interface Props {
  carId: number
  activeDiagramId: number | null
  onDiagramSelect: (id: number) => void
}

export function DiagramBrowser({ carId, activeDiagramId, onDiagramSelect }: Props) {
  const [categories, setCategories] = useState<Category[]>([])
  const [selectedCat, setSelectedCat] = useState<Category | null>(null)
  const [diagrams, setDiagrams] = useState<Diagram[]>([])
  const [loadingCats, setLoadingCats] = useState(false)
  const [loadingDiags, setLoadingDiags] = useState(false)

  useEffect(() => {
    setLoadingCats(true)
    api.categories(carId)
      .then(setCategories)
      .catch(() => setCategories([]))
      .finally(() => setLoadingCats(false))
  }, [carId])

  useEffect(() => {
    if (!selectedCat) return
    setLoadingDiags(true)
    setDiagrams([])
    api.diagrams(selectedCat.id, carId)
      .then(setDiagrams)
      .catch(() => setDiagrams([]))
      .finally(() => setLoadingDiags(false))
  }, [selectedCat, carId])

  function formatCatName(name: string) {
    return name.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {loadingCats && <p className="px-4 py-3 text-slate-400 text-sm">Loading categories…</p>}

      {/* Category list */}
      <div className="flex-shrink-0 overflow-y-auto border-b border-slate-700 max-h-52">
        {categories.map(cat => (
          <button
            key={cat.id}
            onClick={() => { setSelectedCat(cat); setDiagrams([]) }}
            className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between transition-colors ${
              selectedCat?.id === cat.id
                ? 'bg-amber-500/20 text-amber-300'
                : 'hover:bg-slate-700 text-slate-300'
            }`}
          >
            <span>{formatCatName(cat.name)}</span>
            <ChevronRight size={14} className="flex-shrink-0 opacity-50" />
          </button>
        ))}
      </div>

      {/* Diagram list */}
      {selectedCat && (
        <div className="flex-1 overflow-y-auto px-2 pt-2">
          <p className="px-1 text-xs text-slate-500 mb-1 font-medium uppercase tracking-wide">
            {formatCatName(selectedCat.name)}
          </p>
          {loadingDiags && <p className="px-1 py-2 text-slate-400 text-sm">Loading…</p>}
          {!loadingDiags && diagrams.length === 0 && (
            <p className="px-1 py-2 text-slate-500 text-sm">No diagrams found.</p>
          )}
          {diagrams.map((d, i) => (
            <button
              key={d.id}
              data-testid="diagram-entry"
              onClick={() => onDiagramSelect(d.id)}
              className={`w-full text-left px-3 py-2 rounded mb-0.5 text-sm transition-colors ${
                activeDiagramId === d.id
                  ? 'bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/40'
                  : 'hover:bg-slate-700 text-slate-300'
              }`}
            >
              Diagram {i + 1}
            </button>
          ))}
        </div>
      )}

      {!selectedCat && !loadingCats && (
        <p className="px-4 py-3 text-slate-500 text-sm">Select a category to browse diagrams</p>
      )}
    </div>
  )
}
