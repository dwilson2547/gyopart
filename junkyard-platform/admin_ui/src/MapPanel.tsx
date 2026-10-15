import { useMemo, useState } from "react";
import { ApiError, get, post, qs } from "./api.ts";
import type { GroupDetail, MakeOption, ModelOption, Preview } from "./types.ts";
import { REASON_LABEL } from "./types.ts";
import { Combobox } from "./Combobox.tsx";
import type { Resolved } from "./GroupPanel.tsx";
import { decodeEntities, fmtInt, useLoad, yearSpans } from "./util.tsx";

type Target = { make: string; model: string };

/** Map a decode group to catalogue model(s): pick (suggested chips or the searchable list), preview, confirm.
 *  Everything on the decode side comes from the group; targets can only be picked from the catalogue. */
export function MapPanel({ d, onResolved }: { d: GroupDetail; onResolved: Resolved }) {
  const k = d.key;
  const noModels = !d.catalogueMake || !d.makeYears;
  const [otherMake, setOtherMake] = useState(noModels);
  const [make, setMake] = useState<string | null>(noModels ? null : d.catalogueMake);
  const [targets, setTargets] = useState<Target[]>([]);
  const [yearFrom, setYearFrom] = useState<string>(d.yearMin ? String(d.yearMin) : "");
  const [yearTo, setYearTo] = useState<string>(d.yearMax ? String(d.yearMax) : "");
  const [anySeries, setAnySeries] = useState(false);
  const [allYears, setAllYears] = useState(false);
  const [preview, setPreview] = useState<{ result: Preview; inputs: string } | null>(null);
  const [error, setError] = useState<{ field: string | null; message: string } | null>(null);
  const [busy, setBusy] = useState<"preview" | "confirm" | null>(null);

  const yf = yearFrom ? Number(yearFrom) : null;
  const yt = yearTo ? Number(yearTo) : null;
  const names = [k.series ? `${k.model} ${k.series}` : null, k.model].filter(Boolean) as string[];

  const makes = useLoad(() => (otherMake ? get<MakeOption[]>("/api/catalogue/makes") : Promise.resolve([])),
                        `makes|${otherMake}`);
  const ownMake = make === d.catalogueMake && !otherMake;
  const suggestions = useLoad<ModelOption[]>(
    () => (!make ? Promise.resolve([]) : ownMake ? Promise.resolve(d.suggestions ?? [])
      : get(`/api/catalogue/suggest${qs({ make, year_from: yf, year_to: yt })}${names.map((n) => `&name=${encodeURIComponent(n)}`).join("")}`)),
    `sugg|${make}|${ownMake}|${yf}|${yt}`);
  const models = useLoad<ModelOption[]>(
    () => (make ? get(`/api/catalogue/models${qs({ make, year_from: yf, year_to: yt })}`) : Promise.resolve([])),
    `models|${make}|${yf}|${yt}`);

  const inputs = JSON.stringify({ targets, yf, yt, anySeries });
  const previewFresh = preview?.inputs === inputs;
  const has = (t: Target) => targets.some((x) => x.make === t.make && x.model === t.model);
  const toggle = (t: Target) => { setTargets(has(t) ? targets.filter((x) => !(x.make === t.make && x.model === t.model)) : [...targets, t]); setError(null); };

  const modelOptions = useMemo(() => (models.data ?? [])
    .filter((m) => allYears || m.yearsInRange > 0)
    .filter((m) => make && !has({ make, model: m.name }))
    .map((m) => ({ value: m.name, label: decodeEntities(m.name), hint: yearSpans(m.years), dim: m.yearsInRange === 0 })),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [models.data, allYears, targets, make]);

  const yearsInvalid = yf != null && yt != null && yf > yt;
  const body = () => ({
    make: k.make, model: k.model, series: k.series && !anySeries ? k.series : null,
    year_from: yf, year_to: yt, targets,
  });
  const fail = (e: unknown) => setError(e instanceof ApiError ? { field: e.field, message: e.message }
                                                           : { field: null, message: String(e) });

  const runPreview = async () => {
    if (!targets.length) return setError({ field: "targets", message: "Pick at least one catalogue model." });
    if (yearsInvalid) return setError({ field: "years", message: "The first year is after the last." });
    setBusy("preview"); setError(null);
    try { setPreview({ result: await post<Preview>("/api/mappings/preview", body()), inputs }); }
    catch (e) { fail(e); } finally { setBusy(null); }
  };

  const confirm = async () => {
    setBusy("confirm"); setError(null);
    try {
      const r = await post<{ created: number; requeued: number }>("/api/mappings", body());
      const p = preview!.result;
      onResolved(k, `Mapped ${k.make} ${k.model}: ${fmtInt(r.requeued)} cars re-matching, ${fmtInt(p.wouldMatch)} expected to match.`);
    } catch (e) { fail(e); setBusy(null); }
  };

  const errFor = (f: string) => (error && error.field?.startsWith(f) ? error.message : null);
  const p = previewFresh ? preview!.result : null;

  return (
    <div className="fix stack" aria-label="Map to catalogue">
      <div className="row">
        <strong className="grow">Map to catalogue</strong>
        <label className="row small muted" style={{ gap: 4 }}>
          <input type="checkbox" checked={otherMake} onChange={(e) => {
            setOtherMake(e.target.checked); setMake(e.target.checked ? null : d.catalogueMake); }} />
          different make
        </label>
      </div>

      {d.mappings && d.mappings.length > 0 && (
        <div className="small muted">Already mapped: {d.mappings.map((m) => `${decodeEntities(m.model)}${m.series ? ` (series ${m.series})` : ""}`).join(", ")}</div>
      )}

      {otherMake && (
        <div className="field">
          <label>Catalogue make</label>
          <Combobox label="Catalogue make" placeholder="Pick a make…" value={make} autoFocus={noModels}
                    options={(makes.data ?? []).map((m) => ({ value: m.name, label: m.name, hint: `${m.yearMin}–${m.yearMax}` }))}
                    onChange={(v) => { setMake(v); setPreview(null); }} />
          {noModels && <span className="small muted">The catalogue has no {k.make} cars, so pick the make it lists them under.</span>}
        </div>
      )}

      {make && (
        <div className="field">
          <label>{decodeEntities(make)} models for {k.model}{k.series ? ` · ${k.series}` : ""} <span className="muted">(pick one or more)</span></label>
          {suggestions.loading && !suggestions.data ? <span className="muted small">finding suggestions…</span> :
            (suggestions.data ?? []).length === 0
              ? <span className="small muted">No close {decodeEntities(make)} model names; search the full list below{!allYears ? " or show all years" : ""}.</span>
              : (
                <div className="chips">
                  {(suggestions.data ?? []).map((s) => {
                    const t = { make, model: s.name };
                    return (
                      <button key={s.name} type="button" aria-pressed={has(t)}
                              className={`chip${has(t) ? " on" : ""}${s.yearsInRange === 0 ? " off-range" : ""}`}
                              onClick={() => toggle(t)}>
                        <span>{has(t) ? "✓ " : ""}{decodeEntities(s.name)}</span>
                        <span className="muted">{yearSpans(s.years)}</span>
                      </button>
                    );
                  })}
                </div>
              )}
          <div className="row">
            <div className="grow">
              <Combobox label="Add a catalogue model" placeholder={`Search ${decodeEntities(make)} models…`}
                        value={null} options={modelOptions} invalid={!!errFor("targets")}
                        onChange={(v) => v && toggle({ make, model: v })} />
            </div>
            <label className="row small muted" style={{ gap: 4 }}>
              <input type="checkbox" checked={allYears} onChange={(e) => setAllYears(e.target.checked)} /> show all years
            </label>
          </div>
        </div>
      )}

      {targets.length > 0 && (
        <div className="chips" aria-label="Chosen targets">
          {targets.map((t) => (
            <span key={`${t.make}|${t.model}`} className="chip on">
              <span>{t.make !== d.catalogueMake ? `${t.make} ` : ""}{decodeEntities(t.model)}{" "}
                <button type="button" className="link" aria-label={`remove ${decodeEntities(t.model)}`} onClick={() => toggle(t)}>×</button></span>
            </span>
          ))}
        </div>
      )}
      {errFor("targets") && <div className="field-error">{errFor("targets")}</div>}

      <div className="row">
        <div className="field">
          <label>Years</label>
          <div className="row">
            <input type="number" aria-label="First year" value={yearFrom} onChange={(e) => setYearFrom(e.target.value)} />
            <span className="muted">to</span>
            <input type="number" aria-label="Last year" value={yearTo} onChange={(e) => setYearTo(e.target.value)} />
          </div>
        </div>
        {k.series && (
          <div className="field">
            <label>Series</label>
            <div className="row small">
              <label className="row" style={{ gap: 4 }}><input type="radio" checked={!anySeries} onChange={() => setAnySeries(false)} /> only “{k.series}”</label>
              <label className="row" style={{ gap: 4 }}><input type="radio" checked={anySeries} onChange={() => setAnySeries(true)} /> any series</label>
            </div>
          </div>
        )}
      </div>
      {(yearsInvalid || errFor("years") || errFor("year")) && (
        <div className="field-error">{errFor("years") ?? errFor("year") ?? "The first year is after the last."}</div>
      )}

      <div className="row">
        <button onClick={runPreview} disabled={busy != null || !targets.length || yearsInvalid}>
          {busy === "preview" ? "Checking…" : "Preview"}
        </button>
        <button className="primary" onClick={confirm} disabled={busy != null || !p}
                title={p ? "" : "Preview first; it must match the current choices"}>
          {busy === "confirm" ? "Saving…" : "Confirm"}
        </button>
        {preview && !previewFresh && <span className="small muted">choices changed: preview again</span>}
      </div>

      {p && (
        <div className={`preview${p.wouldMatch ? "" : " none"}`} role="status">
          <strong>{fmtInt(p.wouldMatch)} of {fmtInt(p.vehicles)} cars would match</strong>
          {p.exact != null && p.wouldMatch > 0 && <> ({fmtInt(p.exact)} to exactly one car)</>}
          {p.vehicles !== d.vehicles && (
            <div className="small muted">
              This mapping covers every {k.make} {k.model} decode from {yf ?? "any year"}–{yt ?? "any year"}
              {k.series && !anySeries ? ` with series “${k.series}”` : " (any series)"}: {fmtInt(p.vehicles)} unmatched
              cars, {fmtInt(d.vehicles)} of them in this group.
            </div>
          )}
          {Object.keys(p.unmatched).length > 0 && (
            <div className="small muted">
              still unmatched: {Object.entries(p.unmatched).map(([r, n]) => `${fmtInt(n)} ${REASON_LABEL[r] ?? r}`).join(", ")}
            </div>
          )}
        </div>
      )}
      {error && !error.field?.match(/^(targets|years?)/) && <div className="field-error" role="alert">{error.message}</div>}
    </div>
  );
}
