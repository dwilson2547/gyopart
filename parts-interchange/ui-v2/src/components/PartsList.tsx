import { useEffect, useRef } from 'react'
import { Input } from '@/components/ui/input'
import { useParts } from '../hooks/useParts'
import { useApp } from '../context/AppContext'
import { PartCard } from './PartCard'

export function PartsList() {
  const { state, dispatch } = useApp()
  const carId = state.activeCar?.id ?? null
  const { parts, hasMore, loading, filter, setFilter, loadMore } = useParts(carId)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!bottomRef.current) return
    const observer = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasMore && !loading) loadMore()
    }, { threshold: 0.1 })
    observer.observe(bottomRef.current)
    return () => observer.disconnect()
  }, [hasMore, loading, loadMore])

  if (!carId) return null

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 border-b border-slate-800">
        <Input
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="Search parts…"
          className="bg-slate-800 border-slate-700 text-sm h-8"
        />
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="flex flex-col gap-1.5 p-4">
          {parts.length === 0 && !loading && (
            <p className="text-xs text-zinc-400 text-center py-6">No parts found for this vehicle.</p>
          )}
          {parts.map(part => (
            <PartCard
              key={part.id}
              part={part}
              isActive={state.activePart?.id === part.id}
              onClick={() => dispatch({ type: 'SET_ACTIVE_PART', payload: part })}
            />
          ))}
          {loading && <p className="text-xs text-zinc-500 text-center py-2">Loading…</p>}
          <div ref={bottomRef} className="h-1" />
        </div>
      </div>
    </div>
  )
}
