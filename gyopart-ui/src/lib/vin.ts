import type { VinDecoded } from '../types'

export type Verdict = 'agree' | 'differ' | 'unknown'

/** NHTSA VINs: 17 characters, no I, O or Q. Returns the inline error, or null when valid. */
export function vinError(vin: string): string | null {
  const v = vin.trim().toUpperCase()
  if (!v) return null
  if (/[IOQ]/.test(v)) return 'VINs never contain I, O or Q'
  if (/[^A-Z0-9]/.test(v)) return 'Letters and digits only'
  if (v.length !== 17) return `A VIN is 17 characters (this is ${v.length})`
  return null
}

const key = (s: string | null | undefined) => (s ?? '').toLowerCase().replace(/&/g, 'and').replace(/[^a-z0-9]/g, '')

function engineSpec(name: string | null) {
  const m = /^\s*(\d+(?:\.\d+)?)L\s+[A-Z]+(\d+)/i.exec(name ?? '')
  return m ? { disp: parseFloat(m[1]), cyl: parseInt(m[2], 10) } : null
}

export function decodedEngineLabel(d: VinDecoded) {
  const parts = [
    d.displacement_l ? `${d.displacement_l.toFixed(1)}L` : null,
    d.cylinders ? `${d.cylinders} cyl` : null,
    d.fuel,
  ].filter(Boolean)
  return parts.length ? parts.join(' ') : null
}

export interface FieldCheck { field: string; picked: string | null; decoded: string | null; verdict: Verdict }

/** Field-by-field comparison of the picked vehicle with the NHTSA decode. */
export function compare(
  picked: { year: string | null; make: string | null; model: string | null; trim: string | null; engine: string | null },
  d: VinDecoded,
): FieldCheck[] {
  const verdict = (have: string | null, want: string | null, eq: () => boolean): Verdict =>
    !want || !have ? 'unknown' : eq() ? 'agree' : 'differ'

  const models = new Set([d.model, ...(d.model ?? '').split('/'), d.model && d.series ? `${d.model} ${d.series}` : null]
    .filter(Boolean).map(key))
  const trims = new Set([d.trim, d.series].filter(Boolean).map(t => t!.trim().toLowerCase()))
  const pe = engineSpec(picked.engine)
  const decodedEngine = decodedEngineLabel(d)

  return [
    { field: 'Year', picked: picked.year, decoded: d.year,
      verdict: verdict(picked.year, d.year, () => picked.year === d.year) },
    { field: 'Make', picked: picked.make, decoded: d.make,
      verdict: verdict(picked.make, d.make, () => key(picked.make) === key(d.make)) },
    { field: 'Model', picked: picked.model, decoded: [d.model, d.series].filter(Boolean).join(' ') || null,
      verdict: verdict(picked.model, d.model, () => models.has(key(picked.model))) },
    { field: 'Trim', picked: picked.trim, decoded: d.trim ?? d.series,
      verdict: verdict(picked.trim, d.trim ?? d.series, () => trims.has((picked.trim ?? '').trim().toLowerCase())) },
    { field: 'Engine', picked: picked.engine, decoded: decodedEngine,
      verdict: verdict(picked.engine, d.displacement_l ? decodedEngine : null, () =>
        !!pe && Math.abs(pe.disp - (d.displacement_l ?? 0)) < 0.06 && (!d.cylinders || pe.cyl === d.cylinders)) },
  ]
}
