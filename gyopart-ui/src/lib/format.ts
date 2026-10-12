/** "today", "yesterday", "3 days ago", "5 weeks ago", or the date for anything older than a year. */
export function relativeDay(iso: string | null, now = new Date()): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const days = Math.floor((startOfDay(now) - startOfDay(d)) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 14) return `${days} days ago`
  if (days < 70) return `${Math.round(days / 7)} weeks ago`
  if (days < 365) return `${Math.round(days / 30)} months ago`
  return d.toLocaleDateString()
}

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

export function mapsUrl(y: { name: string; address: string | null; city: string | null; state: string | null; zip_code: string | null; lat: number | null; lng: number | null }) {
  const q = y.address ? [y.name, y.address, y.city, y.state, y.zip_code].filter(Boolean).join(', ')
    : y.lat != null && y.lng != null ? `${y.lat},${y.lng}` : [y.name, y.city, y.state].filter(Boolean).join(', ')
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`
}

/** Catalogue trims include junk like "!"; anything without a letter or digit is no trim. */
export function cleanTrim(trim: string | null): string | null {
  return trim && /[A-Za-z0-9]/.test(trim) ? trim : null
}
