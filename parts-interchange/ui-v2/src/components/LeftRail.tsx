import { LeftRailContent } from './LeftRailContent'

export function LeftRail() {
  return (
    <aside className="w-80 shrink-0 h-full flex flex-col border-r border-slate-800 bg-slate-900 overflow-hidden">
      <LeftRailContent constrainGarage />
    </aside>
  )
}
