import { useMemo } from "react";
import { get, qs } from "./api.ts";
import type { Group, GroupKey, GroupPage, Summary, Tab, Yard } from "./types.ts";
import { REASON_LABEL } from "./types.ts";
import { navigate, useLocation } from "./router.tsx";
import { Combobox } from "./Combobox.tsx";
import { GroupPanel } from "./GroupPanel.tsx";
import { Empty, ErrorBanner, Loading, fmtInt, keyLabel, useLoad, useToast, years } from "./util.tsx";

const TABS: { id: Tab; label: string; help: string }[] = [
  { id: "fixable", label: "Fixable", help: "NHTSA's name isn't the catalogue's: map it." },
  { id: "gaps", label: "Catalogue gaps", help: "The catalogue doesn't cover these years yet. Shows yard trends." },
  { id: "nodecode", label: "No decode", help: "No usable VIN decode: fix with a yard rule on the yard's own strings." },
  { id: "ignored", label: "Ignored", help: "Groups you set aside." },
];

const EMPTY: Record<Tab, string> = {
  fixable: "Nothing to fix here: every decode name matches the catalogue.",
  gaps: "No catalogue gaps.",
  nodecode: "Every unmatched vehicle has a usable VIN decode.",
  ignored: "Nothing ignored.",
};

const sameKey = (a: GroupKey, b: GroupKey) => JSON.stringify(a) === JSON.stringify(b);

function useParams() {
  const loc = useLocation();
  const p = new URLSearchParams(loc.search);
  const g = p.get("g");
  let key: GroupKey | null = null;
  try { key = g ? (JSON.parse(g) as GroupKey) : null; } catch { key = null; }
  return {
    tab: (p.get("tab") as Tab) || "fixable", yard: p.get("yard") || "", q: p.get("q") || "",
    page: Number(p.get("page") || 1), key,
  };
}

function setParams(next: Record<string, string | number | null>, current: URLSearchParams) {
  const p = new URLSearchParams(current);
  for (const [k, v] of Object.entries(next)) {
    if (v === null || v === "" || (k === "page" && v === 1)) p.delete(k); else p.set(k, String(v));
  }
  const s = p.toString();
  navigate(s ? `/?${s}` : "/");
}

export function DiscrepanciesPage() {
  const loc = useLocation();
  const cur = new URLSearchParams(loc.search);
  const { tab, yard, q, page, key } = useParams();
  const toast = useToast();
  const set = (next: Record<string, string | number | null>) => setParams(next, cur);

  const summary = useLoad(() => get<Summary>(`/api/discrepancies/summary${qs({ yard, q })}`), `${yard}|${q}`);
  const list = useLoad(() => get<GroupPage>(`/api/discrepancies/groups${qs({ tab, yard, q, page })}`),
                       `${tab}|${yard}|${q}|${page}`);
  const yards = useLoad(() => get<Yard[]>("/api/yards"), "yards");
  const yardOptions = useMemo(() => (yards.data ?? []).map((y) => ({
    value: y.source, label: y.source, hint: `${fmtInt(y.unmatched)} unmatched`,
  })), [yards.data]);

  const groups = list.data?.groups ?? [];
  const status = tab === "ignored" ? "ignored" : "open";

  /** A fix or ignore took the group out of this tab: drop it now, refresh counts, open the next one. */
  const onResolved = (done: GroupKey, message: string) => {
    toast(message);
    const i = groups.findIndex((g) => sameKey(g.key, done));
    const rest = groups.filter((g) => !sameKey(g.key, done));
    list.setData(list.data ? { ...list.data, groups: rest, total: list.data.total - 1 } : list.data);
    summary.reload();
    window.setTimeout(summary.reload, 6000); // the worker re-matches within seconds; counts follow
    const next = rest[Math.min(Math.max(i, 0), rest.length - 1)];
    set({ g: next ? JSON.stringify(next.key) : null });
  };

  const tabInfo = TABS.find((t) => t.id === tab)!;
  return (
    <div className="stack">
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={t.id === tab} className={t.id === tab ? "tab on" : "tab"}
                  onClick={() => set({ tab: t.id, page: 1, g: null })}>
            {t.label}
            <span className="count">
              {summary.data ? `${fmtInt(summary.data[t.id].groups)} · ${fmtInt(summary.data[t.id].vehicles)} cars` : "…"}
            </span>
          </button>
        ))}
      </div>
      <p className="muted" style={{ margin: 0 }}>{tabInfo.help}</p>

      <div className="filters">
        <div style={{ width: 260 }}>
          <Combobox label="Filter by yard" placeholder="All yards" options={yardOptions} value={yard || null}
                    onChange={(v) => set({ yard: v, page: 1, g: null })} />
        </div>
        <input type="text" aria-label="Search make, model or series" placeholder="Search make / model / series"
               defaultValue={q} key={q}
               onKeyDown={(e) => { if (e.key === "Enter") set({ q: (e.target as HTMLInputElement).value.trim(), page: 1, g: null }); }} />
        {(yard || q) && <button onClick={() => set({ yard: null, q: null, page: 1, g: null })}>Clear filters</button>}
      </div>

      {summary.error && <ErrorBanner error={`Counts didn't load: ${summary.error}`} onRetry={summary.reload} />}

      <div className="split">
        <section className="panel list-pane" aria-label="Groups">
          {list.error && <ErrorBanner error={`Groups didn't load: ${list.error}`} onRetry={list.reload} />}
          {list.data == null ? (list.error ? null : <Loading />) : groups.length === 0 ? (
            <Empty>
              {yard || q ? <>No groups match these filters. <button className="link" onClick={() => set({ yard: null, q: null, page: 1 })}>Clear filters</button></> : EMPTY[tab]}
            </Empty>
          ) : (
            <>
              <table className="list">
                <thead><tr><th>{tab === "nodecode" ? "Yard says" : "NHTSA decode"}</th><th>Years</th><th className="num">Cars</th><th className="num">Yards</th></tr></thead>
                <tbody>
                  {groups.map((g) => <GroupRow key={JSON.stringify(g.key)} g={g} selected={key != null && sameKey(key, g.key)}
                                               onSelect={() => set({ g: JSON.stringify(g.key) })} />)}
                </tbody>
              </table>
              <div className="row pager">
                <span className="muted grow">{fmtInt(list.data.total)} groups{list.loading ? " · refreshing…" : ""}</span>
                <button disabled={page <= 1} onClick={() => set({ page: page - 1 })}>← Prev</button>
                <span className="muted">page {list.data.page} of {list.data.pages}</span>
                <button disabled={page >= list.data.pages} onClick={() => set({ page: page + 1 })}>Next →</button>
              </div>
            </>
          )}
        </section>

        <section className="panel detail-pane" aria-label="Group detail">
          {key ? <GroupPanel key={JSON.stringify(key) + status} groupKey={key} status={status} tab={tab} yard={yard}
                             onResolved={onResolved} />
               : <Empty>Pick a group on the left. The biggest ones are at the top.</Empty>}
        </section>
      </div>
    </div>
  );
}

function GroupRow({ g, selected, onSelect }: { g: Group; selected: boolean; onSelect: () => void }) {
  return (
    <tr className={selected ? "selected" : ""} onClick={onSelect} tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter") onSelect(); }} aria-selected={selected}>
      <td>
        <div className="gname">{g.key.kind === "yard" && <span className="tag">{g.key.source}</span>} {keyLabel(g.key)}</div>
        <div className="muted small">{g.reasons.map((r) => REASON_LABEL[r] ?? r).join(" · ")}</div>
      </td>
      <td className="muted nowrap">{years(g.yearMin, g.yearMax)}</td>
      <td className="num">{fmtInt(g.vehicles)}</td>
      <td className="num muted" title={g.yards.join(", ")}>{g.yards.length}</td>
    </tr>
  );
}
