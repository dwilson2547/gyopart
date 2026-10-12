import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router'
import { Car, Check, ChevronDown, Monitor, Moon, Plus, Sun, Warehouse } from 'lucide-react'
import { useTheme } from '../lib/theme'
import { useGarage, vehicleSubtitle, vehicleTitle } from '../state/garageContext'

const THEME_ICON = { system: Monitor, light: Sun, dark: Moon }

/** App bar (photo-dump style) + scrolling content area. */
export function Shell({ children }: { children: React.ReactNode }) {
  const { mode, cycle } = useTheme()
  const ThemeIcon = THEME_ICON[mode]
  return (
    <div className="flex h-dvh flex-col bg-bg text-text">
      <header className="z-20 flex h-13 shrink-0 items-center gap-1 border-b border-line bg-surface px-2">
        <Link to="/" className="px-2 text-lg font-semibold text-text hover:text-accent">gyopart</Link>
        <span className="flex-1" />
        <GarageSwitcher />
        <button
          type="button"
          onClick={cycle}
          aria-label={`Theme: ${mode}`}
          title={`Theme: ${mode} (click to change)`}
          className="inline-flex size-10 items-center justify-center rounded-full hover:bg-hover"
        >
          <ThemeIcon className="size-5" />
        </button>
      </header>
      <main className="min-h-0 flex-1 overflow-auto">{children}</main>
    </div>
  )
}

function GarageSwitcher() {
  const { vehicles, active, setActive } = useGarage()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  if (!vehicles.length) {
    return (
      <NavLink to="/garage" className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm hover:bg-hover">
        <Plus className="size-4" /> Add vehicle
      </NavLink>
    )
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label="Switch vehicle"
        className="flex max-w-[16rem] items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm hover:bg-hover sm:max-w-xs"
      >
        <Car className="size-4 shrink-0 text-muted" />
        <span className="truncate">{active ? [vehicleTitle(active), active.trim].filter(Boolean).join(' ') : 'Choose vehicle'}</span>
        <ChevronDown className="size-4 shrink-0 text-muted" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-30 mt-1 w-80 max-w-[calc(100vw-1rem)] rounded-lg border border-line bg-surface py-1 shadow-lg">
          <p className="section-label px-3 pt-1.5 pb-1">Garage</p>
          {vehicles.map(v => (
            <button
              key={v.car_id}
              role="menuitemradio"
              aria-checked={v.car_id === active?.car_id}
              onClick={() => { setActive(v.car_id); setOpen(false) }}
              className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-hover"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{vehicleTitle(v)}</span>
                <span className="block truncate text-xs text-muted">{vehicleSubtitle(v)}</span>
              </span>
              {v.car_id === active?.car_id && <Check className="mt-0.5 size-4 shrink-0 text-accent" />}
            </button>
          ))}
          <div className="mt-1 border-t border-line pt-1">
            <button
              role="menuitem"
              onClick={() => { setOpen(false); navigate('/garage') }}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-hover"
            >
              <Warehouse className="size-4 text-muted" /> Manage garage
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
