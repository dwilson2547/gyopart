import { post } from "./api.ts";
import type { AnyPreview, Proposal, Suggestion, SuggestionKind } from "./types.ts";
import { decodeEntities, fmtInt } from "./util.tsx";

/** Save a fix from a panel. Opened from a suggestion (Tweak), it goes through the suggestion's approve instead,
 *  so the review records what was changed; the preview the panel showed must still hold. */
export async function saveFix(url: string, kind: SuggestionKind, body: object, preview: AnyPreview,
                              from?: Suggestion): Promise<{ requeued: number }> {
  if (!from) return post<{ requeued: number }>(url, body);
  const s = await post<Suggestion>(`/api/suggestions/${from.id}/approve`, { kind, proposal: body, preview });
  return { requeued: Number(s.result?.requeued ?? s.result?.updated ?? 0) };
}

/** The suggestion's proposal for a panel of this kind, or nothing (a tweak may switch kind: start blank). */
export function proposalFor(from: Suggestion | undefined, kind: SuggestionKind): Proposal | null {
  return from && from.kind === kind ? from.proposal : null;
}

const yrs = (p: Proposal) => (p.year_from || p.year_to ? `, ${p.year_from ?? "…"}–${p.year_to ?? "…"}` : "");

export function describeProposal(kind: SuggestionKind, p: Proposal): string {
  switch (kind) {
    case "decode_mapping":
      return `${p.make} ${p.model}${p.series ? ` · ${p.series}` : " (any series)"} → ${(p.targets ?? [])
        .map((t) => `${t.make} ${decodeEntities(t.model)}`).join(", ")}${yrs(p)}`;
    case "trim_mapping":
      return `“${p.trim}” ${p.action === "noise" ? "is noise" : `→ ${(p.trims ?? []).map(decodeEntities).join(" / ")}`}`
        + ` for ${p.make} ${p.model ?? "(every model)"}${yrs(p)}`;
    case "yard_rule":
      return `“${[p.raw_make, p.raw_model].filter(Boolean).join(" ")}” at ${p.source ?? "every yard"} → ${p.make}`
        + `${p.model ? ` ${decodeEntities(p.model)}` : " (make only)"}`;
    case "ignore_group":
      return "Ignore the group (never matchable)";
  }
}

export function describePreview(kind: SuggestionKind, p: AnyPreview): string {
  if (kind === "trim_mapping")
    return `${fmtInt(p.vehicles)} cars: ${fmtInt(p.exact)} exact (was ${fmtInt(p.exactBefore)}), ${fmtInt(p.narrower)} narrower, `
      + `${fmtInt(p.unchanged)} unchanged${p.wider ? `, ${fmtInt(p.wider)} WIDER` : ""}`;
  if (kind === "ignore_group") return `${fmtInt(p.vehicles)} cars set aside`;
  return `${fmtInt(p.wouldMatch)} of ${fmtInt(p.vehicles)} cars would match`
    + (p.exact != null ? ` (${fmtInt(p.exact)} exact)` : "");
}

/** Same JSON whatever the key order (Postgres JSONB doesn't keep it). */
export function sameJson(a: unknown, b: unknown): boolean {
  const norm = (v: unknown): unknown => Array.isArray(v) ? v.map(norm)
    : v && typeof v === "object" ? Object.fromEntries(Object.entries(v as object).sort(([x], [y]) => (x < y ? -1 : 1)).map(([k, x]) => [k, norm(x)]))
    : v;
  return JSON.stringify(norm(a)) === JSON.stringify(norm(b));
}
