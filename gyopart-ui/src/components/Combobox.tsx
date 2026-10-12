import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, Loader2, RotateCw, X } from 'lucide-react'
import type { Named } from '../types'

interface Props {
  label: string
  options: Named[]
  value: number | null
  onChange: (id: number | null) => void
  disabled?: boolean
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  placeholder?: string
  /** Options sharing these ids are listed first under a "Matches VIN" heading. */
  highlightIds?: Set<number>
}

/** Searchable select over live options: type to filter, arrows + Enter to pick, Esc to close. */
export function Combobox({
  label, options, value, onChange, disabled, loading, error, onRetry, placeholder, highlightIds,
}: Props) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  const selected = options.find(o => o.id === value) ?? null
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const hits = q ? options.filter(o => o.name.toLowerCase().includes(q)) : options
    if (!highlightIds?.size) return hits
    return [...hits.filter(o => highlightIds.has(o.id)), ...hits.filter(o => !highlightIds.has(o.id))]
  }, [options, query, highlightIds])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${cursor}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  const pick = (o: Named) => {
    onChange(o.id)
    setOpen(false)
    setQuery('')
  }

  const openList = () => {
    if (disabled) return
    setOpen(true)
    setQuery('')
    setCursor(Math.max(0, filtered.findIndex(o => o.id === value)))
  }

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!open) return openList()
      setCursor(c => Math.min(c + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor(c => Math.max(c - 1, 0))
    } else if (e.key === 'Enter') {
      if (open && filtered[cursor]) {
        e.preventDefault()
        pick(filtered[cursor])
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const firstOther = highlightIds?.size ? filtered.findIndex(o => !highlightIds.has(o.id)) : -1

  return (
    <div ref={rootRef} className="relative">
      <label htmlFor={id} className="section-label mb-1 block">{label}</label>
      <div
        className={`flex items-center rounded-lg border bg-bg transition-colors ${
          disabled ? 'border-line opacity-55' : error ? 'border-danger' : open ? 'border-accent' : 'border-line'
        }`}
      >
        <input
          id={id}
          ref={inputRef}
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          autoComplete="off"
          disabled={disabled}
          value={open ? query : selected?.name ?? ''}
          placeholder={loading ? 'Loading…' : placeholder ?? `Choose ${label.toLowerCase()}`}
          onChange={e => { setQuery(e.target.value); setOpen(true); setCursor(0) }}
          onFocus={openList}
          onClick={() => !open && openList()}
          onKeyDown={onKey}
          className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm text-text outline-none placeholder:text-muted disabled:cursor-not-allowed"
        />
        {loading ? (
          <Loader2 className="mr-2 size-4 animate-spin text-muted" aria-label="loading" />
        ) : selected && !disabled ? (
          <button
            type="button"
            aria-label={`Clear ${label}`}
            onClick={() => { onChange(null); inputRef.current?.focus() }}
            className="mr-1 rounded p-1 text-muted hover:bg-hover"
          >
            <X className="size-4" />
          </button>
        ) : (
          <ChevronDown className="mr-2 size-4 text-muted" aria-hidden />
        )}
      </div>

      {error && (
        <p className="mt-1 flex items-center gap-2 text-xs text-danger">
          {error}
          {onRetry && (
            <button type="button" onClick={onRetry} className="inline-flex items-center gap-1 text-accent hover:underline">
              <RotateCw className="size-3" /> Retry
            </button>
          )}
        </p>
      )}

      {open && !disabled && (
        <ul
          id={`${id}-list`}
          ref={listRef}
          role="listbox"
          className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-line bg-surface py-1 shadow-lg"
        >
          {filtered.length === 0 && (
            <li className="px-3 py-2 text-sm text-muted">{loading ? 'Loading…' : 'No matches'}</li>
          )}
          {filtered.map((o, i) => (
            <li key={o.id} role="presentation">
              {i === 0 && highlightIds?.has(o.id) && <div className="section-label px-3 pt-1 pb-0.5">Matches VIN</div>}
              {i === firstOther && i > 0 && <div className="section-label border-t border-line px-3 pt-2 pb-0.5">Other</div>}
              <div
                role="option"
                aria-selected={o.id === value}
                data-index={i}
                onMouseDown={e => { e.preventDefault(); pick(o) }}
                onMouseEnter={() => setCursor(i)}
                className={`flex cursor-pointer items-center justify-between px-3 py-1.5 text-sm ${
                  i === cursor ? 'bg-hover' : ''
                }`}
              >
                <span>{o.name}</span>
                {o.id === value && <Check className="size-4 text-accent" />}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
