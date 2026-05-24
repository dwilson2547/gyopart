import { useEffect } from 'react'

interface Props {
  src: string
  caption: string
  onClose: () => void
}

export function ImageLightbox({ src, caption, onClose }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-sm bg-black/70"
      onClick={onClose}
    >
      <div className="max-w-3xl w-full mx-4" onClick={e => e.stopPropagation()}>
        <img src={src} alt={caption} className="w-full rounded-lg" />
        {caption && <p className="text-sm text-zinc-400 text-center mt-2">{caption}</p>}
      </div>
    </div>
  )
}
