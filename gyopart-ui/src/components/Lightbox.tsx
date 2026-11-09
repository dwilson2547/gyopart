import { useEffect } from 'react'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { ZoomImage } from './ZoomImage'

/** Full-screen image viewer: zoom/pan like a diagram, prev/next (arrow keys too), Esc to close. */
export function Lightbox({ images, index, onIndex, onClose, label }: {
  images: string[]; index: number; onIndex: (i: number) => void; onClose: () => void; label: string
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft' && index > 0) onIndex(index - 1)
      else if (e.key === 'ArrowRight' && index < images.length - 1) onIndex(index + 1)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [index, images.length, onIndex, onClose])

  return (
    <div role="dialog" aria-modal="true" aria-label={label} className="fixed inset-0 z-50 flex items-center justify-center bg-black/90"
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} className="w-[min(92vw,80rem)]">
        <ZoomImage key={images[index]} src={images[index]} alt={`${label} ${index + 1}`} boxClass="h-[85dvh] w-full rounded-lg" kind="picture" />
      </div>
      <button aria-label="Close" onClick={onClose} className="absolute top-3 right-3 rounded-full p-2 text-white hover:bg-white/10">
        <X className="size-6" />
      </button>
      {images.length > 1 && (
        <>
          <button aria-label="Previous picture" disabled={index === 0}
            onClick={e => { e.stopPropagation(); onIndex(index - 1) }}
            className="absolute left-2 rounded-full p-2 text-white hover:bg-white/10 disabled:opacity-25">
            <ChevronLeft className="size-8" />
          </button>
          <button aria-label="Next picture" disabled={index === images.length - 1}
            onClick={e => { e.stopPropagation(); onIndex(index + 1) }}
            className="absolute right-2 rounded-full p-2 text-white hover:bg-white/10 disabled:opacity-25">
            <ChevronRight className="size-8" />
          </button>
          <span className="absolute bottom-4 text-sm text-white/80">{index + 1} / {images.length}</span>
        </>
      )}
    </div>
  )
}
