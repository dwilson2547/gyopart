import { Trash2 } from 'lucide-react'
import type { GarageItem } from '../types'

interface Props {
  item: GarageItem
  isActive: boolean
  onSelect: () => void
  onRemove: () => void
}

export function GarageCard({ item, isActive, onSelect, onRemove }: Props) {
  return (
    <div className={`flex items-center justify-between px-3 py-2 rounded bg-slate-800 border ${isActive ? 'border-l-4 border-l-amber-500 border-slate-700' : 'border-slate-700'}`}>
      <div className="flex flex-col min-w-0">
        <span className="text-sm text-white truncate">{item.year} {item.make} {item.model}</span>
        <span className="text-xs text-zinc-400 truncate">{item.trim} · {item.engine}</span>
      </div>
      <div className="flex items-center gap-2 ml-2 shrink-0">
        <button onClick={onSelect} className="text-xs text-amber-500 hover:underline">Select</button>
        <button onClick={onRemove} className="text-zinc-500 hover:text-red-400"><Trash2 size={14} /></button>
      </div>
    </div>
  )
}
