import { useState } from 'react'
import { MessageSquare } from 'lucide-react'
import { ActiveVehicleBadge } from './ActiveVehicleBadge'
import { FeedbackModal } from './FeedbackModal'

export function TopBar() {
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  return (
    <header className="fixed top-0 inset-x-0 z-30 h-14 bg-slate-900 border-b border-slate-800 flex items-center px-4 gap-4">
      <span className="text-white font-semibold text-sm shrink-0">Parts Interchange</span>
      <div className="flex-1 flex justify-center">
        <ActiveVehicleBadge />
      </div>
      <button onClick={() => setFeedbackOpen(true)} className="text-zinc-400 hover:text-white shrink-0" title="Send feedback">
        <MessageSquare size={18} />
      </button>
      <FeedbackModal open={feedbackOpen} onClose={() => setFeedbackOpen(false)} />
    </header>
  )
}
