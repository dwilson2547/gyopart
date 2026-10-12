import { useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Hash, Loader2, X } from 'lucide-react'
import { api, errorMessage } from '../api'
import { useGarage } from '../state/garageContext'
import type { PartLookup, PartNumberHit } from '../types'

const normalize = (s: string) => s.replace(/[^A-Za-z0-9]/g, '').toUpperCase()

/** Global part-number box: suggestions while typing, Enter goes straight to an exact match. */
export function PartNumberBox({ autoFocus, onDone }: { autoFocus?: boolean; onDone?: () => void }) {
  const id = useId()
  const navigate = useNavigate()
  const { active } = useGarage()
  const [text, setText] = useState('')
  const [result, setResult] = useState<PartLookup | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)
  const [submitted, setSubmitted] = useState(false)
  const [moved, setMoved] = useState(false) // arrowed through the list: Enter picks the highlighted row
  const rootRef = useRef<HTMLDivElement>(null)
  const n = normalize(text)

  // Debounced lookup; stale answers dropped.
  useEffect(() => {
    if (n.length < 3) return
    let live = true
    const t = setTimeout(() => {
      setBusy(true)
      api.lookupPartNumber(n)
        .then(r => { if (live) { setResult(r); setError(null) } })
        .catch(e => { if (live) { setResult(null); setError(errorMessage(e)) } })
        .finally(() => { if (live) setBusy(false) })
    }, 250)
    return () => { live = false; clearTimeout(t) }
  }, [n])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (!rootRef.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const current = result && result.q === n ? result : null
  const hits = current ? [...current.exact, ...current.suggestions] : []

  const go = (h: PartNumberHit) => {
    navigate(`/part/${h.id}${active ? `?car=${active.car_id}` : ''}`)
    setText('')
    setResult(null)
    setOpen(false)
    setSubmitted(false)
    setMoved(false)
    onDone?.()
  }

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault(); setOpen(true); setMoved(true)
      setCursor(c => (moved ? Math.min(c + 1, hits.length - 1) : 0))
    } else if (e.key === 'ArrowUp') { e.preventDefault(); setMoved(true); setCursor(c => Math.max(c - 1, 0)) }
    else if (e.key === 'Escape') { setOpen(false); onDone?.() }
    else if (e.key === 'Enter') {
      e.preventDefault()
      setSubmitted(true)
      setOpen(true)
      if (moved && open && hits[cursor]) return go(hits[cursor])
      if (current?.exact.length === 1) return go(current.exact[0])
    }
  }

  const tooShort = n.length > 0 && n.length < 3
  const waiting = n.length >= 3 && (busy || !current) && !error
  let message: string | null = null
  if (tooShort && submitted) message = 'Type at least 3 letters or digits.'
  else if (error && n.length >= 3) message = `Lookup failed: ${error}`
  else if (current && !hits.length) message = `No part numbered ${text.trim()}.`
  else if (submitted && current && !current.exact.length) message = `No exact match for ${text.trim()} — did you mean:`
  const several = (current?.exact.length ?? 0) > 1

  return (
    <div ref={rootRef} className="relative w-full">
      <div className="flex items-center rounded-lg border border-line bg-bg focus-within:border-accent">
        <Hash className="ml-2.5 size-4 shrink-0 text-muted" />
        <input
          id={id}
          role="combobox"
          aria-label="Look up a part number"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          autoComplete="off"
          spellCheck={false}
          autoFocus={autoFocus}
          value={text}
          onChange={e => { setText(e.target.value); setOpen(true); setCursor(0); setMoved(false); setSubmitted(false) }}
          onFocus={() => text && setOpen(true)}
          onKeyDown={onKey}
          placeholder="Part number, e.g. DG1Z-10346-F"
          className="min-w-0 flex-1 bg-transparent px-2 py-1.5 font-mono text-sm outline-none placeholder:font-sans placeholder:text-muted"
        />
        {waiting && <Loader2 className="mr-2 size-4 animate-spin text-muted" aria-label="looking up" />}
        {text && !waiting && (
          <button type="button" aria-label="Clear part number" onClick={() => { setText(''); setResult(null); setOpen(false) }}
            className="mr-1 rounded p-1 text-muted hover:bg-hover"><X className="size-4" /></button>
        )}
      </div>

      {open && (message || hits.length > 0) && (
        <div id={`${id}-list`} className="absolute z-40 mt-1 w-full min-w-72 overflow-hidden rounded-lg border border-line bg-surface shadow-lg">
          {message && <p role="status" className={`px-3 py-2 text-sm ${hits.length ? 'text-muted' : ''}`}>{message}</p>}
          {several && <p className="section-label px-3 pt-2">Same number, several manufacturers</p>}
          <ul role="listbox" className="max-h-80 overflow-auto py-1">
            {hits.map((h, i) => {
              const isExact = i < (current?.exact.length ?? 0)
              return (
                <li key={h.id} role="option" aria-selected={i === cursor}>
                  {i === (current?.exact.length ?? 0) && i > 0 && <div className="section-label border-t border-line px-3 pt-2 pb-1">Starting with {n}</div>}
                  <button type="button" onMouseDown={e => { e.preventDefault(); go(h) }} onMouseEnter={() => { setCursor(i); setMoved(true) }}
                    className={`flex w-full items-baseline gap-2 px-3 py-1.5 text-left ${moved && i === cursor ? 'bg-hover' : ''}`}>
                    <span className="font-mono text-sm">{h.part_number}</span>
                    <span className="min-w-0 flex-1 truncate text-sm text-muted">{h.title}</span>
                    <span className="shrink-0 text-xs text-muted">{h.manufacturer}</span>
                    {isExact && !several && <span className="shrink-0 rounded-full bg-ok-soft px-1.5 text-xs text-ok">exact</span>}
                  </button>
                </li>
              )
            })}
          </ul>
          {!submitted && current?.exact.length === 1 && <p className="border-t border-line px-3 py-1.5 text-xs text-muted">Enter opens the exact match</p>}
        </div>
      )}
    </div>
  )
}
