import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { ArrowLeft, ListTree, MapPin, Navigation, PackageX, Phone, Star, Warehouse } from 'lucide-react'
import { api } from '../api'
import { Empty, ErrorLine, Loading } from '../components/States'
import { mapsUrl, relativeDay } from '../lib/format'
import { useAsync } from '../lib/useAsync'
import { useGarage } from '../state/garageContext'
import type { Yard, YardVehicle } from '../types'

/** Workflow 5: yards near home holding a vehicle the part interchanges with. */
export function PartYardsPage() {
  const partId = Number(useParams().partId)
  const [params, setParams] = useSearchParams()
  const { zip: homeZip, radius: homeRadius, homeYard, setHomeYard } = useGarage()
  const zip = params.get('zip') ?? homeZip
  const radius = Number(params.get('radius') ?? homeRadius)
  const exactOnly = params.get('exact') === '1'
  const carId = params.get('car')
  const carQuery = carId ? `?car=${carId}` : ''

  const part = useAsync(() => api.part(partId), [partId], Number.isFinite(partId))
  const ic = useAsync(() => api.interchange(partId), [partId], Number.isFinite(partId))
  const yards = useAsync(() => api.searchYards(partId, zip, radius), [partId, zip, radius], Number.isFinite(partId))

  const setParam = (next: Record<string, string | null>) => setParams(prev => {
    const p = new URLSearchParams(prev)
    for (const [k, v] of Object.entries(next)) {
      if (v === null) p.delete(k)
      else p.set(k, v)
    }
    return p
  }, { replace: true })

  if (!Number.isFinite(partId) || part.error?.includes('not found')) {
    return <Empty icon={PackageX} title="Part not found."><Link to="/" className="mt-2 text-sm text-accent hover:underline">Back</Link></Empty>
  }

  // Home yard first, then nearest; vehicles newest arrival first.
  const results = (yards.data ?? [])
    .map(y => ({ ...y, matching_vehicles: y.matching_vehicles.filter(v => !exactOnly || v.match === 'exact') }))
    .filter(y => y.matching_vehicles.length)
    .sort((a, b) => Number(b.name === homeYard) - Number(a.name === homeYard) || a.distance_miles - b.distance_miles)
  const total = results.reduce((n, y) => n + y.matching_vehicles.length, 0)

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 px-4 py-5">
      {part.data && (
        <Link to={`/part/${partId}${carQuery}`} className="inline-flex w-fit items-center gap-1.5 text-sm text-accent hover:underline">
          <ArrowLeft className="size-4" /> {part.data.title ?? 'Part'} <span className="font-mono">{part.data.part_number}</span>
        </Link>
      )}

      <section className="rounded-xl border border-line bg-surface p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold"><MapPin className="size-5 text-muted" /> Find it in a yard</h1>
            <p className="mt-0.5 text-sm text-muted">
              Vehicles sitting in a yard that the{' '}
              {part.data ? <>{part.data.title} <span className="font-mono">{part.data.part_number}</span></> : 'part'} interchanges with
              {ic.data && <> ({ic.data.car_count} catalogue configurations)</>}.
            </p>
          </div>
          <Link to={`/part/${partId}/interchange${carQuery}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-hover">
            <ListTree className="size-4" /> Interchange
          </Link>
        </div>
        <SearchControls key={`${zip}-${radius}`} zip={zip} radius={radius} exactOnly={exactOnly}
          onSearch={(z, r) => setParam({ zip: z, radius: String(r) })}
          onExact={on => setParam({ exact: on ? '1' : null })} />
      </section>

      {yards.loading ? <Loading label="Searching yards…" />
        : yards.error ? (
          <ErrorLine message={`Yard inventory is unavailable right now (${yards.error}).`} onRetry={yards.retry} />
        ) : results.length === 0 ? (
          <Empty icon={Warehouse}
            title={exactOnly && yards.data?.length ? 'No exact matches near you — only likely ones.'
              : `None of the yards within ${radius} mi of ${zip} have one right now.`}
            hint={ic.data ? `The part fits ${ic.data.car_count} catalogue configurations; yards restock daily.` : undefined}>
            <div className="mt-3 flex gap-2">
              {exactOnly && yards.data?.length ? (
                <button onClick={() => setParam({ exact: null })} className="rounded-lg border border-line px-3 py-1.5 text-sm text-text hover:bg-hover">
                  Show likely matches
                </button>
              ) : [100, 250, 500].filter(r => r > radius).slice(0, 2).map(r => (
                <button key={r} onClick={() => setParam({ radius: String(r), zip })}
                  className="rounded-lg border border-line px-3 py-1.5 text-sm text-text hover:bg-hover">
                  Search {r} mi
                </button>
              ))}
            </div>
          </Empty>
        ) : (
          <>
            <p className="text-sm text-muted" aria-live="polite">
              {total} vehicle{total === 1 ? '' : 's'} at {results.length} yard{results.length === 1 ? '' : 's'} within {radius} mi of {zip}
            </p>
            {results.map(y => (
              <YardResults key={y.location_id} yard={y} isHome={y.name === homeYard} onHome={() => setHomeYard(y.name)} />
            ))}
          </>
        )}
    </div>
  )
}

function SearchControls({ zip, radius, exactOnly, onSearch, onExact }: {
  zip: string; radius: number; exactOnly: boolean; onSearch: (zip: string, radius: number) => void; onExact: (on: boolean) => void
}) {
  const [z, setZ] = useState(zip)
  const [r, setR] = useState(String(radius))
  const zipBad = !/^\d{5}$/.test(z)
  const rn = Number(r)
  const radiusBad = !Number.isFinite(rn) || rn < 1 || rn > 500
  return (
    <form className="mt-4 flex flex-wrap items-start gap-3" onSubmit={e => { e.preventDefault(); if (!zipBad && !radiusBad) onSearch(z, rn) }}>
      <div>
        <label htmlFor="yzip" className="section-label mb-1 block">ZIP</label>
        <input id="yzip" value={z} onChange={e => setZ(e.target.value.trim())} inputMode="numeric" maxLength={5} aria-invalid={zipBad}
          className={`w-24 rounded-lg border bg-bg px-3 py-1.5 text-sm outline-none focus:border-accent ${zipBad ? 'border-danger' : 'border-line'}`} />
        {zipBad && <p className="mt-1 text-xs text-danger">5-digit US ZIP</p>}
      </div>
      <div>
        <label htmlFor="yradius" className="section-label mb-1 block">Within (mi)</label>
        <input id="yradius" value={r} onChange={e => setR(e.target.value.trim())} inputMode="numeric" aria-invalid={radiusBad}
          className={`w-24 rounded-lg border bg-bg px-3 py-1.5 text-sm outline-none focus:border-accent ${radiusBad ? 'border-danger' : 'border-line'}`} />
        {radiusBad && <p className="mt-1 text-xs text-danger">1–500 miles</p>}
      </div>
      <div className="flex items-center gap-3 pt-5">
        <button type="submit" disabled={zipBad || radiusBad || (z === zip && rn === radius)}
          className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-hover disabled:opacity-40">Search</button>
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input type="checkbox" checked={exactOnly} onChange={e => onExact(e.target.checked)} className="size-4 accent-[var(--accent)]" />
          Exact matches only
        </label>
      </div>
    </form>
  )
}

function YardResults({ yard: y, isHome, onHome }: { yard: Yard; isHome: boolean; onHome: () => void }) {
  const vehicles = [...y.matching_vehicles].sort((a, b) => (b.arrival_date ?? '').localeCompare(a.arrival_date ?? ''))
  const exact = vehicles.filter(v => v.match === 'exact').length
  return (
    <section aria-label={y.name} className={`rounded-xl border bg-surface ${isHome ? 'border-accent' : 'border-line'}`}>
      <header className="flex flex-col gap-2 border-b border-line px-4 py-3 sm:flex-row sm:items-start sm:gap-4">
        <div className="min-w-0 flex-1">
          <h2 className="flex flex-wrap items-center gap-2 font-semibold">
            {y.name}
            {isHome
              ? <span className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs font-medium whitespace-nowrap text-white"><Star className="size-3 fill-current" /> Home yard</span>
              : <button onClick={onHome} className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-xs font-normal whitespace-nowrap text-muted hover:text-accent">
                  <Star className="size-3" /> Make home yard
                </button>}
          </h2>
          <p className="text-sm text-muted">
            {[y.address, y.city, y.state].filter(Boolean).join(', ')} · {y.distance_miles < 1 ? 'under 1' : Math.round(y.distance_miles)} mi
          </p>
        </div>
        <div className="flex items-center gap-1">
          {y.phone && (
            <a href={`tel:${y.phone.replace(/[^\d+]/g, '')}`} className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm hover:bg-hover">
              <Phone className="size-4 text-muted" /> {y.phone}
            </a>
          )}
          <a href={mapsUrl(y)} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-sm hover:bg-hover">
            <Navigation className="size-4" /> Map
          </a>
        </div>
      </header>
      <p className="px-4 pt-2 text-xs text-muted">
        {vehicles.length} vehicle{vehicles.length === 1 ? '' : 's'} · {exact} exact, {vehicles.length - exact} likely
      </p>
      {/* Phones: one card per vehicle; wider screens: a table. */}
      <ul className="divide-y divide-line sm:hidden">
        {vehicles.map(v => (
          <li key={v.vehicle_id} className="flex items-start gap-3 px-4 py-2.5">
            <div className="w-12 shrink-0 text-center">
              <p className="section-label">Row</p>
              <p className="text-lg font-semibold">{v.row ?? '—'}</p>
            </div>
            <div className="min-w-0 flex-1 text-sm">
              <p><span className="font-medium">{[v.year, v.make, v.model].filter(Boolean).join(' ')}</span>
                {v.trim && <span className="text-muted"> {v.trim}</span>}</p>
              <p className="text-xs text-muted">
                {[v.color?.toLowerCase(), relativeDay(v.arrival_date) && `arrived ${relativeDay(v.arrival_date)}`].filter(Boolean).join(' · ')}
              </p>
              {v.vin && <p className="truncate font-mono text-xs text-muted">{v.vin}</p>}
            </div>
            <MatchPill v={v} />
          </li>
        ))}
      </ul>
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left">
              {['Vehicle', 'Row', 'Colour', 'Arrived', 'VIN', 'Match'].map(h => (
                <th key={h} className="section-label px-4 py-2 font-semibold">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {vehicles.map(v => <VehicleRow key={v.vehicle_id} v={v} />)}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function VehicleRow({ v }: { v: YardVehicle }) {
  return (
    <tr className="border-t border-line">
      <td className="px-4 py-2">
        <span className="font-medium">{[v.year, v.make, v.model].filter(Boolean).join(' ')}</span>
        {v.trim && <span className="text-muted"> {v.trim}</span>}
      </td>
      <td className="px-4 py-2 text-base font-semibold">{v.row ?? <span className="text-sm font-normal text-muted">—</span>}</td>
      <td className="px-4 py-2">{v.color ? v.color.toLowerCase() : <span className="text-muted">—</span>}</td>
      <td className="px-4 py-2 whitespace-nowrap" title={v.arrival_date ?? undefined}>{relativeDay(v.arrival_date) ?? <span className="text-muted">—</span>}</td>
      <td className="px-4 py-2 font-mono text-xs text-muted">{v.vin ?? '—'}</td>
      <td className="px-4 py-2"><MatchPill v={v} /></td>
    </tr>
  )
}

function MatchPill({ v }: { v: YardVehicle }) {
  return v.match === 'exact'
    ? <span className="rounded-full bg-ok-soft px-2 py-0.5 text-xs text-ok" title="The VIN decodes to a configuration the part fits">exact</span>
    : <span className="rounded-full border border-line px-2 py-0.5 text-xs text-muted"
        title="The VIN narrows to several trims/engines; at least one uses this part">likely</span>
}
