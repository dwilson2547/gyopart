import { useEffect, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { useApp } from '../context/AppContext'
import { api } from '../api'

export function ZipInput({ partId }: { partId: number }) {
  const { state, dispatch } = useApp()
  const [zip, setZip] = useState(state.zip)
  const [radius, setRadius] = useState(state.radiusMiles)
  const mounted = useRef(true)
  useEffect(() => () => { mounted.current = false }, [])

  async function handleSearch() {
    if (zip.length !== 5) return
    if (mounted.current) dispatch({ type: 'SET_SEARCHING', payload: true })
    if (mounted.current) dispatch({ type: 'SET_ZIP', payload: zip })
    if (mounted.current) dispatch({ type: 'SET_RADIUS', payload: radius })
    try {
      const data = await api.search(partId, zip, radius)
      if (mounted.current) dispatch({ type: 'SET_RESULTS', payload: data.results })
    } catch {
      if (mounted.current) dispatch({ type: 'SET_RESULTS', payload: [] })
    } finally {
      if (mounted.current) dispatch({ type: 'SET_SEARCHING', payload: false })
    }
  }

  return (
    <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-700 flex-shrink-0">
      <input
        className="bg-slate-800 border border-slate-700 text-white rounded px-3 py-2 text-sm w-28 placeholder-slate-500"
        placeholder="ZIP code"
        maxLength={5}
        value={zip}
        onChange={e => setZip(e.target.value.replace(/\D/g, ''))}
        onKeyDown={e => e.key === 'Enter' && handleSearch()}
      />
      <select
        className="bg-slate-800 border border-slate-700 text-white rounded px-2 py-2 text-sm"
        value={radius}
        onChange={e => setRadius(Number(e.target.value))}
      >
        {[25, 50, 100, 200].map(r => (
          <option key={r} value={r}>{r} mi</option>
        ))}
      </select>
      <button
        disabled={zip.length !== 5 || state.searching}
        onClick={handleSearch}
        className="flex items-center gap-1.5 bg-amber-500 text-black font-semibold px-4 py-2 rounded text-sm disabled:opacity-40 hover:bg-amber-400 transition-colors"
      >
        <Search size={14} />
        {state.searching ? 'Searching...' : 'Search'}
      </button>
      {state.activePart && (
        <span className="text-slate-400 text-xs ml-1 truncate max-w-36">
          {state.activePart.title ?? 'Part'}
        </span>
      )}
    </div>
  )
}
