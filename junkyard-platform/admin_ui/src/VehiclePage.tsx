import { useEffect, useMemo, useState } from "react";
import { ApiError, get, post, qs } from "./api.ts";
import type { CatCar, GroupKey, ScrapeJobInfo, VehicleDetail } from "./types.ts";
import { METHOD_LABEL, REASON_LABEL, STEP_LABEL } from "./types.ts";
import { Link } from "./router.tsx";
import { Combobox } from "./Combobox.tsx";
import { Empty, ErrorBanner, Loading, decodeEntities, fmtInt, keyLabel, useLoad, useToast } from "./util.tsx";

const YARD_REASONS = ["no_vin", "decode_failed"];
const FIXABLE = ["model_not_in_catalogue", "make_not_in_catalogue"];
const DECODE_FIELDS = ["ModelYear", "Make", "Model", "Series", "Trim", "Trim2", "DisplacementL", "EngineCylinders",
  "FuelTypePrimary", "DriveType", "BodyClass", "PlantCountry"];

const carName = (c: CatCar) => c.missing ? `car #${c.id} (no longer in the catalogue)`
  : [c.year, c.make, decodeEntities(c.model), decodeEntities(c.trim), c.engine && `· ${c.engine}`].filter(Boolean).join(" ");
const when = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString() : "—");

/** The discrepancy group this unmatched car belongs to, as a Discrepancies-page link. */
function groupLink(v: VehicleDetail): { to: string; label: string } | null {
  const d = v.discrepancy;
  if (!d || !d.reason) return null;
  const yard = YARD_REASONS.includes(d.reason);
  const key: GroupKey = yard
    ? { kind: "yard", make: v.make, model: v.model, series: null, source: v.source }
    : { kind: "decode", make: d.nhtsaMake, model: d.nhtsaModel, series: d.nhtsaSeries, source: null };
  const tab = yard ? "nodecode" : FIXABLE.includes(d.reason) ? "fixable" : "gaps";
  return { to: `/?tab=${tab}&g=${encodeURIComponent(JSON.stringify(key))}`, label: keyLabel(key) };
}

export function VehiclePage({ id }: { id: number }) {
  const v = useLoad(() => get<VehicleDetail>(`/api/vehicles/${id}`), `vehicle|${id}`);
  if (v.error) return <ErrorBanner error={v.error === "no such vehicle" ? `No vehicle #${id}.` : v.error} onRetry={v.reload} />;
  if (v.data == null) return <Loading what="loading vehicle…" />;
  const d = v.data;
  return (
    <div className="stack">
      <div>
        <h1>{[d.year, d.make, d.model, d.trim].filter(Boolean).join(" ") || `Vehicle #${d.id}`}
          {!d.active && <span className="tag" style={{ marginLeft: 8 }}>no longer in the yard</span>}</h1>
        <div className="row muted small">
          <span>{d.location} <span className="tag">{d.source}</span></span>
          <span>stock {d.stock}</span>
          {d.yard.row != null && <span>row {d.yard.row}</span>}
          {d.yard.arrival_date && <span>arrived {when(String(d.yard.arrival_date))}</span>}
          <span className="mono">{d.vin ?? "no VIN"}</span>
        </div>
      </div>
      <div className="split">
        <div className="stack">
          <MatchCard d={d} reload={v.reload} />
          <ManualMatch d={d} onSaved={v.reload} />
          <Rescrape id={d.id} />
        </div>
        <div className="stack">
          <Decode d={d} />
          <YardData d={d} />
        </div>
      </div>
    </div>
  );
}

function MatchCard({ d, reload }: { d: VehicleDetail; reload: () => Promise<void> }) {
  const toast = useToast();
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const m = d.match;
  const link = groupLink(d);

  // After Re-match the worker picks the car up within seconds: poll until it records a new attempt.
  useEffect(() => {
    if (!waiting) return;
    let tries = 0;
    const t = window.setInterval(async () => {
      tries += 1;
      const fresh = await get<VehicleDetail>(`/api/vehicles/${d.id}`).catch(() => null);
      if ((fresh && fresh.match.attemptedAt) || tries >= 15) {
        window.clearInterval(t); setWaiting(false); await reload();
        toast(fresh?.match.attemptedAt ? (fresh.match.resolved ? "Re-matched." : "Re-matched: still no catalogue car.")
                                       : "Still queued; refresh in a moment.", !fresh?.match.attemptedAt);
      }
    }, 2000);
    return () => window.clearInterval(t);
  }, [waiting, d.id, reload, toast]);

  const rematch = async () => {
    setError(null);
    try { await post(`/api/vehicles/${d.id}/rematch`); setWaiting(true); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };

  return (
    <section className="panel stack" aria-label="Match">
      <div className="row">
        <h2 className="grow">Match</h2>
        <button onClick={rematch} disabled={waiting}>{waiting ? "Re-matching…" : "Re-match"}</button>
      </div>
      {m.resolved ? (
        <>
          <div><span className="tag ok-tag">{METHOD_LABEL[m.method ?? ""] ?? m.method}</span>
            {m.confidence != null && <span className="muted small"> · confidence {Math.round(m.confidence * 100)}%</span>}
            <span className="muted small"> · {when(m.attemptedAt)}</span></div>
          {m.candidates.length === 0 ? <Empty>No catalogue cars recorded.</Empty> : (
            <table className="list small">
              <thead><tr><th>{m.candidateCount === 1 ? "Catalogue car" : `${fmtInt(m.candidateCount)} possible catalogue cars`}</th><th className="num">id</th></tr></thead>
              <tbody>{m.candidates.map((c) => <tr key={c.id}><td>{carName(c)}</td><td className="num muted">{c.id}</td></tr>)}</tbody>
            </table>
          )}
          {m.candidateCount > m.candidates.length && <span className="muted small">first {m.candidates.length} shown</span>}
          {(m.steps.length > 0 || m.trimUnread) && (
            <div className="small muted">
              {m.steps.length > 0 && <>Narrowed by: {m.steps.map((s) => STEP_LABEL[s] ?? s).join(", ")}. </>}
              {m.trimUnread && <>Trim text “{m.trimUnread}” wasn't understood: <Link to={`/?tab=trims&g=${encodeURIComponent(JSON.stringify(
                { kind: "trim", make: d.decode?.raw.Make ?? null, model: d.decode?.raw.Model ?? null, series: null, source: null, trim: m.trimUnread }))}`}>settle it →</Link></>}
            </div>
          )}
        </>
      ) : (
        <div className="stack" style={{ gap: 6 }}>
          <div><span className="tag err-tag">not matched</span>
            {d.discrepancy?.reason && <> — {REASON_LABEL[d.discrepancy.reason] ?? d.discrepancy.reason}</>}
            {d.discrepancy?.status === "ignored" && <span className="tag">ignored</span>}</div>
          {d.discrepancy?.nhtsaMake && (
            <div className="small">NHTSA says <strong>{[d.discrepancy.nhtsaYear, d.discrepancy.nhtsaMake, d.discrepancy.nhtsaModel].join(" ")}</strong>
              {d.discrepancy.nhtsaSeries && <> · series “{d.discrepancy.nhtsaSeries}”</>}</div>
          )}
          {link && <div className="small">Fix it for every car like this: <Link to={link.to}>{link.label} group →</Link></div>}
          {m.attemptedAt == null && <div className="muted small">Queued: the matcher hasn't looked at it yet.</div>}
        </div>
      )}
      {error && <div className="field-error" role="alert">{error}</div>}
    </section>
  );
}

/** Year → make → model → car, prefilled from the vehicle and its decode; only catalogue values can be picked. */
function ManualMatch({ d, onSaved }: { d: VehicleDetail; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const decodeMake = d.discrepancy?.nhtsaMake ?? d.decode?.raw?.Make ?? d.make;
  const decodeModel = d.discrepancy?.nhtsaModel ?? d.decode?.raw?.Model ?? d.model;
  const [year, setYear] = useState<string | null>(d.year ? String(d.year) : null);
  const [make, setMake] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [car, setCar] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);

  const years = useLoad(() => (open ? get<number[]>("/api/catalogue/years") : Promise.resolve([])), `years|${open}`);
  const makes = useLoad(() => (open && year ? get<string[]>(`/api/catalogue/year-makes${qs({ year })}`) : Promise.resolve([])), `mk|${open}|${year}`);
  const models = useLoad(() => (open && year && make ? get<string[]>(`/api/catalogue/year-models${qs({ year, make })}`) : Promise.resolve([])), `md|${year}|${make}`);
  const cars = useLoad(() => (open && year && make && model ? get<CatCar[]>(`/api/catalogue/cars${qs({ year, make, model })}`) : Promise.resolve([])), `cars|${year}|${make}|${model}`);

  // Prefill the make from the decode / yard spelling once the year's makes are in.
  useEffect(() => {
    if (make || !makes.data?.length || !decodeMake) return;
    const hit = makes.data.find((m) => m.toLowerCase() === decodeMake.toLowerCase());
    if (hit) setMake(hit);
  }, [makes.data, decodeMake, make]);

  const key = (s: string | null | undefined) => (s ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const modelOptions = useMemo(() => {
    const want = key(decodeModel);
    return (models.data ?? [])
      .map((m) => ({ value: m, label: decodeEntities(m), close: want && (key(m).startsWith(want.slice(0, 3)) || key(m).includes(want)) }))
      .sort((a, b) => Number(b.close) - Number(a.close) || a.label.localeCompare(b.label))
      .map(({ value, label, close }) => ({ value, label, hint: close ? "close to the decode" : undefined }));
  }, [models.data, decodeModel]);

  if (!open) {
    return <button className="link" style={{ alignSelf: "flex-start" }} onClick={() => setOpen(true)}>Pick the exact catalogue car by hand…</button>;
  }
  const save = async () => {
    setBusy(true); setError(null);
    try {
      await post(`/api/vehicles/${d.id}/manual`, { car_id: Number(car) });
      toast("Saved: this car is matched by hand."); setOpen(false); setConfirming(false); await onSaved();
    } catch (e) { setError(e as Error); } finally { setBusy(false); }
  };
  return (
    <section className="fix stack" aria-label="Manual match">
      <div className="row"><strong className="grow">Pick the catalogue car</strong><button className="link" onClick={() => setOpen(false)}>close</button></div>
      <div className="grid2">
        <div className="field"><label>Year</label>
          <Combobox label="Year" value={year} options={(years.data ?? []).map((y) => ({ value: String(y), label: String(y) }))}
                    onChange={(v) => { setYear(v); setMake(null); setModel(null); setCar(null); }} /></div>
        <div className="field"><label>Make</label>
          <Combobox label="Make" value={make} placeholder={year ? "Pick a make…" : "pick a year first"}
                    options={(makes.data ?? []).map((m) => ({ value: m, label: m }))}
                    onChange={(v) => { setMake(v); setModel(null); setCar(null); }} /></div>
        <div className="field"><label>Model</label>
          <Combobox label="Model" value={model} placeholder={make ? `Pick a ${make} model…` : "pick a make first"}
                    options={modelOptions} onChange={(v) => { setModel(v); setCar(null); }} /></div>
        <div className="field"><label>Car (trim · engine)</label>
          <Combobox label="Car" value={car} placeholder={model ? "Pick the trim and engine…" : "pick a model first"}
                    invalid={error instanceof ApiError && error.field === "car_id"}
                    options={(cars.data ?? []).map((c) => ({ value: String(c.id), label: [decodeEntities(c.trim) || "(no trim)", c.engine].filter(Boolean).join(" · "), hint: `#${c.id}` }))}
                    onChange={setCar} /></div>
      </div>
      {model && cars.data && cars.data.length === 0 && <span className="muted small">The catalogue has no cars for that year, make and model.</span>}
      <div className="row">
        {!confirming && <button className="primary" disabled={!car} onClick={() => setConfirming(true)}>Save…</button>}
        {confirming && <>
          <span className="small">Match this car by hand? Re-matching later undoes it.</span>
          <button className="primary" disabled={busy} onClick={save}>{busy ? "Saving…" : "Yes, save"}</button>
          <button disabled={busy} onClick={() => setConfirming(false)}>Cancel</button>
        </>}
      </div>
      {error && <div className="field-error" role="alert">{error.message}</div>}
    </section>
  );
}

function Rescrape({ id }: { id: number }) {
  const toast = useToast();
  const info = useLoad(() => get<ScrapeJobInfo>(`/api/vehicles/${id}/scrapejob`), `sj|${id}`);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const j = info.data?.job;
  const run = async () => {
    setBusy(true); setError(null);
    try {
      await post(`/api/vehicles/${id}/rescrape`);
      toast(`Run requested for ${j?.name}; scrape-job-manager starts it on its next pass.`);
      setConfirming(false); await info.reload();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  return (
    <section className="panel stack" aria-label="Re-scrape the yard">
      <h2>Yard scrape</h2>
      {info.error && <ErrorBanner error={info.error} onRetry={info.reload} />}
      {info.data == null ? (info.error ? null : <Loading />) : !info.data.available ? (
        <div className="muted small">Re-scrape isn't available: {info.data.reason}.</div>
      ) : j && (
        <>
          <table className="list small"><tbody>
            <tr><td className="muted">ScrapeJob</td><td>{j.name} {j.suspended && <span className="tag">suspended (manual runs only)</span>}</td></tr>
            <tr><td className="muted">State</td><td>{j.running ? "running now" : j.phase}{j.runNowRequested && !j.running ? " · run requested" : ""}</td></tr>
            <tr><td className="muted">Last run</td><td>{j.lastRun ? `${j.lastRun.result}${j.lastRun.reason ? ` (${j.lastRun.reason})` : ""} · ${fmtInt(j.lastRun.items)} cars · ${when(j.lastRun.finishedAt)}` : "never"}</td></tr>
            <tr><td className="muted">Next run</td><td>{j.suspended ? "—" : when(j.nextRunAt)}</td></tr>
          </tbody></table>
          <div className="row">
            {!confirming && <button disabled={j.running} onClick={() => setConfirming(true)}
                                    title={j.running ? "a run is in progress" : ""}>Run {j.name} now…</button>}
            {confirming && <>
              <span className="small">Scrape {info.data.source}'s live site now? Every car from this yard is refreshed.</span>
              <button className="primary" disabled={busy} onClick={run}>{busy ? "Requesting…" : "Yes, run it"}</button>
              <button disabled={busy} onClick={() => setConfirming(false)}>Cancel</button>
            </>}
            <button className="link" onClick={info.reload}>refresh</button>
          </div>
        </>
      )}
      {error && <div className="field-error" role="alert">{error}</div>}
    </section>
  );
}

function Decode({ d }: { d: VehicleDetail }) {
  const raw = d.decode?.raw ?? {};
  const filled = Object.entries(raw).filter(([, v]) => v && v !== "Not Applicable" && v !== "0");
  return (
    <section className="panel stack" aria-label="NHTSA decode">
      <h2>NHTSA decode</h2>
      {!d.vin ? <Empty>The yard gives no VIN for this car.</Empty> : !d.decode ? <Empty>Not decoded yet.</Empty> : (
        <>
          {d.decode.error && <div className="callout small">NHTSA couldn't fully decode this VIN (error {d.decode.error}): {raw.ErrorText}</div>}
          <table className="list small"><tbody>
            {DECODE_FIELDS.filter((f) => raw[f]).map((f) => <tr key={f}><td className="muted">{f}</td><td>{raw[f]}</td></tr>)}
          </tbody></table>
          <details><summary>full record ({filled.length} fields)</summary>
            <table className="list small"><tbody>
              {filled.map(([k, val]) => <tr key={k}><td className="muted">{k}</td><td>{val}</td></tr>)}
            </tbody></table>
          </details>
        </>
      )}
    </section>
  );
}

function YardData({ d }: { d: VehicleDetail }) {
  const extras = Object.entries(d.extras ?? {});
  return (
    <section className="panel stack" aria-label="Yard data">
      <h2>What the yard says</h2>
      <table className="list small"><tbody>
        {Object.entries(d.yard).map(([k, val]) => (
          <tr key={k}><td className="muted">{k.replace(/_/g, " ")}</td>
            <td>{k === "preview_image_url" ? <a href={String(val)} target="_blank" rel="noreferrer">image</a> : String(val)}</td></tr>
        ))}
        {extras.map(([k, val]) => <tr key={`x-${k}`}><td className="muted">{k} <span className="tag">extra</span></td><td>{typeof val === "object" ? JSON.stringify(val) : String(val)}</td></tr>)}
      </tbody></table>
    </section>
  );
}
