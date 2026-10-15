import { useState } from 'react'
import { Link, NavLink } from 'react-router'
import { Car, ChevronDown, Hash, Monitor, Moon, Sun, Warehouse, X } from 'lucide-react'
import { useTheme } from '../lib/theme'
import { PartNumberBox } from './PartNumberBox'
import { useCurrentCar } from '../lib/useCurrentCar'
import { vehicleSubtitle, vehicleTitle } from '../state/garageContext'
import { useVehiclePicker } from '../state/vehiclePickerContext'
import { VehiclePickerProvider } from './VehiclePicker'

const THEME_ICON = { system: Monitor, light: Sun, dark: Moon }

/** App bar (photo-dump style) + scrolling content area. */
export function Shell({ children }: { children: React.ReactNode }) {
  const { mode, cycle } = useTheme()
  const ThemeIcon = THEME_ICON[mode]
  const [lookupOpen, setLookupOpen] = useState(false) // phones: the box opens as a row under the bar
  return (
    <VehiclePickerProvider>
      <div className="flex h-dvh flex-col bg-bg text-text">
        <header className="z-20 flex h-13 shrink-0 items-center gap-0.5 border-b border-line bg-surface px-1 sm:gap-1 sm:px-2">
          <Link to="/" className="px-2 text-lg font-semibold text-text hover:text-accent">gyopart</Link>
          <div className="ml-2 hidden max-w-md flex-1 sm:block"><PartNumberBox /></div>
          <span className="flex-1" />
          <button type="button" onClick={() => setLookupOpen(o => !o)} aria-label="Look up a part number" aria-expanded={lookupOpen}
            className="inline-flex size-10 items-center justify-center rounded-full hover:bg-hover sm:hidden">
            {lookupOpen ? <X className="size-5" /> : <Hash className="size-5" />}
          </button>
          <NavLink to="/yards" aria-label="Yards" title="Yards"
            className={({ isActive }) => `inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm hover:bg-hover ${isActive ? 'text-accent' : ''}`}>
            <Warehouse className="size-4" /><span className="hidden md:inline">Yards</span>
          </NavLink>
          <VehicleBlock />
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
        {lookupOpen && (
          <div className="z-10 border-b border-line bg-surface px-3 py-2 sm:hidden">
            <PartNumberBox autoFocus onDone={() => setLookupOpen(false)} />
          </div>
        )}
        <main className="min-h-0 flex-1 overflow-auto">{children}</main>
      </div>
    </VehiclePickerProvider>
  )
}

/** The car being browsed; opens the vehicle picker. */
function VehicleBlock() {
  const car = useCurrentCar()
  const { open } = useVehiclePicker()
  return (
    <button type="button" onClick={open} aria-label="Change vehicle" aria-haspopup="dialog"
      className="flex max-w-[10.5rem] min-w-0 items-center gap-2 rounded-lg border border-line px-2 py-1 text-left hover:bg-hover sm:max-w-xs sm:px-2.5">
      <Car className="hidden size-4 shrink-0 text-muted sm:block" />
      <span className="min-w-0 flex-1 leading-tight">
        {car ? (
          <>
            <span className="block truncate text-sm">{vehicleTitle(car)}</span>
            <span className="block truncate text-xs text-muted">{vehicleSubtitle(car) || 'Change vehicle'}</span>
          </>
        ) : <span className="block py-1.5 text-sm">Choose vehicle</span>}
      </span>
      <ChevronDown className="size-4 shrink-0 text-muted" />
    </button>
  )
}
