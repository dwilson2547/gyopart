import { useEffect, useRef, useState } from "react";
import { get, qs } from "./api.ts";
import type { VehicleHit } from "./types.ts";
import { navigate } from "./router.tsx";

/** Top-bar search: VIN (whole, or ≥5 leading/trailing characters), stock number, or vehicle id. One hit opens
 *  the vehicle; several list below. */
export function VehicleSearch() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<VehicleHit[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const away = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setHits(null); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);

  const open = (id: number) => { setHits(null); setQ(""); navigate(`/vehicles/${id}`); };
  const run = async () => {
    const term = q.trim();
    if (term.length < 2) return;
    setBusy(true); setError(null);
    try {
      const found = await get<VehicleHit[]>(`/api/vehicles/search${qs({ q: term })}`);
      if (found.length === 1) open(found[0].id); else setHits(found);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="vsearch" ref={box}>
      <input type="text" aria-label="Find a vehicle by VIN or stock number" placeholder="VIN or stock #…" value={q}
             onChange={(e) => { setQ(e.target.value); setError(null); }}
             onKeyDown={(e) => { if (e.key === "Enter") run(); if (e.key === "Escape") setHits(null); }} />
      {busy && <span className="muted small">…</span>}
      {(hits || error) && (
        <ul className="combo-list" role="listbox" aria-label="Vehicles found">
          {error && <li className="error combo-none">{error}</li>}
          {hits && hits.length === 0 && <li className="muted combo-none">No vehicle with that VIN or stock number.</li>}
          {hits?.map((h) => (
            <li key={h.id} role="option" aria-selected={false} onMouseDown={(e) => { e.preventDefault(); open(h.id); }}>
              <span>{[h.year, h.make, h.model].filter(Boolean).join(" ")}{!h.active && <span className="tag">gone</span>}</span>
              <span className="muted combo-hint">{h.location ?? h.source} · {h.stock}{h.matched ? "" : " · unmatched"}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
