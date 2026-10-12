import { useParams } from 'react-router'

/** Workflow 2 (find a part on my vehicle) — next. */
export function CarPage() {
  const { carId } = useParams()
  return <div className="p-6 text-muted">Catalogue for car {carId} — coming next.</div>
}
