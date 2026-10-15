import { useMemo, useState } from "react";
import { ApiError, get, post, qs } from "./api.ts";
import type { GroupDetail, MakeOption, ModelOption, Preview } from "./types.ts";
import { Combobox } from "./Combobox.tsx";
import type { Resolved } from "./GroupPanel.tsx";
import { decodeEntities, fmtInt, useLoad, yearSpans } from "./util.tsx";

/** Yard rule for a group with no usable VIN decode: the yard's own make/model text (from the group) means this
 *  catalogue make/model (picked). Scope: this yard only, or every yard. */
export function RulePanel({ d, onResolved }: { d: GroupDetail; onResolved: Resolved }) {
  const k = d.key;
  const [make, setMake] = useState<string | null>(d.catalogueMake ?? d.makeSuggestions?.[0]?.name ?? null);
  const [model, setModel] = useState<string | null>(null);
  const [everyYard, setEveryYard] = useState(false);
  const [allYears, setAllYears] = useState(false);
  const [preview, setPreview] = useState<{ result: Preview; inputs: string } | null>(null);
  const [error, setError] = useState<{ field: string | null; message: string } | null>(null);
  const [busy, setBusy] = useState<"preview" | "confirm" | null>(null);

  const makes = useLoad(() => get<MakeOption[]>("/api/catalogue/makes"), "makes");
  const fromDetail = make === d.modelSuggestionsMake;
  const suggestions = useLoad<ModelOption[]>(
    () => (!make || !k.model ? Promise.resolve([]) : fromDetail ? Promise.resolve(d.modelSuggestions ?? [])
      : get(`/api/catalogue/suggest${qs({ make, name: k.model, year_from: d.yearMin, year_to: d.yearMax })}`)),
    `sugg|${make}`);
  const models = useLoad<ModelOption[]>(
    () => (make ? get(`/api/catalogue/models${qs({ make, year_from: d.yearMin, year_to: d.yearMax })}`) : Promise.resolve([])),
    `models|${make}`);
  const modelOptions = useMemo(() => (models.data ?? [])
    .filter((m) => allYears || m.yearsInRange > 0)
    .map((m) => ({ value: m.name, label: decodeEntities(m.name), hint: yearSpans(m.years), dim: m.yearsInRange === 0 })),
  [models.data, allYears]);

  const inputs = JSON.stringify({ make, model, everyYard });
  const p = preview?.inputs === inputs ? preview.result : null;
  const body = () => ({ source: everyYard ? null : k.source, raw_make: k.make, raw_model: k.model, make, model });
  const fail = (e: unknown) => setError(e instanceof ApiError ? { field: e.field, message: e.message } : { field: null, message: String(e) });
  const makeIsSame = make != null && (k.make ?? "").toLowerCase() === make.toLowerCase();
  const nothingToDo = makeIsSame && !model;

  const runPreview = async () => {
    if (!make) return setError({ field: "make", message: "Pick the catalogue make." });
    if (nothingToDo) return setError({ field: "model", message: `The yard already says ${make}; pick the model it means.` });
    setBusy("preview"); setError(null);
    try { setPreview({ result: await post<Preview>("/api/rules/preview", body()), inputs }); }
    catch (e) { fail(e); } finally { setBusy(null); }
  };
  const confirm = async () => {
    setBusy("confirm"); setError(null);
    try {
      const r = await post<{ created: number; requeued: number }>("/api/rules", body());
      onResolved(k, `Rule saved: ${k.make} ${k.model ?? ""} → ${make} ${model ? decodeEntities(model) : ""}. ${fmtInt(r.requeued)} cars re-matching.`);
    } catch (e) { fail(e); setBusy(null); }
  };
  const errFor = (f: string) => (error?.field === f ? error.message : null);

  return (
    <div className="fix stack" aria-label="Yard rule">
      <strong>Yard rule <span className="muted small">— these cars have no usable VIN decode, so fix the yard's own text</span></strong>

      <div className="field">
        <label>“{k.make ?? "(blank)"}” means make</label>
        {(d.makeSuggestions ?? []).length > 0 && (
          <div className="chips">
            {(d.makeSuggestions ?? []).slice(0, 5).map((m) => (
              <button key={m.name} type="button" aria-pressed={make === m.name} className={`chip${make === m.name ? " on" : ""}`}
                      onClick={() => { setMake(m.name); setModel(null); setError(null); }}>{m.name}</button>
            ))}
          </div>
        )}
        <Combobox label="Catalogue make" placeholder="Pick a make…" value={make} invalid={!!errFor("make")}
                  options={(makes.data ?? []).map((m) => ({ value: m.name, label: m.name, hint: `${m.yearMin}–${m.yearMax}` }))}
                  onChange={(v) => { setMake(v); setModel(null); setError(null); }} />
        {makeIsSame && <span className="small muted">The yard's make already matches the catalogue.</span>}
        {errFor("make") && <span className="field-error">{errFor("make")}</span>}
      </div>

      {make && k.model && (
        <div className="field">
          <label>“{k.model}” means model <span className="muted">(optional if only the make was wrong)</span></label>
          {suggestions.data && suggestions.data.length > 0 ? (
            <div className="chips">
              {suggestions.data.slice(0, 8).map((s) => (
                <button key={s.name} type="button" aria-pressed={model === s.name}
                        className={`chip${model === s.name ? " on" : ""}${s.yearsInRange === 0 ? " off-range" : ""}`}
                        onClick={() => { setModel(model === s.name ? null : s.name); setError(null); }}>
                  <span>{decodeEntities(s.name)}</span><span className="muted">{yearSpans(s.years)}</span>
                </button>
              ))}
            </div>
          ) : !suggestions.loading && <span className="small muted">No close {make} model names; search the list.</span>}
          <div className="row">
            <div className="grow">
              <Combobox label="Catalogue model" placeholder={`Search ${make} models…`} value={model}
                        options={modelOptions} invalid={!!errFor("model")} onChange={(v) => { setModel(v); setError(null); }} />
            </div>
            <label className="row small muted" style={{ gap: 4 }}>
              <input type="checkbox" checked={allYears} onChange={(e) => setAllYears(e.target.checked)} /> show all years
            </label>
          </div>
          {errFor("model") && <span className="field-error">{errFor("model")}</span>}
        </div>
      )}

      <div className="field">
        <label>Applies to</label>
        <div className="row small">
          <label className="row" style={{ gap: 4 }}><input type="radio" checked={!everyYard} onChange={() => setEveryYard(false)} /> only {k.source}</label>
          <label className="row" style={{ gap: 4 }}><input type="radio" checked={everyYard} onChange={() => setEveryYard(true)} /> every yard</label>
        </div>
      </div>

      <div className="row">
        <button onClick={runPreview} disabled={busy != null || !make}>{busy === "preview" ? "Checking…" : "Preview"}</button>
        <button className="primary" onClick={confirm} disabled={busy != null || !p}
                title={p ? "" : "Preview first; it must match the current choices"}>
          {busy === "confirm" ? "Saving…" : "Confirm"}
        </button>
        {preview && !p && <span className="small muted">choices changed: preview again</span>}
      </div>
      {p && (
        <div className={`preview${p.wouldMatch ? "" : " none"}`} role="status">
          <strong>{fmtInt(p.wouldMatch)} of {fmtInt(p.vehicles)} cars would match</strong>
          {p.wouldMatch < p.vehicles && <div className="small muted">{fmtInt(p.vehicles - p.wouldMatch)} still find no catalogue car (often years the catalogue doesn't cover).</div>}
        </div>
      )}
      {error && !["make", "model"].includes(error.field ?? "") && <div className="field-error" role="alert">{error.message}</div>}
    </div>
  );
}
