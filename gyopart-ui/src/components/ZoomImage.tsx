import { useRef, useState } from 'react'
import { ImageOff, Maximize2, ZoomIn, ZoomOut } from 'lucide-react'

const MIN = 1
const MAX = 6

/** An image you can zoom (buttons, wheel, double-click) and pan (drag). */
export function ZoomImage({ src, alt }: { src: string | null; alt: string }) {
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 })
  const [failed, setFailed] = useState<string | null>(null)
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null)
  const box = useRef<HTMLDivElement>(null)

  // Zoom keeping the point under (cx, cy) — relative to the box centre — fixed.
  const zoomAt = (factor: number, cx = 0, cy = 0) => setView(v => {
    const scale = Math.min(MAX, Math.max(MIN, v.scale * factor))
    if (scale === MIN) return { scale, x: 0, y: 0 }
    const k = scale / v.scale
    return { scale, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k }
  })
  const fromCentre = (e: { clientX: number; clientY: number }) => {
    const r = box.current!.getBoundingClientRect()
    return [e.clientX - r.left - r.width / 2, e.clientY - r.top - r.height / 2] as const
  }

  if (!src || failed === src) {
    return (
      <div className="flex aspect-[4/3] w-full flex-col items-center justify-center gap-1 rounded-lg border border-line bg-bg text-sm text-muted">
        <ImageOff className="size-7" />
        {src ? 'The diagram image failed to load.' : 'No image for this diagram.'}
        <span className="text-xs">The parts list still works.</span>
      </div>
    )
  }

  return (
    <div className="relative">
      <div
        ref={box}
        className={`relative aspect-[4/3] w-full touch-none overflow-hidden rounded-lg border border-line bg-white ${
          view.scale > 1 ? 'cursor-grab active:cursor-grabbing' : 'cursor-zoom-in'
        }`}
        onWheel={e => { const [cx, cy] = fromCentre(e); zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, cx, cy) }}
        onDoubleClick={e => { const [cx, cy] = fromCentre(e); zoomAt(view.scale >= MAX ? 0 : 2, cx, cy) }}
        onPointerDown={e => {
          if (view.scale === 1) return
          e.currentTarget.setPointerCapture(e.pointerId)
          drag.current = { x: e.clientX, y: e.clientY, ox: view.x, oy: view.y }
        }}
        onPointerMove={e => {
          const d = drag.current
          if (d) setView(v => ({ ...v, x: d.ox + e.clientX - d.x, y: d.oy + e.clientY - d.y }))
        }}
        onPointerUp={() => { drag.current = null }}
      >
        <img
          src={src}
          alt={alt}
          draggable={false}
          onError={() => setFailed(src)}
          className="absolute inset-0 size-full object-contain select-none"
          style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}
        />
      </div>
      <div className="absolute right-2 bottom-2 flex gap-1 rounded-lg border border-line bg-surface/90 p-0.5 shadow-sm">
        <button type="button" aria-label="Zoom in" onClick={() => zoomAt(1.5)} disabled={view.scale >= MAX}
          className="rounded-md p-1.5 hover:bg-hover disabled:opacity-40"><ZoomIn className="size-4" /></button>
        <button type="button" aria-label="Zoom out" onClick={() => zoomAt(1 / 1.5)} disabled={view.scale <= MIN}
          className="rounded-md p-1.5 hover:bg-hover disabled:opacity-40"><ZoomOut className="size-4" /></button>
        <button type="button" aria-label="Reset zoom" onClick={() => setView({ scale: 1, x: 0, y: 0 })}
          disabled={view.scale === 1} className="rounded-md p-1.5 hover:bg-hover disabled:opacity-40">
          <Maximize2 className="size-4" />
        </button>
      </div>
    </div>
  )
}
