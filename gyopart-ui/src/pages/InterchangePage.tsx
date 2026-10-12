import { useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { ArrowLeft, Car, ChevronRight, ListTree, MapPin, PackageX } from 'lucide-react'
import { api } from '../api'
import { Empty, ErrorLine, Loading } from '../components/States'
import { useAsync } from '../lib/useAsync'
import { useGarage, vehicleTitle } from '../state/garageContext'
import type { InterchangeModel } from '../types'

const num = (v: string | null) => (v && /^\d+$/.test(v) ? Number(v) : null)

/** Workflow 4: every vehicle the part fits, make → model (year ranges) → year → trim/engine. */
export function InterchangePage() {
  const partId = Number(useParams().partId)
  const [params, setParams] = useSearchParams()
  const carId = num(params.get('car'))
  const makeFilter = params.get('make')
  const { vehicles } = useGarage()
  const part = useAsync(() => api.part(partId), [partId], Number.isFinite(partId))
  const ic = useAsync(() => api.interchange(partId), [partId], Number.isFinite(partId))
  const [open, setOpen] = useState<Set<string>>(new Set())

  // Garage cars (and the car the user came from) that this part fits, to mark them in the chart.
  const garageIds = useMemo(() => new Set(vehicles.map(v => v.car_id)), [vehicles])
  const fitsMine = useMemo(() => {
    const ids = new Set(ic.data?.makes.flatMap(m => m.models.flatMap(mo => mo.years.flatMap(y => y.cars.map(c => c.car_id)))))
    return vehicles.filter(v => ids.has(v.car_id))
  }, [ic.data, vehicles])

  if (!Number.isFinite(partId) || part.error?.includes('not found') || ic.error?.includes('not found')) {
    return <Empty icon={PackageX} title="Part not found."><Link to="/" className="mt-2 text-sm text-accent hover:underline">Back</Link></Empty>
  }
  if (ic.loading || part.loading) return <Loading />
  if (ic.error || part.error) {
    return <ErrorLine message={(ic.error ?? part.error)!} onRetry={() => { ic.retry(); part.retry() }} />
  }
  const data = ic.data!
  const p = part.data!
  const carQuery = carId ? `?car=${carId}` : ''
  const makes = makeFilter ? data.makes.filter(m => m.make === makeFilter) : data.makes
  const modelCount = data.makes.reduce((n, m) => n + m.models.length, 0)
  const key = (make: string, m: InterchangeModel) => `${make}|${m.model}`
  const allKeys = makes.flatMap(mk => mk.models.map(m => key(mk.make, m)))
  const toggle = (k: string) => setOpen(s => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n })
  const carLink = (id: number) => `/car/${id}?q=${encodeURIComponent(p.part_number ?? p.title ?? '')}`

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 px-4 py-5">
      <Link to={`/part/${partId}${carQuery}`} className="inline-flex w-fit items-center gap-1.5 text-sm text-accent hover:underline">
        <ArrowLeft className="size-4" /> {p.title ?? 'Part'} <span className="font-mono">{p.part_number}</span>
      </Link>

      <section className="rounded-xl border border-line bg-surface p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold"><ListTree className="size-5 text-muted" /> Interchange</h1>
            <p className="mt-0.5 text-sm text-muted">
              {p.title} <span className="font-mono">{p.part_number}</span> fits {data.car_count} vehicle{data.car_count === 1 ? '' : 's'}
              {data.car_count > 0 && <> across {data.makes.length} make{data.makes.length === 1 ? '' : 's'} and {modelCount} model{modelCount === 1 ? '' : 's'}</>}.
              {' '}Any of them is a donor.
            </p>
          </div>
          {data.car_count > 0 && (
            <Link to={`/part/${partId}/yards${carQuery}`}
              className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">
              <MapPin className="size-4" /> Find in yards
            </Link>
          )}
        </div>
        {fitsMine.length > 0 && (
          <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg bg-ok-soft px-3 py-2 text-sm">
            <Car className="size-4 text-ok" /> Fits your {fitsMine.map(v => `${vehicleTitle(v)} ${v.trim ?? ''}`.trim()).join(', ')}
          </p>
        )}
      </section>

      {data.car_count === 0 ? (
        <Empty icon={ListTree} title="This part isn't listed for any vehicle in the catalogue."
          hint="It may be sold as a standalone part or only listed on a site we haven't scraped." />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by make">
            <Chip on={!makeFilter} onClick={() => setParams(p => { p.delete('make'); return p }, { replace: true })}>
              All · {data.car_count}
            </Chip>
            {data.makes.map(m => (
              <Chip key={m.make} on={makeFilter === m.make}
                onClick={() => setParams(p => { p.set('make', m.make); return p }, { replace: true })}>
                {m.make} · {m.car_count}
              </Chip>
            ))}
            <span className="flex-1" />
            <button onClick={() => setOpen(allKeys.every(k => open.has(k)) ? new Set() : new Set(allKeys))}
              className="rounded-lg px-2.5 py-1 text-sm text-accent hover:bg-hover">
              {allKeys.every(k => open.has(k)) ? 'Collapse all' : 'Expand all'}
            </button>
          </div>

          {makes.map(mk => (
            <section key={mk.make} aria-label={mk.make} className="rounded-xl border border-line bg-surface">
              <h2 className="flex items-baseline justify-between border-b border-line px-4 py-2.5">
                <span className="font-semibold">{mk.make}</span>
                <span className="text-xs text-muted">{mk.car_count} vehicle{mk.car_count === 1 ? '' : 's'}</span>
              </h2>
              <ul className="divide-y divide-line">
                {mk.models.map(m => {
                  const k = key(mk.make, m)
                  const isOpen = open.has(k)
                  const mine = m.years.some(y => y.cars.some(c => garageIds.has(c.car_id)))
                  return (
                    <li key={k}>
                      <button onClick={() => toggle(k)} aria-expanded={isOpen}
                        className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-hover">
                        <ChevronRight className={`size-4 shrink-0 text-muted transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                        <span className="min-w-0 flex-1">
                          <span className="font-medium">{m.model}</span>
                          {mine && <span className="ml-2 rounded-full border border-ok px-2 py-0.5 text-xs whitespace-nowrap text-ok">your vehicle</span>}
                        </span>
                        <span className="text-sm">{m.year_ranges}</span>
                        <span className="w-20 text-right text-xs text-muted">{m.car_count} config{m.car_count === 1 ? '' : 's'}</span>
                      </button>
                      {isOpen && (
                        <table className="mb-2 ml-11 w-[calc(100%-3.5rem)] text-sm">
                          <tbody>
                            {m.years.map(y => (
                              <tr key={y.year} className="align-top">
                                <th scope="row" className="w-14 py-1 pr-3 text-left font-normal text-muted">{y.year}</th>
                                <td className="py-1">
                                  <div className="flex flex-wrap gap-1.5">
                                    {y.cars.map(c => {
                                      const isMine = garageIds.has(c.car_id)
                                      return (
                                        <Link key={c.car_id} to={carLink(c.car_id)}
                                          title={`Open the ${y.year} ${mk.make} ${m.model} catalogue at this part`}
                                          className={`rounded-full border px-2.5 py-0.5 text-xs hover:border-accent hover:text-accent ${
                                            isMine ? 'border-ok bg-ok-soft text-text' : 'border-line'}`}>
                                          {[c.trim, c.engine].filter(Boolean).join(' · ') || 'Base'}
                                        </Link>
                                      )
                                    })}
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </li>
                  )
                })}
              </ul>
            </section>
          ))}
        </>
      )}
    </div>
  )
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} aria-pressed={on}
      className={`rounded-full border px-3 py-1 text-sm ${on ? 'border-accent bg-accent text-white' : 'border-line hover:bg-hover'}`}>
      {children}
    </button>
  )
}
