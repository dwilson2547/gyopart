import { useState } from "react";
import { ApiError, post } from "./api.ts";
import type { GroupDetail, Suggestion, TrimPreview } from "./types.ts";
import type { Resolved } from "./GroupPanel.tsx";
import { proposalFor, saveFix } from "./suggestions.ts";
import { decodeEntities, fmtInt, yearSpans } from "./util.tsx";

/** Settle a trim text (matching-v2-design §2.2): it means these catalogue trims (picked from the trims the
 *  group's cars could be), or it's noise. For this model or every model of the make; preview, then confirm.
 *  `from`: tweaking a suggestion, so start from its proposal and save through its approve. */
export function TrimPanel({ d, onResolved, from }: { d: GroupDetail; onResolved: Resolved; from?: Suggestion }) {
  const k = d.key;
  const init = proposalFor(from, "trim_mapping");
  const options = d.candidateTrims ?? [];
  const [action, setAction] = useState<"map" | "noise">(init?.action ?? "map");
  const [picked, setPicked] = useState<string[]>(init?.trims ?? []);
  const [everyModel, setEveryModel] = useState(!!init && !init.model);
  const [yearFrom, setYearFrom] = useState(init?.year_from ? String(init.year_from) : "");
  const [yearTo, setYearTo] = useState(init?.year_to ? String(init.year_to) : "");
  const [preview, setPreview] = useState<{ result: TrimPreview; inputs: string } | null>(null);
  const [error, setError] = useState<{ field: string | null; message: string } | null>(null);
  const [busy, setBusy] = useState<"preview" | "confirm" | null>(null);

  const yf = yearFrom ? Number(yearFrom) : null;
  const yt = yearTo ? Number(yearTo) : null;
  const inputs = JSON.stringify({ action, picked, everyModel, yf, yt });
  const p = preview?.inputs === inputs ? preview.result : null;
  const toggle = (t: string) => { setPicked(picked.includes(t) ? picked.filter((x) => x !== t) : [...picked, t]); setError(null); };
  const body = () => ({ make: k.make, model: everyModel ? null : k.model, trim: k.trim, action,
                        trims: action === "map" ? picked : [], year_from: yf, year_to: yt });
  const fail = (e: unknown) => setError(e instanceof ApiError ? { field: e.field, message: e.message } : { field: null, message: String(e) });
  const yearsInvalid = yf != null && yt != null && yf > yt;
  const ready = !yearsInvalid && (action === "noise" || picked.length > 0);

  const runPreview = async () => {
    setBusy("preview"); setError(null);
    try { setPreview({ result: await post<TrimPreview>("/api/trim-mappings/preview", body()), inputs }); }
    catch (e) { fail(e); } finally { setBusy(null); }
  };
  const confirm = async () => {
    setBusy("confirm"); setError(null);
    try {
      const r = await saveFix("/api/trim-mappings", "trim_mapping", body(), p!, from);
      onResolved(k, action === "noise"
        ? `“${k.trim}” is noise for ${k.make}${everyModel ? "" : ` ${k.model}`}: ${fmtInt(r.requeued)} cars re-matching.`
        : `“${k.trim}” → ${picked.join(" / ")}: ${fmtInt(r.requeued)} cars re-matching, ${fmtInt(p!.exact)} expected exact.`);
    } catch (e) { fail(e); setBusy(null); }
  };

  return (
    <div className="fix stack" aria-label="Settle trim text">
      <strong>What does “{k.trim}” mean?</strong>
      {(d.trimMappings ?? []).length > 0 && (
        <div className="small muted">Already settled for other years or models: {d.trimMappings!.map((m) =>
          `${m.action === "noise" ? "noise" : m.trims.join(" / ")} (${m.nhtsaModel ?? "every model"}${m.yearFrom || m.yearTo ? `, ${m.yearFrom ?? "…"}–${m.yearTo ?? "…"}` : ""})`).join("; ")}</div>
      )}
      <div className="row small">
        <label className="row" style={{ gap: 4 }}><input type="radio" checked={action === "map"} onChange={() => setAction("map")} /> it names a trim</label>
        <label className="row" style={{ gap: 4 }}><input type="radio" checked={action === "noise"} onChange={() => setAction("noise")} /> it's noise (says nothing about the trim)</label>
      </div>

      {action === "map" && (
        <div className="field">
          <label>Catalogue trims these cars could be <span className="muted">(pick one, or several when it could be any of them)</span></label>
          {options.length === 0 ? <span className="small muted">No catalogue trims among the candidates.</span> : (
            <div className="chips">
              {options.map((t) => (
                <button key={t.name} type="button" aria-pressed={picked.includes(t.name)}
                        className={`chip${picked.includes(t.name) ? " on" : ""}`} onClick={() => toggle(t.name)}
                        title={t.models.map(decodeEntities).join(", ")}>
                  <span>{picked.includes(t.name) ? "✓ " : ""}{decodeEntities(t.name)}</span>
                  <span className="muted">{fmtInt(t.vehicles)} cars · {yearSpans(t.years)}</span>
                </button>
              ))}
            </div>
          )}
          {error?.field?.startsWith("trims") && <div className="field-error">{error.message}</div>}
        </div>
      )}

      <div className="row">
        <div className="field">
          <label>Applies to</label>
          <div className="row small">
            <label className="row" style={{ gap: 4 }}><input type="radio" checked={!everyModel} onChange={() => setEveryModel(false)} /> {k.make} {k.model}</label>
            <label className="row" style={{ gap: 4 }}><input type="radio" checked={everyModel} onChange={() => setEveryModel(true)} /> every {k.make} model</label>
          </div>
        </div>
        <div className="field">
          <label>Years <span className="muted">(blank = all)</span></label>
          <div className="row">
            <input type="number" aria-label="First year" placeholder={d.yearMin ? String(d.yearMin) : ""} value={yearFrom} onChange={(e) => setYearFrom(e.target.value)} />
            <span className="muted">to</span>
            <input type="number" aria-label="Last year" placeholder={d.yearMax ? String(d.yearMax) : ""} value={yearTo} onChange={(e) => setYearTo(e.target.value)} />
          </div>
        </div>
      </div>
      {yearsInvalid && <div className="field-error">The first year is after the last.</div>}

      <div className="row">
        <button onClick={runPreview} disabled={busy != null || !ready}>{busy === "preview" ? "Checking…" : "Preview"}</button>
        <button className="primary" onClick={confirm} disabled={busy != null || !p}
                title={p ? "" : "Preview first; it must match the current choices"}>{busy === "confirm" ? "Saving…" : "Confirm"}</button>
        {preview && !p && <span className="small muted">choices changed: preview again</span>}
      </div>

      {p && (
        <div className={`preview${p.narrower || action === "noise" ? "" : " none"}`} role="status">
          <strong>{fmtInt(p.vehicles)} cars have this text</strong>: {fmtInt(p.exact)} would match exactly one car
          (now {fmtInt(p.exactBefore)}), {fmtInt(p.narrower)} narrower, {fmtInt(p.unchanged)} unchanged.
          {p.wider > 0 && <div className="field-error">{fmtInt(p.wider)} cars would get <em>more</em> candidates: this overrides a reading
            that worked for them. Narrow it to this model or these years.</div>}
          {p.vehicles !== d.vehicles && <div className="small muted">{fmtInt(d.vehicles)} of them are in this group; the rest already
            read or narrowed another way.</div>}
        </div>
      )}
      {error && !error.field?.startsWith("trims") && <div className="field-error" role="alert">{error.message}</div>}
    </div>
  );
}
