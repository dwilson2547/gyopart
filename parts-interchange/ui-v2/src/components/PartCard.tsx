import type { Part } from '../types'

interface Props {
  part: Part
  isActive: boolean
  onClick: () => void
}

export function PartCard({ part, isActive, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 rounded border flex flex-col gap-0.5 hover:bg-slate-800 transition-colors ${
        isActive ? 'border-l-4 border-l-amber-500 border-slate-700 bg-slate-800' : 'border-slate-700 bg-slate-900'
      }`}
    >
      <span className="text-xs font-mono text-amber-500">{part.part_number}</span>
      <span className="text-sm text-white leading-tight">{part.title}</span>
    </button>
  )
}
