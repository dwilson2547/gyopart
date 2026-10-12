import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { ArrowLeft, Check, CheckCircle2, Copy, Images, ListTree, MapPin, PackageX, XCircle } from 'lucide-react'
import { api } from '../api'
import { Lightbox } from '../components/Lightbox'
import { Empty, ErrorLine, Loading } from '../components/States'
import { ZoomImage } from '../components/ZoomImage'
import { useAsync } from '../lib/useAsync'
import { useCarParam } from '../lib/useCarParam'
import { vehicleTitle } from '../state/garageContext'
import type { CarDetail, PartDetail } from '../types'

const num = (v: string | null) => (v && /^\d+$/.test(v) ? Number(v) : null)

/** Workflow 3: confirm the part before going on to the interchange or the yards. */
export function PartPage() {
  const partId = Number(useParams().partId)
  const [params] = useSearchParams()
  const carId = num(params.get('car'))
  const diagramParam = num(params.get('diagram'))
  const car = useCarParam(carId)
  const detail = useAsync(() => api.partDetail(partId, carId), [partId, carId], Number.isFinite(partId))

  if (!Number.isFinite(partId) || detail.error?.includes('not found')) {
    return (
      <Empty icon={PackageX} title="Part not found.">
        <Link to="/" className="mt-2 text-sm text-accent hover:underline">Back to your vehicle</Link>
      </Empty>
    )
  }
  if (detail.loading) return <Loading />
  if (detail.error) return <ErrorLine message={detail.error} onRetry={detail.retry} />
  const p = detail.data!
  const carQuery = carId ? `?car=${carId}` : ''
  const diagram = p.diagrams.find(d => d.diagram_id === diagramParam) ?? p.diagrams[0] ?? null
  const back = carId && diagram?.sub_category_id
    ? `/car/${carId}?sub=${diagram.sub_category_id}&diagram=${diagram.diagram_id}&part=${p.id}`
    : carId ? `/car/${carId}` : null

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-5">
      {back && (
        <Link to={back} className="inline-flex w-fit items-center gap-1.5 text-sm text-accent hover:underline">
          <ArrowLeft className="size-4" /> Change part
        </Link>
      )}

      <Header p={p} car={car} carQuery={carQuery} />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <DiagramSection p={p} selectedId={diagram?.diagram_id ?? null} carId={carId} />
        <Details p={p} />
      </div>

      <Pictures p={p} />
    </div>
  )
}

function Header({ p, car, carQuery }: { p: PartDetail; car: CarDetail | null; carQuery: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    if (!p.part_number) return
    try {
      await navigator.clipboard.writeText(p.part_number)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard blocked: the number is selectable text anyway */ }
  }

  return (
    <section className="rounded-xl border border-line bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1">
          <p className="section-label">{p.manufacturer ?? 'OEM'} part</p>
          <h1 className="text-2xl font-semibold">{p.title ?? 'Untitled part'}</h1>
          {p.part_number && (
            <div className="mt-1 flex items-center gap-2">
              <span className="font-mono text-lg tracking-wide select-all">{p.part_number}</span>
              <button onClick={copy} aria-label="Copy part number" title="Copy part number"
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-muted hover:bg-hover">
                {copied ? <><Check className="size-3.5 text-ok" /> Copied</> : <Copy className="size-3.5" />}
              </button>
            </div>
          )}
          {p.other_names.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Also called">
              {p.other_names.map(n => (
                <span key={n} className="rounded-full border border-line px-2.5 py-0.5 text-xs text-muted">{n}</span>
              ))}
            </div>
          )}
        </div>
        {p.msrp != null && (
          <div className="text-right">
            <p className="section-label">MSRP new</p>
            <p className="text-lg">${p.msrp.toFixed(2)}</p>
          </div>
        )}
      </div>

      {car && p.fits_car !== null && (
        <p className={`mt-4 flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${p.fits_car ? 'bg-ok-soft' : 'bg-danger-soft'}`}>
          {p.fits_car
            ? <><CheckCircle2 className="size-4 text-ok" /> Fits your {vehicleTitle(car)} {car.trim}</>
            : <><XCircle className="size-4 text-danger" /> Not listed for your {vehicleTitle(car)} {car.trim} — check the interchange.</>}
        </p>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <Link to={`/part/${p.id}/interchange${carQuery}`}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">
          <ListTree className="size-4" /> See interchange
          <span className="opacity-80">· {p.fit_count} vehicle{p.fit_count === 1 ? '' : 's'}</span>
        </Link>
        <Link to={`/part/${p.id}/yards${carQuery}`}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">
          <MapPin className="size-4" /> Find in yards
        </Link>
      </div>
    </section>
  )
}

function DiagramSection({ p, selectedId, carId }: { p: PartDetail; selectedId: number | null; carId: number | null }) {
  const [chosen, setChosen] = useState<number | null>(null)
  const current = p.diagrams.find(d => d.diagram_id === (chosen ?? selectedId)) ?? null
  // No catalogue diagram: the parts site's own illustration of the part, which also names its callout.
  const illustration = !current ? p.illustrations[0] ?? null : null
  const callout = current?.part_index ?? illustration?.callout ?? null

  if (!current && !illustration) {
    return (
      <section className="rounded-xl border border-line bg-surface">
        <Empty icon={Images} title="No diagram for this part." hint="Its pictures are below, if it has any." />
      </section>
    )
  }
  return (
    <section aria-label="Diagram" className="min-w-0">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h2 className="font-medium">{current?.label ?? 'Illustration'}</h2>
        {callout && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-accent px-2.5 py-0.5 text-xs font-semibold text-white">
            Callout {callout}
          </span>
        )}
        {callout && <span className="text-xs text-muted">— look for number {callout} on the drawing</span>}
      </div>
      <ZoomImage key={current?.diagram_id ?? illustration?.large} src={current?.image_url ?? illustration!.large}
        alt={current?.label ?? 'illustration'} />
      {p.diagrams.length > 1 && (
        <div className="mt-2">
          <p className="section-label mb-1">{carId ? 'On these diagrams' : 'Also on'}</p>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {p.diagrams.map(d => (
              <button key={d.diagram_id} onClick={() => setChosen(d.diagram_id)}
                aria-pressed={d.diagram_id === current?.diagram_id}
                className={`w-28 shrink-0 overflow-hidden rounded-lg border bg-white ${
                  d.diagram_id === current?.diagram_id ? 'border-accent ring-1 ring-accent' : 'border-line hover:border-accent'}`}>
                {d.image_url && <img src={d.image_url} alt={d.label ?? 'diagram'} loading="lazy" className="aspect-[4/3] w-full object-contain p-1" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function Details({ p }: { p: PartDetail }) {
  const rows: [string, string | null][] = [
    ['Description', p.description], ['Position', p.positions], ['Notes', p.notes], ['Replaces', p.replaces],
  ]
  const shown = rows.filter(([, v]) => v)
  return (
    <section aria-label="Details" className="h-fit rounded-xl border border-line bg-surface">
      <p className="section-label border-b border-line px-4 py-2">Details</p>
      {shown.length ? (
        <dl className="divide-y divide-line">
          {shown.map(([k, v]) => (
            <div key={k} className="px-4 py-2.5">
              <dt className="text-xs text-muted">{k}</dt>
              <dd className="text-sm">{v}</dd>
            </div>
          ))}
        </dl>
      ) : <p className="px-4 py-4 text-sm text-muted">No description from the parts site.</p>}
    </section>
  )
}

function Pictures({ p }: { p: PartDetail }) {
  const [open, setOpen] = useState<number | null>(null)
  return (
    <section aria-label="Pictures">
      <h2 className="mb-2 font-medium">Pictures</h2>
      {p.photos.length === 0 ? (
        <p className="text-sm text-muted">No pictures for this part.</p>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-2">
          {p.photos.map((ph, i) => (
            <button key={ph.large} onClick={() => setOpen(i)} aria-label={`Open picture ${i + 1}`}
              className="overflow-hidden rounded-lg border border-line bg-white hover:border-accent">
              <img src={ph.medium} alt={`${p.title ?? 'part'} ${i + 1}`} loading="lazy" className="aspect-square w-full object-contain p-2" />
            </button>
          ))}
        </div>
      )}
      {open !== null && (
        <Lightbox images={p.photos.map(ph => ph.large)} index={open} onIndex={setOpen} onClose={() => setOpen(null)}
          label={p.title ?? 'Part picture'} />
      )}
    </section>
  )
}
