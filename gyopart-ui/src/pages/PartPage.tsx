import { useParams } from 'react-router'

/** Workflow 3 (confirm the part) — next. */
export function PartPage() {
  const { partId } = useParams()
  return <div className="p-6 text-muted">Part {partId} — coming next.</div>
}
