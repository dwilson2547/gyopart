import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { CheckCircle2, MapPin, Plus, Trash2, Warehouse, XCircle } from 'lucide-react'
import { AddVehicle } from '../components/AddVehicle'
import { useGarage, vehicleSubtitle, vehicleTitle } from '../state/garageContext'
import type { GarageVehicle } from '../types'

export function GaragePage() {
  const { vehicles, active, add, remove, setActive } = useGarage()
  const [adding, setAdding] = useState(vehicles.length === 0)
  const [flash, setFlash] = useState<number | null>(null)
  const [confirming, setConfirming] = useState<number | null>(null)

  useEffect(() => {
    if (flash === null) return
    const t = setTimeout(() => setFlash(null), 2000)
    return () => clearTimeout(t)
  }, [flash])

  const saved = (v: GarageVehicle) => {
    add(v)
    setAdding(false)
    setFlash(v.car_id)
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Garage</h1>
        {!adding && (
          <button
            onClick={() => setAdding(true)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
          >
            <Plus className="size-4" /> Add vehicle
          </button>
        )}
      </div>

      {adding && (
        <section className="rounded-xl border border-line bg-surface p-4 sm:p-5">
          <h2 className="mb-4 font-medium">{vehicles.length ? 'Add a vehicle' : 'Add your first vehicle'}</h2>
          <AddVehicle onSaved={saved} onCancel={vehicles.length ? () => setAdding(false) : undefined} />
        </section>
      )}

      {vehicles.length === 0 && !adding && (
        <div className="flex flex-col items-center gap-1 py-12 text-center text-muted">
          <Warehouse className="size-8" />
          <p>No vehicles yet.</p>
          <p className="text-sm">Add one to browse its parts catalogue.</p>
        </div>
      )}

      {vehicles.length > 0 && (
        <section aria-label="Vehicles" className="flex flex-col gap-2">
          {vehicles.map(v => {
            const isActive = v.car_id === active?.car_id
            return (
              <article
                key={v.car_id}
                className={`flex flex-wrap items-center gap-3 rounded-xl border bg-surface px-4 py-3 transition-colors duration-700 ${
                  flash === v.car_id ? 'border-accent bg-accent-soft' : isActive ? 'border-accent' : 'border-line'
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="truncate font-medium">{vehicleTitle(v)}</h3>
                    {isActive && (
                      <span className="rounded-full border border-accent px-2 py-0.5 text-xs text-accent">Active</span>
                    )}
                  </div>
                  <p className="truncate text-sm text-muted">{vehicleSubtitle(v)}</p>
                  {v.vin && <VinLine v={v} />}
                </div>
                <div className="flex items-center gap-1">
                  <Link
                    to={`/car/${v.car_id}`}
                    onClick={() => setActive(v.car_id)}
                    className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-hover"
                  >
                    Parts
                  </Link>
                  {!isActive && (
                    <button onClick={() => setActive(v.car_id)} className="rounded-lg px-3 py-1.5 text-sm hover:bg-hover">
                      Make active
                    </button>
                  )}
                  {confirming === v.car_id ? (
                    <span className="flex items-center gap-1 text-sm">
                      <span className="text-muted">Remove?</span>
                      <button onClick={() => { remove(v.car_id); setConfirming(null) }}
                        className="rounded-lg bg-danger px-2.5 py-1 text-white hover:opacity-90">Remove</button>
                      <button onClick={() => setConfirming(null)} className="rounded-lg px-2.5 py-1 hover:bg-hover">Keep</button>
                    </span>
                  ) : (
                    <button onClick={() => setConfirming(v.car_id)} aria-label={`Remove ${vehicleTitle(v)}`}
                      className="inline-flex size-9 items-center justify-center rounded-full text-muted hover:bg-hover hover:text-danger">
                      <Trash2 className="size-4" />
                    </button>
                  )}
                </div>
              </article>
            )
          })}
        </section>
      )}

      <HomeSettings />
    </div>
  )
}

function VinLine({ v }: { v: GarageVehicle }) {
  const d = v.decoded
  const agrees = d && d.year === v.year && d.make?.toLowerCase() === v.make.toLowerCase()
  return (
    <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
      <span className="font-mono tracking-wide">{v.vin}</span>
      {d && (agrees
        ? <CheckCircle2 className="size-3.5 text-ok" aria-label="VIN verified" />
        : <XCircle className="size-3.5 text-danger" aria-label="VIN differs" />)}
    </p>
  )
}

function HomeSettings() {
  const { zip, radius, setHome } = useGarage()
  const [z, setZ] = useState(zip)
  const [r, setR] = useState(String(radius))
  const [saved, setSaved] = useState(false)
  const zipBad = !/^\d{5}$/.test(z)
  const radiusN = Number(r)
  const radiusBad = !Number.isFinite(radiusN) || radiusN < 1 || radiusN > 500
  const dirty = z !== zip || radiusN !== radius

  useEffect(() => {
    if (!saved) return
    const t = setTimeout(() => setSaved(false), 2000)
    return () => clearTimeout(t)
  }, [saved])

  return (
    <section className="rounded-xl border border-line bg-surface p-4 sm:p-5">
      <h2 className="mb-1 flex items-center gap-2 font-medium"><MapPin className="size-4 text-muted" /> Home</h2>
      <p className="mb-3 text-sm text-muted">Yard searches look this far from here.</p>
      <form
        className="flex flex-wrap items-start gap-3"
        onSubmit={e => { e.preventDefault(); if (!zipBad && !radiusBad) { setHome(z, radiusN); setSaved(true) } }}
      >
        <div>
          <label htmlFor="zip" className="section-label mb-1 block">ZIP</label>
          <input id="zip" value={z} onChange={e => setZ(e.target.value.trim())} inputMode="numeric" maxLength={5}
            aria-invalid={zipBad}
            className={`w-28 rounded-lg border bg-bg px-3 py-2 text-sm outline-none focus:border-accent ${zipBad ? 'border-danger' : 'border-line'}`} />
          {zipBad && <p className="mt-1 text-xs text-danger">5-digit US ZIP</p>}
        </div>
        <div>
          <label htmlFor="radius" className="section-label mb-1 block">Radius (mi)</label>
          <input id="radius" value={r} onChange={e => setR(e.target.value.trim())} inputMode="numeric"
            aria-invalid={radiusBad}
            className={`w-28 rounded-lg border bg-bg px-3 py-2 text-sm outline-none focus:border-accent ${radiusBad ? 'border-danger' : 'border-line'}`} />
          {radiusBad && <p className="mt-1 text-xs text-danger">1–500 miles</p>}
        </div>
        <div className="flex items-center gap-2 pt-5">
          <button type="submit" disabled={!dirty || zipBad || radiusBad}
            className="rounded-lg border border-line px-3 py-2 text-sm hover:bg-hover disabled:opacity-40">Save</button>
          {saved && <span className="text-sm text-ok">Saved</span>}
        </div>
      </form>
    </section>
  )
}
