import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { Check, Warehouse, X } from 'lucide-react'
import { useChooseCar } from '../lib/useChooseCar'
import { useCurrentCar } from '../lib/useCurrentCar'
import { useGarage, vehicleSubtitle, vehicleTitle } from '../state/garageContext'
import { VehiclePickerContext } from '../state/vehiclePickerContext'
import type { GarageVehicle } from '../types'
import { AddVehicle } from './AddVehicle'

/** Provides useVehiclePicker().open() and renders the modal it opens. */
export function VehiclePickerProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const value = useMemo(() => ({ open: () => setOpen(true) }), [])
  return (
    <VehiclePickerContext.Provider value={value}>
      {children}
      {open && <VehicleDialog onClose={() => setOpen(false)} />}
    </VehiclePickerContext.Provider>
  )
}

function VehicleDialog({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    // A combobox closing its own list on Escape marks the event handled; only a bare Escape closes the modal.
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !e.defaultPrevented) onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div role="dialog" aria-modal="true" aria-label="Choose a vehicle" onClick={onClose}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/50 p-3 sm:p-8">
      <div onClick={e => e.stopPropagation()} className="w-full max-w-4xl rounded-xl border border-line bg-surface shadow-xl">
        <div className="flex items-center justify-between border-b border-line py-1.5 pr-2 pl-4">
          <h2 className="font-semibold">Choose a vehicle</h2>
          <button onClick={onClose} aria-label="Close" className="rounded-full p-2 hover:bg-hover"><X className="size-5" /></button>
        </div>
        <div className="p-4 sm:p-5"><VehicleChooser onChosen={onClose} /></div>
      </div>
    </div>
  )
}

/** Garage quick-pick plus the full year → engine picker. Used in the modal and on the home page. */
export function VehicleChooser({ onChosen }: { onChosen?: () => void }) {
  const { vehicles } = useGarage()
  const current = useCurrentCar()
  const choose = useChooseCar()
  const [save, setSave] = useState(true)
  const pick = (v: GarageVehicle, saveIt: boolean) => { choose(v, saveIt); onChosen?.() }

  return (
    <div className="flex flex-col gap-6">
      {vehicles.length > 0 && (
        <section aria-label="Your garage">
          <Heading label="Your garage" onLeave={onChosen} />
          <div className="grid gap-2 sm:grid-cols-2">
            {vehicles.map(v => {
              const isCurrent = v.car_id === current?.car_id
              return (
                <button key={v.car_id} onClick={() => pick(v, false)} aria-current={isCurrent || undefined}
                  className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-left hover:bg-hover ${
                    isCurrent ? 'border-accent' : 'border-line'}`}>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{vehicleTitle(v)}</span>
                    <span className="block truncate text-xs text-muted">{vehicleSubtitle(v)}</span>
                  </span>
                  {isCurrent && <Check className="mt-0.5 size-4 shrink-0 text-accent" />}
                </button>
              )
            })}
          </div>
        </section>
      )}
      <section aria-label="Another vehicle">
        {vehicles.length ? <p className="section-label mb-2">Another vehicle</p> : <Heading label="Pick a vehicle" onLeave={onChosen} />}
        <AddVehicle submitLabel="Browse parts" onSaved={v => pick(v, save)}
          extra={
            <label className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={save} onChange={e => setSave(e.target.checked)} className="accent-[var(--accent)]" />
              Save to garage
            </label>
          } />
      </section>
    </div>
  )
}

/** Section label with the Manage garage link — the garage page also holds the home ZIP, so it stays
 *  reachable with an empty garage. */
function Heading({ label, onLeave }: { label: string; onLeave?: () => void }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-2">
      <p className="section-label">{label}</p>
      <Link to="/garage" onClick={onLeave} className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
        <Warehouse className="size-3.5" /> Manage garage
      </Link>
    </div>
  )
}
