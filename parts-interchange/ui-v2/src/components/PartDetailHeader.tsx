import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { ImageLightbox } from './ImageLightbox'
import type { Part, PartImage } from '../types'

function resolveImageUrl(img: PartImage['image']): string {
  return img.url || `/part-images/${img.bucket_path}`
}

interface Props { part: Part }

export function PartDetailHeader({ part }: Props) {
  const [lightboxImg, setLightboxImg] = useState<{ src: string; caption: string } | null>(null)
  const firstImage = part.images[0]
  const chips = [
    part.positions && { label: 'Position', value: part.positions },
    part.notes && { label: 'Notes', value: part.notes },
    part.replaces && { label: 'Replaces', value: part.replaces },
  ].filter(Boolean) as { label: string; value: string }[]

  return (
    <div className="p-6 border-b border-slate-800">
      <div className="flex items-start gap-4">
        {firstImage && (
          <button
            onClick={() => setLightboxImg({ src: resolveImageUrl(firstImage.image), caption: firstImage.part_image_text })}
            className="shrink-0"
          >
            <img src={resolveImageUrl(firstImage.image)} alt={part.title} className="w-16 h-16 object-cover rounded border border-slate-700 hover:border-amber-500 transition-colors" />
          </button>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-2xl font-mono text-amber-500 leading-none">{part.part_number}</p>
          <p className="text-lg text-white mt-1">{part.title}</p>
          {chips.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-3">
              {chips.map(c => (
                <Badge key={c.label} variant="outline" className="border-slate-700 text-zinc-400 text-xs">
                  {c.label}: {c.value}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </div>
      {lightboxImg && <ImageLightbox src={lightboxImg.src} caption={lightboxImg.caption} onClose={() => setLightboxImg(null)} />}
    </div>
  )
}
