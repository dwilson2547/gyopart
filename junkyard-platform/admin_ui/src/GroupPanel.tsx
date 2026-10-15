import { useState } from "react";
import { post } from "./api.ts";
import type { Count, GroupDetail, GroupKey, Tab } from "./types.ts";
import { REASON_LABEL } from "./types.ts";
import { MapPanel } from "./MapPanel.tsx";
import { Empty, ErrorBanner, Loading, fmtInt, keyLabel, useLoad, years } from "./util.tsx";

export type Resolved = (key: GroupKey, message: string) => void;

export function GroupPanel({ groupKey, status, tab, onResolved }: {
  groupKey: GroupKey; status: "open" | "ignored"; tab: Tab; onResolved: Resolved;
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
      </div>

      {status === "open" && groupKey.kind === "decode" && <MapPanel d={d} onResolved={onResolved} />}

      <Coverage d={d} tab={tab} />
      <div className="grid2">
        <Breakdown title="By yard" rows={d.byYard} />
        <Breakdown title="By year" rows={d.byYear} />
      </div>
      <Samples d={d} />
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

function Breakdown({ title, rows }: { title: string; rows: Count[] }) {
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
                <td className="bar-cell"><div className="bar" style={{ width: `${(100 * r.vehicles) / max}%` }} /></td>
                <td className="num">{fmtInt(r.vehicles)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rows.length > 8 && <button className="link" onClick={() => setAll(!all)}>{all ? "fewer" : `all ${rows.length}`}</button>}
    </div>
  );
}

function Samples({ d }: { d: GroupDetail }) {
  const [open, setOpen] = useState(false);
  return (
    <details open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Sample cars ({d.samples.length} newest of {fmtInt(d.vehicles)})</summary>
      <table className="list small">
        <thead><tr><th>Yard</th><th>Year</th><th>Yard says</th><th>VIN</th><th>Stock / row</th></tr></thead>
        <tbody>
          {d.samples.map((s) => (
            <tr key={s.id}>
              <td>{s.location}<div className="muted">{s.source}</div></td>
              <td>{s.year ?? "—"}</td>
              <td>{[s.make, s.model, s.trim].filter(Boolean).join(" ")}</td>
              <td className="mono">{s.vin ?? <span className="muted">none</span>}</td>
              <td className="muted">{s.stock}{s.row ? ` · row ${s.row}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
