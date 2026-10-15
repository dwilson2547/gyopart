import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import { ChevronDown, ChevronLeft, ChevronRight, FolderTree, ImageOff, LayoutGrid, PackageSearch, X } from 'lucide-react'
import { api } from '../api'
import { CatalogueTree } from '../components/CatalogueTree'
import { Empty, ErrorLine, Loading } from '../components/States'
import { ZoomImage } from '../components/ZoomImage'
import { useAsync } from '../lib/useAsync'
import { useMediaQuery } from '../lib/useMediaQuery'
import { useGarage, vehicleSubtitle, vehicleTitle } from '../state/garageContext'
import { useVehiclePicker } from '../state/vehiclePickerContext'
import type { CarDiagram, DiagramPart, PartHit, TreeCategory } from '../types'

const num = (v: string | null) => (v && /^\d+$/.test(v) ? Number(v) : null)

/** Workflow 2: browse a car's catalogue — tree on the left (always visible), diagrams on the right. */
export function CarPage() {
  // Keyed by car, so switching cars starts clean (filter text, open categories) without a reload.
  const { carId } = useParams()
  return <CarCatalogue key={carId} />
}

function CarCatalogue() {
  const carId = Number(useParams().carId)
  const picker = useVehiclePicker()
  const [params, setParams] = useSearchParams()
  const subId = num(params.get('sub'))
  const diagramId = num(params.get('diagram'))
  const partId = num(params.get('part'))
  const query = params.get('q') ?? ''
  const [drawer, setDrawer] = useState(false)
  // Tailwind's lg breakpoint. Only one tree may be mounted: each syncs its filter text into ?q=, so a
  // hidden second copy would keep writing its stale text back (the mobile search loop).
  const wide = useMediaQuery('(min-width: 1024px)')

  const { vehicles } = useGarage()
  const inGarage = vehicles.find(v => v.car_id === carId) ?? null
  const fetched = useAsync(() => api.car(carId), [carId], !inGarage)
  const car = inGarage ?? fetched.data
  const tree = useAsync(() => api.tree(carId), [carId])

  const set = useCallback((next: Record<string, string | number | null>, replace = false) => {
    setParams(p => {
      const n = new URLSearchParams(p)
      for (const [k, v] of Object.entries(next)) {
        if (v === null || v === '') n.delete(k)
        else n.set(k, String(v))
      }
      return n
    }, { replace })
  }, [setParams])

  const onQuery = useCallback((q: string) => set({ q }, true), [set])
  const onSub = (id: number) => { set({ sub: id, diagram: null, part: null }); setDrawer(false) }
  const onHit = (h: PartHit) => {
    setDrawer(false)
    if (h.diagram_id) set({ sub: h.sub_category_id, diagram: h.diagram_id, part: h.part_id })
    else navigateToPart(h.part_id)
  }
  const navigate = useNavigate()
  const navigateToPart = (id: number, diagram?: number) =>
    navigate(`/part/${id}?car=${carId}${diagram ? `&diagram=${diagram}` : ''}`)

  if (!Number.isFinite(carId)) return <Empty icon={PackageSearch} title="Not a vehicle." />
  if (fetched.error) return <ErrorLine message={`Couldn't load this vehicle: ${fetched.error}`} onRetry={fetched.retry} />

  const crumbs = tree.data ? findCrumbs(tree.data, subId) : null
  const treePanel = tree.loading ? <Loading /> : tree.error ? <ErrorLine message={tree.error} onRetry={tree.retry} />
    : tree.data && (
      <CatalogueTree carId={carId} tree={tree.data} subId={subId} partId={partId} query={query}
        onQuery={onQuery} onSub={onSub} onHit={onHit} />
    )

  return (
    <div className="flex h-full">
      {/* Tree: a fixed column on wide screens, a drawer on narrow ones. */}
      {wide && (
        <aside className="w-80 shrink-0 border-r border-line bg-surface" aria-label="Catalogue">
          {treePanel}
        </aside>
      )}
      {drawer && !wide && (
        <div className="fixed inset-0 z-40">
          <div className="absolute inset-0 bg-black/50" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-full max-w-sm flex-col bg-surface shadow-xl" aria-label="Catalogue">
            <div className="flex items-center justify-between border-b border-line py-1 pr-2 pl-4 font-semibold">
              Categories
              <button onClick={() => setDrawer(false)} aria-label="Close categories" className="rounded-full p-2 hover:bg-hover">
                <X className="size-5" />
              </button>
            </div>
            <div className="min-h-0 flex-1">{treePanel}</div>
          </aside>
        </div>
      )}

      <section className="min-w-0 flex-1 overflow-auto">
        <div className="sticky top-0 z-10 flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-bg/95 px-4 py-2.5 backdrop-blur">
          <button onClick={() => setDrawer(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-sm hover:bg-hover lg:hidden">
            <FolderTree className="size-4" /> Categories
          </button>
          <button onClick={picker.open} aria-label="Change vehicle" title="Change vehicle"
            className="-mx-2 flex min-w-0 items-center gap-1.5 rounded-lg px-2 py-0.5 text-left hover:bg-hover">
            <span className="min-w-0">
              <h1 className="truncate font-semibold">{car ? vehicleTitle(car) : 'Vehicle'}</h1>
              {car && <p className="truncate text-xs text-muted">{vehicleSubtitle(car)}</p>}
            </span>
            <ChevronDown className="size-4 shrink-0 text-muted" />
          </button>
          {crumbs && (
            <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1 text-sm text-muted sm:ml-auto">
              <span className="truncate">{crumbs.cat.label}</span>
              <ChevronRight className="size-3.5 shrink-0" />
              {diagramId ? (
                <button onClick={() => set({ diagram: null, part: null })} className="truncate text-accent hover:underline">
                  {crumbs.sub.label}
                </button>
              ) : <span className="truncate text-text">{crumbs.sub.label}</span>}
            </nav>
          )}
        </div>

        <div className="p-4">
          {tree.data && tree.data.length === 0 ? (
            <Empty icon={ImageOff} title="No diagrams for this vehicle yet."
              hint="The catalogue is still being scraped for some makes and years — check back later." />
          ) : !subId ? (
            <>
              <Blurb />
              <Empty icon={FolderTree} title="Pick a category"
                hint={<>Browse the categories{' '}<span className="lg:hidden">(the Categories button)</span>
                  <span className="hidden lg:inline">on the left</span>, or filter by part name or number.</>} />
            </>
          ) : diagramId ? (
            <DiagramView carId={carId} subId={subId} diagramId={diagramId} partId={partId}
              onDiagram={id => set({ diagram: id, part: null })} onPart={id => navigateToPart(id, diagramId)} />
          ) : (
            <DiagramGrid carId={carId} subId={subId} onPick={id => set({ diagram: id })}
              onOnly={id => set({ diagram: id }, true)} />
          )}
        </div>
      </section>
    </div>
  )
}

/** What the name stands for, with the letters that spell it picked out. */
function Blurb() {
  const a = (t: string) => <span className="text-[#9db0cd]">{t}</span>
  return (
    <div className="mx-auto mt-6 max-w-md text-center">
      <p className="text-2xl font-semibold tracking-tight">{a('G')}et {a('Y')}our {a('O')}wn {a('Part')}</p>
      <p className="mt-1 text-sm text-muted">Part compatibility search and recycled auto parts inventory lookup</p>
    </div>
  )
}

function findCrumbs(tree: TreeCategory[], subId: number | null) {
  for (const cat of tree) {
    const sub = cat.subcategories.find(s => s.id === subId)
    if (sub) return { cat, sub }
  }
  return null
}

function DiagramGrid({ carId, subId, onPick, onOnly }: {
  carId: number; subId: number; onPick: (id: number) => void; onOnly: (id: number) => void
}) {
  const diagrams = useAsync(() => api.carDiagrams(carId, subId), [carId, subId])
  // One diagram: nothing to choose, open it.
  useEffect(() => {
    if (diagrams.data?.length === 1) onOnly(diagrams.data[0].id)
  }, [diagrams.data, onOnly])

  if (diagrams.loading) return <Loading />
  if (diagrams.error) return <ErrorLine message={diagrams.error} onRetry={diagrams.retry} />
  if (!diagrams.data?.length) return <Empty icon={LayoutGrid} title="No diagrams in this subcategory for this vehicle." />
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3">
      {diagrams.data.map((d, i) => (
        <button key={d.id} onClick={() => onPick(d.id)}
          className="group overflow-hidden rounded-xl border border-line bg-surface text-left hover:border-accent">
          <Thumb d={d} />
          <div className="flex items-baseline justify-between gap-2 px-3 py-2">
            <span className="truncate text-sm font-medium">{d.label ?? `Diagram ${i + 1}`}</span>
            <span className="shrink-0 text-xs text-muted">
              {d.fitting_part_count} part{d.fitting_part_count === 1 ? '' : 's'}
            </span>
          </div>
        </button>
      ))}
    </div>
  )
}

function Thumb({ d }: { d: CarDiagram }) {
  const [failed, setFailed] = useState(false)
  return (
    <div className="flex aspect-[4/3] items-center justify-center border-b border-line bg-white">
      {d.image_url && !failed
        ? <img src={d.image_url} alt={d.label ?? 'diagram'} loading="lazy" onError={() => setFailed(true)}
            className="size-full object-contain p-2" />
        : <ImageOff className="size-6 text-gray-400" />}
    </div>
  )
}

function DiagramView({ carId, subId, diagramId, partId, onDiagram, onPart }: {
  carId: number; subId: number; diagramId: number; partId: number | null
  onDiagram: (id: number) => void; onPart: (id: number) => void
}) {
  const detail = useAsync(() => api.diagram(diagramId, carId), [diagramId, carId])
  const siblings = useAsync(() => api.carDiagrams(carId, subId), [carId, subId])
  const [showOthers, setShowOthers] = useState(false)
  const selectedRef = useRef<HTMLLIElement>(null)

  const parts = useMemo(() => {
    const all = [...(detail.data?.parts ?? [])].sort((a, b) =>
      (parseInt(a.part_index ?? '', 10) || 9999) - (parseInt(b.part_index ?? '', 10) || 9999))
    return { fits: all.filter(p => p.fits !== false), others: all.filter(p => p.fits === false) }
  }, [detail.data])

  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [partId, detail.data])

  if (detail.loading) return <Loading />
  if (detail.error) return <ErrorLine message={detail.error} onRetry={detail.retry} />
  const d = detail.data!
  const list = siblings.data ?? []
  const at = list.findIndex(x => x.id === diagramId)

  const row = (p: DiagramPart) => {
    const selected = p.id === partId
    return (
      <li key={`${p.id}-${p.part_index}`} ref={selected ? selectedRef : undefined}>
        <button onClick={() => onPart(p.id)}
          className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left ${
            selected ? 'bg-accent-soft ring-1 ring-accent' : 'hover:bg-hover'}`}>
          <span className={`mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
            selected ? 'bg-accent text-white' : 'border border-line text-muted'}`}>
            {p.part_index ?? '–'}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium">{p.title ?? 'Untitled part'}</span>
            <span className="block font-mono text-xs text-muted">{p.part_number}</span>
            {p.description && <span className="mt-0.5 line-clamp-2 block text-xs text-muted">{p.description}</span>}
          </span>
          <ChevronRight className="mt-1 size-4 shrink-0 text-muted" />
        </button>
      </li>
    )
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
      <div>
        <div className="mb-2 flex items-center gap-2">
          <h2 className="min-w-0 flex-1 truncate font-medium">{d.label ?? 'Diagram'}</h2>
          {list.length > 1 && at >= 0 && (
            <div className="flex items-center gap-1 text-sm text-muted">
              <button aria-label="Previous diagram" disabled={at === 0} onClick={() => onDiagram(list[at - 1].id)}
                className="rounded-full p-1 hover:bg-hover disabled:opacity-30"><ChevronLeft className="size-4" /></button>
              <span>Diagram {at + 1} of {list.length}</span>
              <button aria-label="Next diagram" disabled={at === list.length - 1} onClick={() => onDiagram(list[at + 1].id)}
                className="rounded-full p-1 hover:bg-hover disabled:opacity-30"><ChevronRight className="size-4" /></button>
            </div>
          )}
        </div>
        <ZoomImage key={d.id} src={d.image_url} alt={d.image_alt ?? d.label ?? 'diagram'} />
        <p className="mt-1.5 text-xs text-muted">Scroll or double-click to zoom, drag to pan. Pick a part by its callout number.</p>
      </div>

      <div className="rounded-xl border border-line bg-surface">
        <p className="section-label border-b border-line px-3 py-2">Parts on this diagram</p>
        {parts.fits.length === 0 && parts.others.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-muted">No parts listed for this diagram.</p>
        ) : (
          <ul className="flex flex-col gap-0.5 p-1.5" aria-label="Parts">
            {parts.fits.map(row)}
            {parts.fits.length === 0 && (
              <li className="px-3 py-4 text-center text-sm text-muted">None of this diagram's parts fit this exact vehicle.</li>
            )}
          </ul>
        )}
        {parts.others.length > 0 && (
          <div className="border-t border-line p-1.5">
            <button onClick={() => setShowOthers(s => !s)} className="w-full rounded-lg px-2.5 py-1.5 text-left text-xs text-muted hover:bg-hover">
              {showOthers ? 'Hide' : 'Show'} {parts.others.length} part{parts.others.length === 1 ? '' : 's'} for other trims/engines
            </button>
            {showOthers && <ul className="flex flex-col gap-0.5 opacity-60">{parts.others.map(row)}</ul>}
          </div>
        )}
      </div>
    </div>
  )
}
