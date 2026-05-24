import { ArrowLeft } from 'lucide-react'
import { useApp } from '../context/AppContext'
import { PartDetailHeader } from './PartDetailHeader'
import { InterchangeTable } from './InterchangeTable'

export function RightPanel() {
  const { state } = useApp()

  if (!state.activePart) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-8">
        <ArrowLeft size={32} className="text-slate-700 mb-4" />
        <p className="text-zinc-500 text-sm">Select a part from the list to see which other vehicles it fits.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PartDetailHeader part={state.activePart} />
      <div className="flex-1 overflow-hidden">
        <InterchangeTable part={state.activePart} />
      </div>
    </div>
  )
}
