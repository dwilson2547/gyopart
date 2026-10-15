import { useEffect, useRef, useState } from 'react'
import { ImageOff, Maximize2, ZoomIn, ZoomOut } from 'lucide-react'

const MIN = 1
const MAX = 6

const DIAGRAM_BOX = 'aspect-[4/3] max-h-[min(65vh,38rem)] w-full rounded-lg border border-line'

/** An image you can zoom (buttons, wheel, double-click, pinch) and pan (drag). `boxClass` sizes the frame. */
export function ZoomImage({ src, alt, boxClass = DIAGRAM_BOX, kind = 'diagram' }: {
  src: string | null; alt: string; boxClass?: string; kind?: 'diagram' | 'picture'
}) {
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 })
  const [failed, setFailed] = useState<string | null>(null)
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null)
  const pointers = useRef(new Map<number, { x: number; y: number }>()) // touches/mouse currently down, for pinch
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

  // Native listener: React's onWheel is passive, so it can't stop the page scrolling while zooming.
  const showing = !!src && failed !== src
  useEffect(() => {
    const el = box.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const [cx, cy] = fromCentre(e)
      zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, cx, cy)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [showing])

  if (!showing) {
    return (
      <div className={`flex flex-col items-center justify-center gap-1 bg-bg text-sm text-muted ${boxClass}`}>
        <ImageOff className="size-7" />
        {src ? `The ${kind === 'diagram' ? 'diagram image' : 'picture'} failed to load.` : `No image for this ${kind}.`}
        {kind === 'diagram' && <span className="text-xs">The parts list still works.</span>}
      </div>
    )
  }

  return (
    <div className="relative">
      <div
        ref={box}
        className={`relative touch-none overflow-hidden bg-white ${boxClass} ${
          view.scale > 1 ? 'cursor-grab active:cursor-grabbing' : 'cursor-zoom-in'
        }`}
        onDoubleClick={e => { const [cx, cy] = fromCentre(e); zoomAt(view.scale >= MAX ? 0 : 2, cx, cy) }}
        onPointerDown={e => {
          e.currentTarget.setPointerCapture(e.pointerId)
          pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
          // One pointer pans (once zoomed); a second one turns it into a pinch.
          drag.current = pointers.current.size === 1 && view.scale > 1
            ? { x: e.clientX, y: e.clientY, ox: view.x, oy: view.y } : null
        }}
        onPointerMove={e => {
          const pts = pointers.current
          const prev = pts.get(e.pointerId)
          if (!prev) return
          if (pts.size === 2) {
            const other = [...pts.entries()].find(([id]) => id !== e.pointerId)![1]
            const before = Math.hypot(prev.x - other.x, prev.y - other.y)
            const after = Math.hypot(e.clientX - other.x, e.clientY - other.y)
            pts.set(e.pointerId, { x: e.clientX, y: e.clientY })
            if (before > 0) {
              const [cx, cy] = fromCentre({ clientX: (e.clientX + other.x) / 2, clientY: (e.clientY + other.y) / 2 })
              zoomAt(after / before, cx, cy)
            }
            return
          }
          pts.set(e.pointerId, { x: e.clientX, y: e.clientY })
          const d = drag.current
          if (d) setView(v => ({ ...v, x: d.ox + e.clientX - d.x, y: d.oy + e.clientY - d.y }))
        }}
        onPointerUp={e => { pointers.current.delete(e.pointerId); drag.current = null }}
        onPointerCancel={e => { pointers.current.delete(e.pointerId); drag.current = null }}
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
