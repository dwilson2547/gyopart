import { useEffect, useState } from "react";
import { ApiError, get, post, qs } from "./api.ts";
import type { AnyPreview, GroupDetail, GroupKey, Suggestion, SuggesterStatus, SuggestionList, SuggestionView } from "./types.ts";
import { KIND_LABEL } from "./types.ts";
import { MapPanel } from "./MapPanel.tsx";
import { RulePanel } from "./RulePanel.tsx";
import { TrimPanel } from "./TrimPanel.tsx";
import { Link, navigate, useLocation } from "./router.tsx";
import { describePreview, describeProposal, sameJson } from "./suggestions.ts";
import { Empty, ErrorBanner, Loading, keyLabel, useLoad, useToast } from "./util.tsx";

const VIEWS: { id: SuggestionView; label: string; help: string }[] = [
  { id: "pending", label: "Waiting", help: "Fixes proposed by an agent. Nothing changes for any car until you approve one." },
  { id: "reviewed", label: "Approved", help: "Approved as proposed, or after you changed them (edited)." },
  { id: "rejected", label: "Rejected", help: "The same fix is never proposed again for that group." },
  { id: "stale", label: "Stale", help: "The group emptied before review: fixed or settled some other way." },
];

const groupLink = (k: GroupKey) =>
  `/${qs({ tab: k.kind === "trim" ? "trims" : k.kind === "yard" ? "nodecode" : null, g: JSON.stringify(k) })}`;
const when = (iso: string | null) => (iso ? new Date(iso + "Z").toLocaleString() : "—");

/** Review fix suggestions (matching-v2-design §3.3): approve, tweak or reject, one card at a time. */
export function SuggestionsPage() {
  const loc = useLocation();
  const p = new URLSearchParams(loc.search);
  const view = (p.get("view") as SuggestionView) || "pending";
  const open = Number(p.get("id")) || null;
  const list = useLoad(() => get<SuggestionList>(`/api/suggestions${qs({ view })}`), view);
  const go = (next: { view?: SuggestionView; id?: number | null }) =>
    navigate(`/suggestions${qs({ view: (next.view ?? view) === "pending" ? null : next.view ?? view,
                                 id: next.id === undefined ? open : next.id })}`);
  const rows = list.data?.suggestions ?? [];
  const info = VIEWS.find((v) => v.id === view)!;

  /** A card was approved or rejected: drop it and open the next one. */
  const done = (s: Suggestion) => {
    const i = rows.findIndex((r) => r.id === s.id);
    const rest = rows.filter((r) => r.id !== s.id);
    list.setData({ ...list.data!, suggestions: rest });
    list.reload();   // counts
    go({ id: rest[Math.min(Math.max(i, 0), rest.length - 1)]?.id ?? null });
  };

  return (
    <div className="stack">
      <SuggesterStrip onRan={list.reload} />
      <div className="tabs" role="tablist">
        {VIEWS.map((v) => (
          <button key={v.id} role="tab" aria-selected={v.id === view} className={v.id === view ? "tab on" : "tab"}
                  onClick={() => go({ view: v.id, id: null })}>
            {v.label}<span className="count">{list.data ? list.data.counts[v.id] : "…"}</span>
          </button>
        ))}
      </div>
      <p className="muted" style={{ margin: 0 }}>{info.help}</p>
      {list.error && <ErrorBanner error={`Suggestions didn't load: ${list.error}`} onRetry={list.reload} />}
      {list.data == null ? (list.error ? null : <Loading />) : rows.length === 0 ? (
        <Empty>{view === "pending" ? "No suggestions waiting. An MCP session can file them with suggest_fix." : "None."}</Empty>
      ) : (
        <div className="stack">
          {rows.map((s) => (
            <Card key={s.id} s={s} open={s.id === open} onToggle={() => go({ id: s.id === open ? null : s.id })}
                  onDone={done} />
          ))}
        </div>
      )}
    </div>
  );
}

/** The suggester's last run and Run now. Runs take a few minutes; the strip refreshes while one is going. */
function SuggesterStrip({ onRan }: { onRan: () => void }) {
  const toast = useToast();
  const st = useLoad(() => get<SuggesterStatus>("/api/suggester"), "suggester");
  const [busy, setBusy] = useState(false);
  const running = st.data?.running ?? false;
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => { st.reload(); onRan(); }, 15000);
    return () => window.clearInterval(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);
  if (st.error) return <ErrorBanner error={`Suggester status didn't load: ${st.error}`} onRetry={st.reload} />;
  if (!st.data) return null;
  const last = st.data.runs[0];
  const counts = last ? Object.entries(last.counts).map(([k, n]) => `${n} ${k}`).join(", ") : "";
  const runNow = async () => {
    setBusy(true);
    try { await post("/api/suggester/run"); toast("Suggester started; new suggestions appear here as it files them."); st.reload(); }
    catch (e) { toast(e instanceof Error ? e.message : String(e), true); }
    finally { setBusy(false); }
  };
  return (
    <div className="row small muted">
      <span className="grow">
        Suggester{st.data.schedule ? ` (cron ${st.data.schedule})` : ""}:{" "}
        {running ? <strong>running…</strong> : last
          ? <>last run {when(last.startedAt)} ({last.trigger}), {last.status}{counts ? `: ${counts}` : ""}{last.error ? ` · ${last.error}` : ""}</>
          : "no runs yet"}
      </span>
      <button disabled={busy || running || !st.data.runNow} onClick={runNow} title={st.data.reason ?? ""}>
        {busy ? "Starting…" : "Run now"}
      </button>
    </div>
  );
}

function Card({ s, open, onToggle, onDone }: {
  s: Suggestion; open: boolean; onToggle: () => void; onDone: (s: Suggestion) => void;
}) {
  return (
    <section className={`panel stack sugg${open ? " open" : ""}`} aria-label={`Suggestion ${s.id}`}>
      <div className="row" role="button" tabIndex={0} onClick={onToggle} style={{ cursor: "pointer" }}
           onKeyDown={(e) => { if (e.key === "Enter") onToggle(); }} aria-expanded={open}>
        <span className="tag">{KIND_LABEL[s.kind]}</span>
        <strong className="grow">{keyLabel(s.key)}{s.key.kind === "yard" ? ` · ${s.key.source}` : ""}</strong>
        {s.status === "edited" && <span className="tag">edited</span>}
        <span className="muted small">{s.model} · {when(s.filedAt)}</span>
      </div>
      <div>{describeProposal(s.kind, s.proposal)}</div>
      {s.rationale && <div className="muted small rationale">{s.rationale}</div>}
      <div className="small muted">When filed: {describePreview(s.kind, s.preview)}</div>
      {s.status === "pending" ? (open && <Review s={s} onDone={onDone} />) : <Outcome s={s} />}
    </section>
  );
}

function Outcome({ s }: { s: Suggestion }) {
  return (
    <div className="small stack" style={{ gap: 4 }}>
      <div>
        <strong>{s.status}</strong>{s.reviewedBy ? ` by ${s.reviewedBy}` : ""} · {when(s.reviewedAt)}
        {s.rejectReason && <> · “{s.rejectReason}”</>}
      </div>
      {s.final && <div>Saved instead: {describeProposal(s.final.kind, s.final.proposal)} ({describePreview(s.final.kind, s.final.preview)})</div>}
      <Link to={groupLink(s.key)} className="small">open the group</Link>
    </div>
  );
}

/** A pending card, open: today's preview, then approve / tweak / reject. */
function Review({ s, onDone }: { s: Suggestion; onDone: (s: Suggestion) => void }) {
  const toast = useToast();
  const live = useLoad(() => post<AnyPreview>(`/api/suggestions/${s.id}/preview`), String(s.id));
  const [mode, setMode] = useState<"idle" | "confirm-changed" | "tweak" | "reject">("idle");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setMode("idle"); setError(null); }, [s.id]);

  const changed = live.data != null && !sameJson(live.data, s.preview);
  const fail = (e: unknown) => { setError(e instanceof Error ? e.message : String(e)); setBusy(false); };

  const approve = async () => {
    if (changed && mode !== "confirm-changed") return setMode("confirm-changed");
    setBusy(true); setError(null);
    try {
      const r = await post<Suggestion>(`/api/suggestions/${s.id}/approve`, { preview: live.data });
      toast(`Approved: ${describeProposal(s.kind, s.proposal)}. Cars re-matching.`);
      onDone(r);
    } catch (e) {
      if (e instanceof ApiError && e.field === "preview") { live.reload(); setMode("idle"); }
      fail(e);
    }
  };
  const reject = async () => {
    setBusy(true); setError(null);
    try {
      const r = await post<Suggestion>(`/api/suggestions/${s.id}/reject`, { reason: reason.trim() || null });
      toast(`Rejected suggestion for ${keyLabel(s.key)}.`);
      onDone(r);
    } catch (e) { fail(e); }
  };

  if (live.error) {
    return <ErrorBanner error={live.error.includes("stale") ? `${live.error}. Reload to move it to Stale.` : `Preview didn't run: ${live.error}`}
                        onRetry={live.reload} />;
  }
  return (
    <div className="stack">
      {live.data == null ? <Loading what="running the preview on today's data…" /> : (
        <div className={`preview${changed ? " none" : ""}`} role="status">
          <strong>Now: {describePreview(s.kind, live.data)}</strong>
          {changed ? <div className="small">The numbers changed since it was filed (cars arrived, left, or were fixed another way).</div>
                   : <div className="small muted">Same as when it was filed.</div>}
          {s.kind === "trim_mapping" && (live.data.wider ?? 0) > 0 && (
            <div className="field-error">{live.data.wider} cars would get more candidates: it overrides a reading that worked.</div>)}
        </div>
      )}

      {mode === "tweak" ? <Tweak s={s} onDone={onDone} onCancel={() => setMode("idle")} /> : mode === "reject" ? (
        <div className="stack" style={{ gap: 6 }}>
          <label className="fieldlabel" htmlFor={`reason-${s.id}`}>Why not? <span className="muted">(optional; it's kept with the suggestion so later ones can learn from it)</span></label>
          <textarea id={`reason-${s.id}`} rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
          <div className="row">
            <button className="danger" disabled={busy} onClick={reject}>{busy ? "Rejecting…" : "Reject"}</button>
            <button disabled={busy} onClick={() => setMode("idle")}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="row">
          {mode === "confirm-changed" && <span>Approve with today's numbers?</span>}
          <button className="primary" disabled={busy || live.data == null} onClick={approve}>
            {busy ? "Approving…" : mode === "confirm-changed" ? "Yes, approve" : "Approve"}
          </button>
          {mode === "confirm-changed" && <button disabled={busy} onClick={() => setMode("idle")}>Cancel</button>}
          {mode === "idle" && <>
            <button disabled={busy} onClick={() => setMode("tweak")}>Tweak…</button>
            <button disabled={busy} onClick={() => setMode("reject")}>Reject…</button>
            <Link to={groupLink(s.key)} className="small">open the group</Link>
          </>}
        </div>
      )}
      {error && <div className="field-error" role="alert">{error}</div>}
    </div>
  );
}

/** The group's own fix form, filled in from the suggestion; confirming approves it as edited if anything changed. */
function Tweak({ s, onDone, onCancel }: { s: Suggestion; onDone: (s: Suggestion) => void; onCancel: () => void }) {
  const toast = useToast();
  const detail = useLoad(() => post<GroupDetail>("/api/discrepancies/group", { key: s.key, status: "open" }), String(s.id));
  if (detail.error) return <ErrorBanner error={detail.error} onRetry={detail.reload} />;
  if (detail.data == null) return <Loading what="loading the group…" />;
  const resolved = (_: GroupKey, message: string) => {
    toast(message);
    onDone({ ...s, status: "approved" });
  };
  const d = detail.data;
  return (
    <div className="stack">
      {s.key.kind === "decode" && <MapPanel d={d} onResolved={resolved} from={s} />}
      {s.key.kind === "trim" && <TrimPanel d={d} onResolved={resolved} from={s} />}
      {s.key.kind === "yard" && <RulePanel d={d} onResolved={resolved} from={s} />}
      <div><button onClick={onCancel}>Back</button></div>
    </div>
  );
}
