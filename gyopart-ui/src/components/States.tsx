import { Loader2, RotateCw, type LucideIcon } from 'lucide-react'

/** Centred muted icon + line + hint (photo-dump's empty state). */
export function Empty({ icon: Icon, title, hint, children }: {
  icon: LucideIcon; title: string; hint?: React.ReactNode; children?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-1 px-4 py-12 text-center text-muted">
      <Icon className="mb-1 size-8" />
      <p className="text-text">{title}</p>
      {hint && <p className="max-w-sm text-sm">{hint}</p>}
      {children}
    </div>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted" role="status">
      <Loader2 className="size-4 animate-spin" /> {label}
    </div>
  )
}

export function ErrorLine({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="m-3 flex flex-wrap items-center gap-2 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
      {message}
      {onRetry && (
        <button type="button" onClick={onRetry} className="inline-flex items-center gap-1 text-accent hover:underline">
          <RotateCw className="size-3.5" /> Retry
        </button>
      )}
    </div>
  )
}
