import { useEffect, useRef, useState } from 'react'
import { X, ZoomIn } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context/AppContext'
import type { DiagramDetail, Part } from '../types'

interface Props {
  diagramId: number
  onPartSelect: (part: Part) => void
}

export function DiagramView({ diagramId, onPartSelect }: Props) {
  const { state } = useApp()
  const [detail, setDetail] = useState<DiagramDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [zoomed, setZoomed] = useState(false)
  const dialogRef = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    setDetail(null)
    setLoading(true)
    api.diagram(diagramId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [diagramId])

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (zoomed) {
      dialog.showModal()
    } else {
      dialog.close()
    }
  }, [zoomed])

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-slate-400 text-sm">Loading diagram…</p>
      </div>
    )
  }

  if (!detail) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-slate-500 text-sm">Failed to load diagram.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Diagram image */}
      <div className="flex-shrink-0 p-4 border-b border-slate-700 bg-slate-900/50 overflow-auto max-h-96">
        <div className="relative group inline-block w-full">
          <img
            src={detail.image_url}
            alt={detail.image_alt}
            className="max-w-full h-auto mx-auto block cursor-zoom-in"
            onClick={() => setZoomed(true)}
          />
          <button
            onClick={() => setZoomed(true)}
            className="absolute top-2 right-2 bg-slate-800/80 text-slate-300 hover:text-white p-1.5 rounded opacity-0 group-hover:opacity-100 transition-opacity"
            title="View full size"
          >
            <ZoomIn size={14} />
          </button>
        </div>
        {detail.image_alt && (
          <p className="text-xs text-slate-500 text-center mt-2">{detail.image_alt}</p>
        )}
      </div>

      {/* Parts list */}
      <div className="flex-1 overflow-y-auto p-4">
        <p className="text-xs text-slate-500 mb-3 font-medium uppercase tracking-wide">
          Parts in this diagram — click to search junkyards
        </p>
        <div className="grid grid-cols-1 gap-1">
          {detail.parts.map(p => {
            const isActive = state.activePart?.id === p.id
            return (
              <button
                key={`${p.id}-${p.part_index}`}
                data-testid="diagram-part"
                onClick={() => onPartSelect(p)}
                className={`w-full text-left px-3 py-2 rounded text-sm transition-colors flex items-start gap-2 ${
                  isActive
                    ? 'bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/40'
                    : 'hover:bg-slate-800 text-slate-200'
                }`}
              >
                <span className="flex-shrink-0 text-xs text-slate-500 w-6 mt-0.5 font-mono">{p.part_index}</span>
                <span>
                  <span className="block font-medium">{p.title ?? 'Unnamed Part'}</span>
                  {p.part_number && (
                    <span className="text-slate-500 text-xs">#{p.part_number}</span>
                  )}
                  {p.description && (
                    <span className="block text-slate-500 text-xs mt-0.5">{p.description}</span>
                  )}
                </span>
              </button>
            )
          })}
          {detail.parts.length === 0 && (
            <p className="text-slate-500 text-sm">No parts listed for this diagram.</p>
          )}
        </div>
      </div>

      {/* Fullscreen dialog */}
      <dialog
        ref={dialogRef}
        className="bg-slate-950 p-0 max-w-[95vw] max-h-[95vh] rounded-lg shadow-2xl backdrop:bg-black/80"
        onClick={(e) => { if (e.target === dialogRef.current) setZoomed(false) }}
        onKeyDown={(e) => { if (e.key === 'Escape') setZoomed(false) }}
      >
        <div className="relative">
          <button
            onClick={() => setZoomed(false)}
            className="absolute top-3 right-3 z-10 bg-slate-800/90 text-slate-300 hover:text-white p-1.5 rounded"
          >
            <X size={16} />
          </button>
          {detail && (
            <img
              src={detail.image_url}
              alt={detail.image_alt}
              className="block max-w-[95vw] max-h-[95vh] w-auto h-auto"
            />
          )}
        </div>
      </dialog>
    </div>
  )
}
