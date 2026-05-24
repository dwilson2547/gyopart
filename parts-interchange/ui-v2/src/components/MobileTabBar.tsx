import { Car, List } from 'lucide-react'

interface Props {
  activeTab: 0 | 1
  onChange: (tab: 0 | 1) => void
}

export function MobileTabBar({ activeTab, onChange }: Props) {
  const tabs = [
    { index: 0, label: 'My Car', Icon: Car },
    { index: 1, label: 'Interchange', Icon: List },
  ] as const

  return (
    <nav className="fixed bottom-0 inset-x-0 z-30 h-14 bg-slate-900 border-t border-slate-800 flex md:hidden">
      {tabs.map(({ index, label, Icon }) => (
        <button
          key={index}
          onClick={() => onChange(index)}
          className={`flex-1 flex flex-col items-center justify-center gap-0.5 text-xs transition-colors ${
            activeTab === index ? 'text-amber-500 border-t-2 border-amber-500' : 'text-zinc-500'
          }`}
        >
          <Icon size={18} />
          {label}
        </button>
      ))}
    </nav>
  )
}
