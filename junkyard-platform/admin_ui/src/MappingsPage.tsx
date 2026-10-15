import { useMemo, useState } from "react";
import { del, get } from "./api.ts";
import type { MappingRow, RuleRow } from "./types.ts";
import { Link } from "./router.tsx";
import { Empty, ErrorBanner, Loading, decodeEntities, fmtInt, useLoad, useToast, years } from "./util.tsx";

/** Every decode mapping and yard rule, with how many cars they cover now; delete re-matches those cars. */
export function MappingsPage() {
  const mappings = useLoad(() => get<MappingRow[]>("/api/mappings"), "mappings");
  const rules = useLoad(() => get<RuleRow[]>("/api/rules"), "rules");
  const [q, setQ] = useState("");
  const toast = useToast();
  const needle = q.trim().toLowerCase();

  // One block per decode (NHTSA make/model/series/years), its catalogue targets as rows.
  const groups = useMemo(() => {
    const by = new Map<string, MappingRow[]>();
    for (const m of mappings.data ?? []) {
      const text = `${m.nhtsaMake} ${m.nhtsaModel} ${m.nhtsaSeries ?? ""} ${m.make} ${decodeEntities(m.model)}`.toLowerCase();
      if (needle && !text.includes(needle)) continue;
      const key = JSON.stringify([m.nhtsaMake, m.nhtsaModel, m.nhtsaSeries, m.yearFrom, m.yearTo]);
      by.set(key, [...(by.get(key) ?? []), m]);
    }
    return [...by.values()];
  }, [mappings.data, needle]);
  const shownRules = (rules.data ?? []).filter((r) =>
    !needle || `${r.source ?? ""} ${r.raw} ${r.canonical} ${r.makeContext ?? ""}`.toLowerCase().includes(needle));

  const removeMapping = async (m: MappingRow) => {
    const r = await del<{ requeued: number }>(`/api/mappings/${m.id}`);
    mappings.setData((mappings.data ?? []).filter((x) => x.id !== m.id));
    toast(`Deleted ${m.nhtsaMake} ${m.nhtsaModel} → ${decodeEntities(m.model)}. ${fmtInt(r.requeued)} cars re-matching.`);
    mappings.reload();
  };
  const removeRule = async (rule: RuleRow) => {
    const r = await del<{ requeued: number }>(`/api/rules/${rule.id}`);
    rules.setData((rules.data ?? []).filter((x) => x.id !== rule.id));
    toast(`Deleted rule ${rule.raw} → ${decodeEntities(rule.canonical)}. ${fmtInt(r.requeued)} cars re-matching.`);
    rules.reload();
  };

  return (
    <div className="stack">
      <div className="row">
        <h1 className="grow">Mappings &amp; rules</h1>
        <input type="text" aria-label="Filter mappings and rules" placeholder="Filter…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <section className="panel stack">
        <div>
          <h2>Decode mappings</h2>
          <p className="muted small" style={{ margin: 0 }}>What an NHTSA decode name means in the catalogue. Cars counts are active yard cars with that decode now.</p>
        </div>
        {mappings.error && <ErrorBanner error={`Mappings didn't load: ${mappings.error}`} onRetry={mappings.reload} />}
        {mappings.data == null ? (mappings.error ? null : <Loading />) : groups.length === 0 ? (
          <Empty>{needle ? "No mapping matches the filter." : <>No mappings yet. Create them from <Link to="/">Discrepancies</Link>.</>}</Empty>
        ) : (
          <table className="list">
            <thead><tr><th>NHTSA decode</th><th>Means (catalogue)</th><th className="num">Cars</th><th className="num">Matched</th><th>Added</th><th /></tr></thead>
            <tbody>
              {groups.map((rows) => rows.map((m, i) => (
                <tr key={m.id}>
                  {i === 0 && (
                    <td rowSpan={rows.length}>
                      <div className="gname">{m.nhtsaMake} {m.nhtsaModel}{m.nhtsaSeries ? ` · ${m.nhtsaSeries}` : ""}</div>
                      <div className="muted small">{m.yearFrom || m.yearTo ? years(m.yearFrom, m.yearTo) : "all years"}{m.nhtsaSeries ? "" : " · any series"}</div>
                    </td>
                  )}
                  <td>{m.make !== rows[0].nhtsaMake && m.make.toLowerCase() !== m.nhtsaMake.toLowerCase() ? `${m.make} ` : ""}{decodeEntities(m.model)}</td>
                  {i === 0 && <td rowSpan={rows.length} className="num">{fmtInt(m.vehicles)}</td>}
                  {i === 0 && <td rowSpan={rows.length} className="num">{fmtInt(m.matched)}</td>}
                  <td className="muted small nowrap">{m.createdBy} · {m.createdAt.slice(0, 10)}</td>
                  <td className="nowrap"><ConfirmDelete what={`${decodeEntities(m.model)} mapping`} cars={m.vehicles} onDelete={() => removeMapping(m)} /></td>
                </tr>
              )))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel stack">
        <div>
          <h2>Yard rules</h2>
          <p className="muted small" style={{ margin: 0 }}>For cars without a usable VIN decode: what a yard's own make/model text means.</p>
        </div>
        {rules.error && <ErrorBanner error={`Rules didn't load: ${rules.error}`} onRetry={rules.reload} />}
        {rules.data == null ? (rules.error ? null : <Loading />) : shownRules.length === 0 ? (
          <Empty>{needle ? "No rule matches the filter." : <>No yard rules yet. Create them from the <Link to="/?tab=nodecode">No decode</Link> tab.</>}</Empty>
        ) : (
          <table className="list">
            <thead><tr><th>Where</th><th>Yard says</th><th>Means</th><th className="num">Applied</th><th>Added</th><th /></tr></thead>
            <tbody>
              {shownRules.map((r) => (
                <tr key={r.id}>
                  <td>{r.scope === "source" ? <span className="tag">{r.source}</span> : <span className="muted">every yard</span>}</td>
                  <td>{r.field} “{r.raw}”{r.ruleType !== "exact" && <span className="tag" title="old-style rule">{r.ruleType}</span>}</td>
                  <td>{r.makeContext && r.field !== "make" ? `${r.makeContext} ` : ""}{decodeEntities(r.canonical)}</td>
                  <td className="num">{fmtInt(r.appliedCount)}</td>
                  <td className="muted small nowrap">{r.createdBy} · {r.createdAt.slice(0, 10)}</td>
                  <td className="nowrap"><ConfirmDelete what="rule" cars={null} onDelete={() => removeRule(r)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function ConfirmDelete({ what, cars, onDelete }: { what: string; cars: number | null; onDelete: () => Promise<void> }) {
  const [state, setState] = useState<"idle" | "confirm" | "busy">("idle");
  const [error, setError] = useState<string | null>(null);
  if (state === "idle") return <button className="danger" onClick={() => { setError(null); setState("confirm"); }}>Delete…</button>;
  return (
    <span className="row" style={{ gap: 6 }}>
      <span className="small">{cars != null ? `Delete and re-match ${fmtInt(cars)} cars?` : `Delete this ${what} and re-match its cars?`}</span>
      <button className="danger" disabled={state === "busy"} onClick={async () => {
        setState("busy");
        try { await onDelete(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); setState("confirm"); }
      }}>{state === "busy" ? "Deleting…" : "Yes, delete"}</button>
      <button disabled={state === "busy"} onClick={() => setState("idle")}>Cancel</button>
      {error && <span className="field-error" role="alert">{error}</span>}
    </span>
  );
}
