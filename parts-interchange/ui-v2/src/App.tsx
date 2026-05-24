import { useEffect, useState } from 'react'
import { TopBar } from './components/TopBar'
import { LeftRail } from './components/LeftRail'
import { LeftRailContent } from './components/LeftRailContent'
import { RightPanel } from './components/RightPanel'
import { MobileTabBar } from './components/MobileTabBar'
import { useApp } from './context/AppContext'

export default function App() {
  const { state } = useApp()
  const [mobileTab, setMobileTab] = useState<0 | 1>(0)

  useEffect(() => {
    if (state.activePart) setMobileTab(1)
  }, [state.activePart])

  return (
    <div className="flex flex-col h-screen bg-slate-950">
      <TopBar />

      {/* Desktop layout */}
      <div className="hidden md:flex flex-1 overflow-hidden pt-14">
        <LeftRail />
        <main className="flex-1 overflow-hidden bg-slate-950">
          <RightPanel />
        </main>
      </div>

      {/* Mobile layout */}
      <div className="flex md:hidden flex-1 overflow-hidden pt-14 pb-14">
        {mobileTab === 0 ? (
          <div className="flex-1 overflow-y-auto bg-slate-900 flex flex-col">
            <LeftRailContent />
          </div>
        ) : (
          <div className="flex-1 overflow-hidden">
            <RightPanel />
          </div>
        )}
      </div>
      <MobileTabBar activeTab={mobileTab} onChange={setMobileTab} />
    </div>
  )
}
