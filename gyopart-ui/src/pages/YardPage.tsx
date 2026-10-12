import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { ArrowLeft, Check, ChevronDown, Loader2, Navigation, Phone, Plus, Star, Warehouse } from 'lucide-react'
import { api, errorMessage } from '../api'
import { Combobox } from '../components/Combobox'
import { Empty, ErrorLine, Loading } from '../components/States'
import { cleanTrim, mapsUrl, relativeDay } from '../lib/format'
import { useAsync } from '../lib/useAsync'
import { useGarage } from '../state/garageContext'
import type { CarDetail, YardInventoryVehicle } from '../types'

/** Workflow 7, part 2: a yard's inventory, newest arrivals first, filterable; vehicles link to their catalogue. */
export function YardPage() {
  const yardId = Number(useParams().yardId)
  const [params, setParams] = useSearchParams()
  const make = params.get('make')
  const model = params.get('model')
  const year = params.get('year') ? Number(params.get('year')) : null
  const { homeYard, setHomeYard } = useGarage()

  const yard = useAsync(() => api.yard(yardId), [yardId], Number.isFinite(yardId))
  const facets = useAsync(() => api.yardFacets(yardId), [yardId], Number.isFinite(yardId))
  const first = useAsync(() => api.yardVehicles(yardId, { make, model, year }), [yardId, make, model, year], Number.isFinite(yardId))
  const filterKey = JSON.stringify([yardId, make, model, year])
  const [more, setMore] = useState<{ key: string; vehicles: YardInventoryVehicle[] }>({ key: '', vehicles: [] })
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState<string | null>(null)

  const setFilter = (next: Record<string, string | null>) => setParams(prev => {
    const p = new URLSearchParams(prev)
    for (const [k, v] of Object.entries(next)) {
      if (v === null || v === '') p.delete(k)
      else p.set(k, v)
    }
    return p
  }, { replace: true })

  if (!Number.isFinite(yardId) || yard.error?.includes('not found')) {
    return <Empty icon={Warehouse} title="Yard not found."><Link to="/yards" className="mt-2 text-sm text-accent hover:underline">All yards</Link></Empty>
  }
  if (yard.loading) return <Loading />
  if (yard.error) return <ErrorLine message={`Yard inventory is unavailable right now (${yard.error}).`} onRetry={yard.retry} />
  const y = yard.data!
  const isHome = y.name === homeYard

  const extra = more.key === filterKey ? more.vehicles : []
  const vehicles = [...(first.data?.vehicles ?? []), ...extra]
  const total = first.data?.total ?? 0
  const loadMore = async () => {
    setLoadingMore(true)
    setMoreError(null)
    try {
      const page = await api.yardVehicles(yardId, { make, model, year, offset: vehicles.length })
      setMore({ key: filterKey, vehicles: [...extra, ...page.vehicles] })
    } catch (e) {
      setMoreError(errorMessage(e))
    } finally {
      setLoadingMore(false)
    }
  }

  // Facets → combobox options (ids are positions; the URL keeps the names).
  const makes = (facets.data?.makes ?? []).map((m, i) => ({ id: i, name: m.make, label: `${m.make} (${m.count})` }))
  const makeFacet = facets.data?.makes.find(m => m.make === make)
  const models = (makeFacet?.models ?? []).map((m, i) => ({ id: i, name: m.model, label: `${m.model} (${m.count})` }))
  const years: { id: number; name: string }[] = []
  if (facets.data?.year_min && facets.data.year_max) {
    for (let yr = facets.data.year_max; yr >= facets.data.year_min; yr--) years.push({ id: yr, name: String(yr) })
  }
  const filtered = !!(make || model || year)

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 px-4 py-5">
      <Link to="/yards" className="inline-flex w-fit items-center gap-1.5 text-sm text-accent hover:underline">
        <ArrowLeft className="size-4" /> All yards
      </Link>

      <section className={`rounded-xl border bg-surface p-4 sm:p-5 ${isHome ? 'border-accent' : 'border-line'}`}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1">
            <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold">
              {y.name}
              {isHome
                ? <span className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs font-medium whitespace-nowrap text-white"><Star className="size-3 fill-current" /> Home yard</span>
                : <button onClick={() => setHomeYard(y.name)} className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-xs font-normal whitespace-nowrap text-muted hover:text-accent">
                    <Star className="size-3" /> Make home yard
                  </button>}
            </h1>
            <p className="text-sm text-muted">{[y.address, y.city, y.state, y.zip_code].filter(Boolean).join(', ')}</p>
            <p className="mt-1 text-sm">
              {y.vehicle_count.toLocaleString()} vehicles
              {y.new_this_week > 0 && <span className="text-ok"> · +{y.new_this_week} this week</span>}
              <span className="text-muted"> · {y.catalogued_count.toLocaleString()} matched to the catalogue</span>
              {y.last_seen_at && <span className="text-muted"> · checked {relativeDay(y.last_seen_at)}</span>}
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
        </div>
      </section>

      {y.vehicle_count === 0 ? (
        <Empty icon={Warehouse} title="No vehicles on record for this yard."
          hint={y.last_seen_at ? `Last checked ${relativeDay(y.last_seen_at)}.` : 'It has not been scraped yet.'} />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-[1fr_1fr_10rem_auto] sm:items-end">
            <Combobox label="Make" options={makes.map(m => ({ id: m.id, name: m.label }))}
              value={makes.find(m => m.name === make)?.id ?? null}
              onChange={id => setFilter({ make: id === null ? null : makes[id].name, model: null })}
              loading={facets.loading} error={facets.error} onRetry={facets.retry} placeholder="Any make" />
            <Combobox label="Model" options={models.map(m => ({ id: m.id, name: m.label }))}
              value={models.find(m => m.name === model)?.id ?? null}
              onChange={id => setFilter({ model: id === null ? null : models[id].name })}
              disabled={!make} placeholder={make ? 'Any model' : 'Pick a make first'} />
            <Combobox label="Year" options={years} value={year} onChange={id => setFilter({ year: id === null ? null : String(id) })}
              loading={facets.loading} placeholder="Any year" />
            {filtered && (
              <button onClick={() => setFilter({ make: null, model: null, year: null })}
                className="rounded-lg px-3 py-2 text-sm text-accent hover:bg-hover">Clear filters</button>
            )}
          </div>

          {first.loading ? <Loading label="Loading inventory…" />
            : first.error ? <ErrorLine message={`Couldn't load the inventory (${first.error}).`} onRetry={first.retry} />
              : vehicles.length === 0 ? (
                <Empty icon={Warehouse} title="No vehicles match these filters.">
                  <button onClick={() => setFilter({ make: null, model: null, year: null })}
                    className="mt-2 text-sm text-accent hover:underline">Clear filters</button>
                </Empty>
              ) : (
                <section aria-label="Inventory" className="rounded-xl border border-line bg-surface">
                  <p className="border-b border-line px-4 py-2 text-xs text-muted" aria-live="polite">
                    {total.toLocaleString()} vehicle{total === 1 ? '' : 's'}{filtered ? ' matching' : ''} · newest arrivals first
                  </p>
                  <ul className="divide-y divide-line">
                    {vehicles.map(v => <InventoryRow key={v.vehicle_id} v={v} />)}
                  </ul>
                  {vehicles.length < total && (
                    <div className="flex flex-col items-center gap-1 border-t border-line p-3">
                      <button onClick={loadMore} disabled={loadingMore}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-hover disabled:opacity-50">
                        {loadingMore && <Loader2 className="size-4 animate-spin" />} Show more ({(total - vehicles.length).toLocaleString()} left)
                      </button>
                      {moreError && <p className="text-xs text-danger">{moreError}</p>}
                    </div>
                  )}
                </section>
              )}
        </>
      )}
    </div>
  )
}

function InventoryRow({ v }: { v: YardInventoryVehicle }) {
  const arrived = relativeDay(v.arrival_date)
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
      <div className="w-12 shrink-0 text-center">
        <p className="section-label">Row</p>
        <p className="text-lg font-semibold">{v.row ?? '—'}</p>
      </div>
      <div className="min-w-0 flex-1 text-sm">
        <p><span className="font-medium">{[v.year, v.make, v.model].filter(Boolean).join(' ')}</span>
          {v.trim && <span className="text-muted"> {v.trim}</span>}</p>
        <p className="text-xs text-muted">{[v.color?.toLowerCase(), arrived && `arrived ${arrived}`].filter(Boolean).join(' · ')}</p>
        {v.vin && <p className="font-mono text-xs text-muted">{v.vin}</p>}
      </div>
      <div className="flex w-full justify-end sm:w-auto"><CatalogueActions v={v} /></div>
    </li>
  )
}

/** Exact match: Parts + Add to garage. Likely: the same, after choosing which configuration it is. */
function CatalogueActions({ v }: { v: YardInventoryVehicle }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  if (!v.candidates.length) {
    return <span className="text-xs text-muted" title="The VIN didn't match a car in the parts catalogue (often a model year not scraped yet)">Not in catalogue yet</span>
  }
  if (v.candidates.length === 1) {
    const c = v.candidates[0]
    return (
      <div className="flex items-center gap-1.5">
        <span className="rounded-full bg-ok-soft px-2 py-0.5 text-xs text-ok" title={configLabel(c)}>exact</span>
        <Link to={`/car/${c.car_id}`} className="rounded-lg border border-line px-2.5 py-1 text-sm hover:bg-hover">Parts</Link>
        <AddToGarage car={c} />
      </div>
    )
  }
  return (
    <div ref={ref} className="relative flex items-center gap-1.5">
      <span className="rounded-full border border-line px-2 py-0.5 text-xs text-muted" title="The VIN fits several catalogue configurations">likely</span>
      <button onClick={() => setOpen(o => !o)} aria-expanded={open} aria-haspopup="menu"
        className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-sm hover:bg-hover">
        Parts <ChevronDown className="size-3.5" />
      </button>
      {open && (
        <div role="menu" className="absolute top-full right-0 z-30 mt-1 w-72 rounded-lg border border-line bg-surface py-1 shadow-lg">
          <p className="section-label px-3 pt-1 pb-1">Which one is it? ({v.candidates.length})</p>
          {v.candidates.map(c => (
            <div key={c.car_id} className="flex items-center gap-2 px-3 py-1.5 hover:bg-hover">
              <Link role="menuitem" to={`/car/${c.car_id}`} className="min-w-0 flex-1 truncate text-sm">{configLabel(c)}</Link>
              <AddToGarage car={c} compact />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const configLabel = (c: CarDetail) => [cleanTrim(c.trim) ?? 'Base', c.engine].filter(Boolean).join(' · ')

function AddToGarage({ car, compact }: { car: CarDetail; compact?: boolean }) {
  const { vehicles, add } = useGarage()
  const has = vehicles.some(g => g.car_id === car.car_id)
  if (has) {
    return <span className="inline-flex items-center gap-1 text-xs text-ok"><Check className="size-3.5" />{compact ? '' : ' In garage'}</span>
  }
  return (
    <button onClick={() => add({ ...car, vin: null, decoded: null, added_at: new Date().toISOString() })}
      aria-label={`Add ${car.year} ${car.make} ${car.model} ${configLabel(car)} to garage`} title="Add to garage"
      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-accent hover:bg-hover">
      <Plus className="size-3.5" />{compact ? '' : ' Garage'}
    </button>
  )
}
