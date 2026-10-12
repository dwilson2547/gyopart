import { useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleSlash, Loader2, ScanLine, XCircle } from 'lucide-react'
import { api, errorMessage } from '../api'
import { useAsync } from '../lib/useAsync'
import { compare, vinError, type Verdict } from '../lib/vin'
import type { CarDetail, GarageVehicle, Named, VinDecode } from '../types'
import { Combobox } from './Combobox'

interface Pick { year: number | null; make: number | null; model: number | null; trim: number | null; engine: number | null }
// What the user did per level: an id, null = cleared on purpose, undefined = untouched (may be auto-picked).
type Choices = { [K in keyof Pick]?: number | null }
const EMPTY: Choices = {}
const LEVELS = ['year', 'make', 'model', 'trim', 'engine'] as const

const nameOf = (opts: Named[] | null, id: number | null) => opts?.find(o => o.id === id)?.name ?? null

/** Year → make → model → trim → engine pickers, with an optional VIN checked against NHTSA. */
export function AddVehicle({ onSaved, onCancel }: { onSaved: (v: GarageVehicle) => void; onCancel?: () => void }) {
  const [pick, setPick] = useState<Choices>(EMPTY)
  const [vin, setVin] = useState('')
  const [vinTouched, setVinTouched] = useState(false)
  const [decode, setDecode] = useState<VinDecode | null>(null)
  const [decoding, setDecoding] = useState(false)
  const [decodeError, setDecodeError] = useState<string | null>(null)

  // `sel` is the effective selection: what the user picked, plus any level with exactly one option (common for
  // engine) picked automatically, and the engine the decoded VIN pins down for the chosen trim. Derived during
  // render, so each list can depend on the levels above it; a level the user cleared stays clear.
  const auto = (choice: number | null | undefined, opts: Named[] | null, hint: number | null = null) =>
    choice !== undefined ? choice
      : opts?.length === 1 ? opts[0].id
        : hint !== null && opts?.some(o => o.id === hint) ? hint : null
  const years = useAsync(api.years, [])
  const year = pick.year ?? null
  const makes = useAsync(() => api.makes(year!), [year], year !== null)
  const make = auto(pick.make, makes.data)
  const models = useAsync(() => api.models(year!, make!), [year, make], make !== null)
  const model = auto(pick.model, models.data)
  const trims = useAsync(() => api.trims(year!, make!, model!), [year, make, model], model !== null)
  const trim = auto(pick.trim, trims.data)
  const engines = useAsync(() => api.engines(year!, make!, model!, trim!), [year, make, model, trim], trim !== null)
  const vinEngines = new Set(decode?.candidates.filter(c => c.trim_id === trim).map(c => c.engine_id))
  const engine = auto(pick.engine, engines.data, vinEngines.size === 1 ? [...vinEngines][0] : null)
  const cars = useAsync(() => api.cars(year!, make!, model!, trim!, engine!),
    [year, make, model, trim, engine], engine !== null)
  const sel: Pick = { year, make, model, trim, engine }
  const lists = { year: years, make: makes, model: models, trim: trims, engine: engines }

  // Choosing a level clears everything below it.
  const choose = (level: typeof LEVELS[number], id: number | null) => {
    const next: Choices = { ...sel, [level]: id }
    for (const l of LEVELS.slice(LEVELS.indexOf(level) + 1)) delete next[l]
    setPick(next)
  }

  const carId = cars.data?.[0]?.id ?? null
  const picked = {
    year: nameOf(years.data, sel.year), make: nameOf(makes.data, sel.make), model: nameOf(models.data, sel.model),
    trim: nameOf(trims.data, sel.trim), engine: nameOf(engines.data, sel.engine),
  }

  const vinProblem = vinError(vin)
  const runDecode = async () => {
    setVinTouched(true)
    if (vinProblem || !vin.trim()) return
    setDecoding(true)
    setDecodeError(null)
    setDecode(null)
    try {
      const d = await api.decodeVin(vin.trim().toUpperCase())
      setDecode(d)
      // Nothing picked yet: start from the decode.
      if (sel.year === null && d.candidates.length) applyDecoded(d.candidates)
    } catch (e) {
      setDecodeError(errorMessage(e))
    } finally {
      setDecoding(false)
    }
  }

  // Fill the pickers from the decode: year/make/model always agree across candidates; trim/engine only when unique.
  const applyDecoded = (cands: CarDetail[]) => {
    const c = cands[0]
    const uniq = (f: (x: CarDetail) => number | null) => new Set(cands.map(f)).size === 1 ? f(c) : null
    const trim = uniq(x => x.trim_id)
    setPick({ year: c.year_id, make: c.make_id, model: c.model_id, ...(trim !== null && { trim }) })
  }

  const candidateIds = {
    trim: new Set(decode?.candidates.map(c => c.trim_id ?? -1)),
    engine: new Set(decode?.candidates.filter(c => c.trim_id === sel.trim).map(c => c.engine_id ?? -1)),
  }

  const checks = decode ? compare(picked, decode.decoded) : null
  const pickedInCandidates = !!decode && carId !== null && decode.candidates.some(c => c.car_id === carId)

  const save = () => {
    if (carId === null) return
    onSaved({
      car_id: carId,
      year_id: sel.year!, year: picked.year!, make_id: sel.make!, make: picked.make!,
      model_id: sel.model!, model: picked.model!, trim_id: sel.trim, trim: picked.trim,
      engine_id: sel.engine, engine: picked.engine,
      vin: decode ? decode.vin : vin.trim() ? vin.trim().toUpperCase() : null,
      decoded: decode?.decoded ?? null,
      added_at: new Date().toISOString(),
    })
  }

  const noCar = sel.engine !== null && !cars.loading && !cars.error && carId === null

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={e => { e.preventDefault(); save() }}
      aria-label="Add a vehicle"
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {LEVELS.map((level, i) => (
          <Combobox
            key={level}
            label={level[0].toUpperCase() + level.slice(1)}
            options={lists[level].data ?? []}
            value={sel[level]}
            onChange={id => choose(level, id)}
            disabled={i > 0 && sel[LEVELS[i - 1]] === null}
            loading={lists[level].loading}
            error={lists[level].error}
            onRetry={lists[level].retry}
            highlightIds={level === 'trim' || level === 'engine' ? candidateIds[level] : undefined}
          />
        ))}
      </div>
      {noCar && <p className="-mt-3 text-xs text-danger">No catalogue car for this combination — pick another engine.</p>}
      {cars.error && <p className="-mt-3 text-xs text-danger">{cars.error}</p>}

      <div>
        <label htmlFor="vin" className="section-label mb-1 block">VIN <span className="normal-case tracking-normal">(optional)</span></label>
        <div className="flex gap-2">
          <input
            id="vin"
            value={vin}
            onChange={e => { setVin(e.target.value.toUpperCase()); setDecode(null); setDecodeError(null) }}
            onBlur={() => setVinTouched(true)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); runDecode() } }}
            maxLength={17}
            spellCheck={false}
            placeholder="17 characters, e.g. 1FTFW1ET5DFC10312"
            aria-invalid={vinTouched && !!vinProblem}
            className={`w-full max-w-sm rounded-lg border bg-bg px-3 py-2 font-mono text-sm tracking-wider text-text outline-none placeholder:font-sans placeholder:tracking-normal placeholder:text-muted focus:border-accent ${
              vinTouched && vinProblem ? 'border-danger' : 'border-line'
            }`}
          />
          <button
            type="button"
            onClick={runDecode}
            disabled={!vin.trim() || !!vinProblem || decoding}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-sm hover:bg-hover disabled:opacity-50"
          >
            {decoding ? <Loader2 className="size-4 animate-spin" /> : <ScanLine className="size-4" />}
            Decode
          </button>
        </div>
        {vinTouched && vinProblem && <p className="mt-1 text-xs text-danger">{vinProblem}</p>}
        {decodeError && (
          <p className="mt-1 text-xs text-danger">
            Couldn't decode the VIN ({decodeError}). The vehicle can still be saved without it.
          </p>
        )}
        {!vin && <p className="mt-1 text-xs text-muted">Decoding checks your pick against the NHTSA record for the VIN.</p>}
      </div>

      {decode && checks && (
        <VinReport decode={decode} checks={checks} matches={pickedInCandidates} hasPick={carId !== null}
          onUse={() => applyDecoded(decode.candidates)} />
      )}

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={carId === null}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-40"
        >
          Save to garage
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-hover">
            Cancel
          </button>
        )}
        {carId === null && <span className="text-xs text-muted">Pick year through engine to save.</span>}
      </div>
    </form>
  )
}

const VERDICT_ICON: Record<Verdict, React.ReactNode> = {
  agree: <CheckCircle2 className="size-4 text-ok" aria-label="agrees" />,
  differ: <XCircle className="size-4 text-danger" aria-label="differs" />,
  unknown: <CircleSlash className="size-4 text-muted" aria-label="not compared" />,
}

function VinReport({ decode, checks, matches, hasPick, onUse }: {
  decode: VinDecode
  checks: ReturnType<typeof compare>
  matches: boolean
  hasPick: boolean
  onUse: () => void
}) {
  const d = decode.decoded
  const n = decode.candidates.length
  const headline = !n
    ? `NHTSA says ${[d.year, d.make, d.model].filter(Boolean).join(' ') || 'nothing usable'} — not in the catalogue yet, so it can't be matched to a car.`
    : matches
      ? n === 1 ? 'The VIN matches this vehicle exactly.' : `The VIN fits this vehicle (one of ${n} catalogue trims/engines it could be).`
      : hasPick
        ? 'The VIN points to a different vehicle than the one picked.'
        : `The VIN fits ${n} catalogue ${n === 1 ? 'car' : 'cars'}.`
  const tone = !n ? 'bg-warn-soft' : matches ? 'bg-ok-soft' : hasPick ? 'bg-danger-soft' : 'bg-accent-soft'

  return (
    <section aria-label="VIN check" className="rounded-lg border border-line bg-surface">
      <div className={`flex flex-wrap items-center justify-between gap-2 rounded-t-lg px-4 py-2.5 text-sm ${tone}`}>
        <span>{headline}</span>
        {n > 0 && !matches && (
          <button type="button" onClick={onUse} className="rounded-lg bg-accent px-3 py-1 text-xs font-medium text-white hover:opacity-90">
            Use decoded vehicle
          </button>
        )}
      </div>
      {d.error_text && (
        <p className="flex items-start gap-2 border-t border-line px-4 py-2 text-xs text-muted">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> NHTSA warning: {d.error_text}
        </p>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-t border-line text-left">
            <th className="section-label px-4 py-1.5 font-semibold" />
            <th className="section-label px-2 py-1.5 font-semibold">Picked</th>
            <th className="section-label px-2 py-1.5 font-semibold">NHTSA</th>
            <th className="w-8" />
          </tr>
        </thead>
        <tbody>
          {checks.map(c => (
            <tr key={c.field} className="border-t border-line">
              <td className="px-4 py-1.5 text-muted">{c.field}</td>
              <td className="px-2 py-1.5">{c.picked ?? <span className="text-muted">—</span>}</td>
              <td className="px-2 py-1.5">{c.decoded ?? <span className="text-muted">not decoded</span>}</td>
              <td className="pr-3">{VERDICT_ICON[c.verdict]}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(d.drive || d.body) && (
        <p className="border-t border-line px-4 py-2 text-xs text-muted">{[d.body, d.drive].filter(Boolean).join(' · ')}</p>
      )}
    </section>
  )
}
