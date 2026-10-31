import { useState } from "react";
import { post } from "./api.ts";
import type { Count, GroupDetail, GroupKey, Tab } from "./types.ts";
import { REASON_LABEL } from "./types.ts";
import { MapPanel } from "./MapPanel.tsx";
import { Link } from "./router.tsx";
import { RulePanel } from "./RulePanel.tsx";
import { TrimPanel } from "./TrimPanel.tsx";
import { describeProposal } from "./suggestions.ts";
import { Empty, ErrorBanner, Loading, fmtInt, keyLabel, useLoad, years } from "./util.tsx";

export type Resolved = (key: GroupKey, message: string) => void;

export function GroupPanel({ groupKey, status, tab, yard, onResolved }: {
  groupKey: GroupKey; status: "open" | "ignored"; tab: Tab; yard?: string; onResolved: Resolved;
}) {
  const detail = useLoad(() => post<GroupDetail>("/api/discrepancies/group", { key: groupKey, status }),
                         JSON.stringify(groupKey) + status);
  if (detail.error) return <ErrorBanner error={detail.error} onRetry={detail.reload} />;
  if (detail.data == null) return <Loading what="loading group…" />;
  const d = detail.data;
  return (
    <div className="stack">
      <div>
        <h2>{groupKey.kind === "yard" && <span className="tag">{groupKey.source}</span>} {keyLabel(groupKey)}</h2>
        <div className="row muted small">
          <span>{fmtInt(d.vehicles)} cars</span><span>·</span><span>{years(d.yearMin, d.yearMax)}</span>
          {d.byReason.map((r) => <span key={String(r.value)} className="tag">{REASON_LABEL[String(r.value)] ?? r.value} · {fmtInt(r.vehicles)}</span>)}
        </div>
        {yard && groupKey.kind === "decode" && (
          <div className="small muted">
            All yards shown (a fix applies everywhere): {fmtInt(d.byYard.find((y) => y.value === yard)?.vehicles ?? 0)} of
            these are at {yard}.
          </div>
        )}
      </div>

      {d.pendingSuggestion && (
        <div className="callout">
          An agent suggested a fix for this group: {describeProposal(d.pendingSuggestion.kind, d.pendingSuggestion.proposal)}.{" "}
          <Link to={`/suggestions?id=${d.pendingSuggestion.id}`}>Review it</Link>
        </div>
      )}
      {!d.pendingSuggestion && d.suggesterAttempt && d.suggesterAttempt.outcome !== "filed" && (
        <div className="small muted">
          Suggester ({new Date(d.suggesterAttempt.at + "Z").toLocaleDateString()}, {d.suggesterAttempt.prompt}): {d.suggesterAttempt.outcome}
          {d.suggesterAttempt.reason ? `: ${d.suggesterAttempt.reason}` : ""}
        </div>
      )}
      {status === "open" && groupKey.kind === "decode" && <MapPanel d={d} onResolved={onResolved} />}
      {status === "open" && groupKey.kind === "yard" && <RulePanel d={d} onResolved={onResolved} />}
      {groupKey.kind === "trim" && <TrimPanel d={d} onResolved={onResolved} />}
      {groupKey.kind !== "trim" && <StatusActions d={d} onResolved={onResolved} />}

      <Coverage d={d} tab={tab} />
      <div className="grid2">
        <Breakdown title="By yard" rows={d.byYard} />
        <Breakdown title="By year" rows={d.byYear} cls={yearCoverage(d)}
                   legend={d.key.kind === "decode" ? <CoverageLegend /> : null} />
      </div>
      <Samples d={d} />
    </div>
  );
}

/** Ignore (confirmed inline: it hides cars) or reopen an ignored group. */
function StatusActions({ d, onResolved }: { d: GroupDetail; onResolved: Resolved }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ignore = d.status === "open";
  const run = async () => {
    setBusy(true); setError(null);
    try {
      const r = await post<{ updated: number }>("/api/discrepancies/status", { key: d.key, ignore });
      onResolved(d.key, ignore ? `Ignored ${keyLabel(d.key)} (${fmtInt(r.updated)} cars). Find it under Ignored.`
                               : `Reopened ${keyLabel(d.key)} (${fmtInt(r.updated)} cars).`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e)); setBusy(false);
    }
  };
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row">
        {ignore && !confirming && <button onClick={() => setConfirming(true)}>Ignore this group…</button>}
        {ignore && confirming && (
          <>
            <span>Ignore {fmtInt(d.vehicles)} cars? They leave this list until reopened.</span>
            <button className="danger" disabled={busy} onClick={run}>{busy ? "Ignoring…" : "Yes, ignore"}</button>
            <button disabled={busy} onClick={() => setConfirming(false)}>Cancel</button>
          </>
        )}
        {!ignore && <button className="primary" disabled={busy} onClick={run}>{busy ? "Reopening…" : "Reopen"}</button>}
      </div>
      {error && <div className="field-error" role="alert">{error}</div>}
    </div>
  );
}

function Coverage({ d, tab }: { d: GroupDetail; tab: Tab }) {
  if (d.key.kind !== "decode") return null;
  const cat = d.makeYears;
  return (
    <div className={tab === "gaps" ? "callout" : "muted small"}>
      {d.catalogueMake == null || cat == null
        ? <>The catalogue has no cars of make <strong>{d.key.make}</strong>.</>
        : <>The catalogue has <strong>{cat.name}</strong> for {years(cat.yearMin, cat.yearMax)}; these cars are {years(d.yearMin, d.yearMax)}.</>}
    </div>
  );
}

/** Colour a year bar by what the catalogue has for it: this model, only the make, or nothing. */
function yearCoverage(d: GroupDetail): ((value: Count["value"]) => string) | undefined {
  if (d.key.kind !== "decode" || !d.catalogueYears) return undefined;
  const model = new Set(d.modelYears ?? []), make = new Set(d.catalogueYears);
  return (v) => (typeof v !== "number" ? "" : model.has(v) ? "cov-model" : make.has(v) ? "cov-make" : "cov-none");
}

function CoverageLegend() {
  return (
    <div className="legend small muted">
      <span><i className="bar cov-model" /> model in catalogue</span>
      <span><i className="bar cov-make" /> make only</span>
      <span><i className="bar cov-none" /> not in catalogue</span>
    </div>
  );
}

function Breakdown({ title, rows, cls, legend }: {
  title: string; rows: Count[]; cls?: (value: Count["value"]) => string; legend?: React.ReactNode;
}) {
  const [all, setAll] = useState(false);
  const max = Math.max(1, ...rows.map((r) => r.vehicles));
  const shown = all ? rows : rows.slice(0, 8);
  return (
    <div>
      <h3>{title}</h3>
      {rows.length === 0 ? <Empty>none</Empty> : (
        <table className="bars">
          <tbody>
            {shown.map((r) => (
              <tr key={String(r.value)}>
                <td className="nowrap">{r.value ?? "—"}</td>
                <td className="bar-cell"><div className={`bar ${cls ? cls(r.value) : ""}`} style={{ width: `${(100 * r.vehicles) / max}%` }} /></td>
                <td className="num">{fmtInt(r.vehicles)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rows.length > 8 && <button className="link" onClick={() => setAll(!all)}>{all ? "fewer" : `all ${rows.length}`}</button>}
      {legend}
    </div>
  );
}

function Samples({ d }: { d: GroupDetail }) {
  const [open, setOpen] = useState(false);
  return (
    <details open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Sample cars ({d.samples.length} newest of {fmtInt(d.vehicles)})</summary>
      <table className="list small">
        <thead><tr><th>Yard</th><th>Year</th><th>Yard says</th>{d.key.kind === "trim" && <th>NHTSA series</th>}<th>VIN</th><th>Stock / row</th></tr></thead>
        <tbody>
          {d.samples.map((s) => (
            <tr key={s.id}>
              <td><Link to={`/vehicles/${s.id}`}>{s.location}</Link><div className="muted">{s.source}</div></td>
              <td>{s.year ?? "—"}</td>
              <td>{[s.make, s.model, s.trim].filter(Boolean).join(" ")}</td>
              {d.key.kind === "trim" && <td className="muted">{s.series ?? "—"}</td>}
              <td className="mono">{s.vin ?? <span className="muted">none</span>}</td>
              <td className="muted">{s.stock}{s.row ? ` · row ${s.row}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
