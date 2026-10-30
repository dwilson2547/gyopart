# VIN matching v2 (trims) and the fix-suggestion agent — design

Status: **phases 1–3 in dev** (2026-10-27/28/30, §4); the rest is planned (user, 2026-10-27). Prod waits for the whole
system (user, 2026-10-28). §1 is verified against the code on `dev` (731cd38)
and read-only queries against the **dev** databases on 2026-10-27; the §2.1 numbers come from a throwaway
prototype of the normaliser run over the same data. Prod numbers have not been measured for this.

Two parts, in this order: first the matcher learns to use trims properly (§2), then a local model on the home GPU
**suggests** fixes that the admin approves, tweaks or rejects before anything touches the fleet (§3). The agent comes
second because trims widen what it has to map; it should map against the matcher it will live with.

Follows on from [admin-rewrite-design.md](admin-rewrite-design.md) (decode mappings §2.2, MCP §2.7).

## 1. Where matching stands

### 1.1 What the matcher already uses (`pipeline/car_matcher.py`)

Year + make + model pick the catalogue rows; then three **soft** filters narrow them, each applied only when it
keeps at least one car:

- **Engine**: NHTSA `DisplacementL` (± 0.05 L) and `EngineCylinders` against the catalogue engine name
  (`"2.4L L4 - Gas"`). Already parsed; nothing to add.
- **Fuel**: NHTSA fuel/electrification → gas / flex / diesel / hybrid / electric.
- **Trim**: the catalogue trim must equal NHTSA `Trim` or `Series` exactly (case-insensitive). This is the weak one.

One car left = `vin_exact`; more = `vin_candidates` ("one of these").

### 1.2 Dev, 2026-10-27: the ambiguity is trims

Active, resolved vehicles: 60,000 `vin_exact`; **59,192 `vin_candidates`** (2–3 candidates: 40,979 · 4–10: 18,178 ·
11+: 35); `ymmt_match` 7,644.

What differs between an ambiguous vehicle's candidates:

| Candidates differ by | Vehicles |
|---|---|
| **trim only** | **57,083 (96%)** |
| engine and trim | 1,832 |
| engine only | 243 |
| neither (duplicate catalogue rows) | 34 |

So engine and displacement are already doing their job, and trim is the gap. Of the 59,191 ambiguous vehicles with a
cached decode, 18,346 (31%) have neither `Trim` nor `Series`; for those the decode carries no trim at all.

What NHTSA's trim text looks like next to the catalogue's trims (real examples):

| NHTSA `Trim` / `Series` | Catalogue trims for that car | Shape |
|---|---|---|
| `1LT`, `2LT`, `LT-1LT`, `LT (1LT)` | LS / LT / LTZ | GM grade digits → `LT` |
| `SLT2`, `SLE 2`, `SLT-2 1/2 Ton` | SLE / SLT | grade digit, weight class |
| `EX-V6`, `SEL FWD` | EX / LX · SE / SEL | engine or drive suffix |
| `quattro Premium Plus` | Premium / Premium Plus / Prestige | most specific wins |
| `Standard / Turbo / R-Spec / Rally Edition`, `LX, S, X-Line` | … | **a list of alternatives** |
| `Middle level`, `Lev2 - All models`, `GL` (Kia) | Limited / SE · LS / LT / LTZ | maker-internal grade, needs a mapping |
| `ACV40L/GSV40L/AHV40L`, `ZZE130L`, `1500 (1/2 Ton)`, `Styleside` | … | no trim information |

Yard listings add a little: 1,725 ambiguous vehicles have a trim from the yard and none from NHTSA (mostly
`pull_a_part`). `vehicles.trim` is the yard's value unless the scraper left it empty, in which case the worker filled
it from the decode (`decoded_vehicle_fields`).

## 2. Phase A — trim matching

### 2.1 A trim normaliser in the trim filter (deterministic)

Replaces the exact-string comparison. Only ever narrows, as today.

1. **Tokenise** NHTSA `Trim` (then `Series`) on spaces and hyphens. Bracketed text is read as more of the same
   (`LT (1LT)`).
2. **Grade digits**: `1LT` / `SLT2` / `SLE 2` → `LT` / `SLT` / `SLE`.
3. **Noise tokens** never count against a match: drive (`AWD`, `4x4`, `4Motion`, `quattro`, `xDrive`, `4Matic`),
   engine (`V6`, `2.0T`), body, weight class (`1/2 Ton`), transmission, chassis codes (`ZZE130L`).
4. Within one alternative, the **most specific** catalogue trim whose tokens are all present wins
   (`Premium Plus` over `Premium`, `Royale LS` over `LS`).
5. **Exact only when nothing is left unexplained.** Text split by `/` or `,` is a list of alternatives: it narrows to
   the catalogue trims it names but never chooses one by specificity. Any leftover non-noise word also blocks the
   specificity choice (`LX Premium` must not become `LX` when the catalogue has `LX-P`).
6. **Yard trim** goes through the same steps only when the decode has no trim text. It never overrides the decode.

Prototype over the 59,191 ambiguous dev vehicles (rules 1–5, no yard trims): **8,190 become exact, 7,894 narrow** to
fewer candidates, 18,346 have no trim text, and 24,761 have text that doesn't help. The first version of the
prototype, without rule 5, made 14,780 exact, but a spot check showed the list cases above choosing wrong. The
shipped version is table-driven-tested from real decodes, and a reviewed random sample of new exacts comes before
the prod re-match.

After it ships: requeue every `vin_candidates` vehicle (decodes are cached, so it costs catalogue queries only).

### 2.2 Trim mappings (the mappable part)

For maker-internal grades the decode can't name by itself. Table `trim_mappings`:

- `make_key`, `model_key` (nullable = every model of the make), `trim_key` (the normalised NHTSA string),
  `year_from` / `year_to` (nullable = open-ended)
- `action`: `map` → `catalogue_trims` (one or more catalogue trim names, picked from the catalogue, never typed), or
  `noise` → the string carries no trim and stops being shown
- `created_by`, `created_at`, like `decode_mappings`

They apply in the trim filter before the normaliser. Same rules as decode mappings: preview first, create requeues
the affected vehicles, delete works only on mappings agents made, and targets must exist in the catalogue.

Size of the job (dev, after the §2.1 prototype): 7,053 vehicles' trim text is pure noise by rule 3. **838 distinct
(make, NHTSA trim) strings** cover the remaining 16,501 vehicles; the top 300 strings cover 14,891 of them. Many of
the top strings are noise the rules don't know yet (`Styleside`, `Econoline`, Hyundai `NFA` / `HD`). A `noise` mapping
settles each of those once.

### 2.3 Admin surfaces

- A **Trims** tab on the discrepancies page: groups by (make, model, NHTSA trim, year range) where the trim text
  didn't narrow, most vehicles first, with the candidate catalogue trims and their year coverage. Pick targets or
  mark noise → preview → confirm, as for decode mappings.
- **MCP**: trim groups, `preview_trim_mapping`, `create_trim_mapping`, deletable when agent-made, same as decode
  mappings.
- A vehicle's page shows which filters narrowed it (`CarMatch.narrowed_by`, not stored today) so a wrong exact can
  be traced to its rule or mapping.

Engine and displacement get no new work: §1.2 leaves 2,075 vehicles where the engine is part of the ambiguity, and
the existing engine filter already covers it.

## 3. Phase B — the fix-suggestion agent

### 3.1 Runs on a local model; nothing is trained

The agent is a small open-weights instruct model on the home GPU, queued through the cluster's GPU scheduler service.
No hosted LLM API is in the loop, which keeps it cost-free and keeps unattended automation off any hosted model. No
model is fine-tuned. The "skill" is a versioned prompt (like the photo-tag prompts in the GPU scheduler), and every
suggestion records the prompt version and checkpoint that produced it. Interactive MCP sessions stay as they are.

### 3.2 Suggestions, not fixes

Nothing the agent produces writes a mapping or requeues a vehicle. It writes a suggestion. Table `fix_suggestions`:

- `kind`: `decode_mapping` | `trim_mapping` | `yard_rule` | `ignore_group`
- the group it is for, the proposal (exactly the arguments the create function takes), the preview it ran
  (vehicles affected / would match / exact), a short rationale, `model`, `prompt`
- `status`: `pending` → `approved` | `edited` | `rejected` | `stale`; `reviewed_by`, `reviewed_at`,
  `reject_reason`, and the id of the mapping created from it

A suggestion goes `stale` when its group's vehicles change or someone fixes the group another way. A rejected
(group, proposal) pair is never suggested again.

### 3.3 Review

A **Suggestions** page in the admin SPA, one card per suggestion: the group, the proposal, the rationale, and a
**preview re-run live** when the card opens (the snapshot can be days old).

- **Approve**: creates the mapping through the same function as a manual fix. If the live preview differs from the
  snapshot, the card shows the difference and asks again.
- **Tweak**: opens the normal create form pre-filled; whatever is confirmed is recorded as `edited`, with the
  final values kept next to the proposal.
- **Reject**: optional reason.

The created mapping's `created_by` reads `agent-suggested:<model> (approved by <user>)`. Approval is human-only
through the UI. MCP clients may read suggestions, and may file them, so an interactive session can propose instead
of create.

### 3.4 How a run works: one model call per group

The GPU scheduler drains batches and swaps models, so a multi-turn tool loop fits it badly. Each group is instead one
job:

1. **Gather (code)**: the group, catalogue year coverage, sample decodes (trim, engine, body, drive), existing
   mappings for the make, rejected proposals for the group.
2. **Candidates (code)**: the similarity-ranked catalogue models or trims already offered in the UI, each with its
   preview already run.
3. **Decide (model)**: one call with the bundle and the prompt; it returns JSON: pick candidates (with series/year
   narrowing), mark noise / ignore, or `unsure` with a reason.
4. **Check (code)**, before anything is stored: targets must come from the bundle's candidate list (the model can't
   invent a name); the preview must match vehicles and change nothing outside the group; a gap group never gets a
   mapping to a model just because it exists in other years. A failed check or `unsure` stores no suggestion and
   shows the reason on the group instead.

Runs: a nightly job (like `catalogue-gap-recheck`) over open groups that have no pending or rejected suggestion,
plus a run-now button. Order: decode groups (`model_not_in_catalogue`, `make_not_in_catalogue`), then trim strings,
then yard rules.

### 3.5 Which model, and how to tell it's good enough

The GPU scheduler's current Qwen3-VL-4B adapter takes images only, so this needs a text adapter there first. Bake-off
candidates: Qwen3-VL-4B used text-only (already on the GPU, no swap) against a text instruct model of about 8B,
quantised to fit beside the others on the 12 GB card. ⚠ Neither has been tried on this task.

Labels for the bake-off are the user's own fixes: prod's `decode_mappings` and yard rules made by the user (count not
measured), replayed as groups with those mappings hidden. After launch, the approve / edited / rejected history is the
running score, per kind and prompt version. The agreement needed before the nightly run is switched on is the user's
call after the bake-off.

## 4. Phases

1. **Trim normaliser** (§2.1) + table-driven tests from real decodes, reviewed sample, re-match of `vin_candidates`.
   Dev, then prod. **In dev 2026-10-27** (gyopart 3fb7021; admin-api and vin-resolver `sha-3fb7021f7cd5` in
   `values-dev.yaml`): `pipeline/trim_match.py`, 38 cases from real decodes in `tests/test_trim_match.py`. Two rules
   beyond §2.1 came out of the review: a list narrows only when *every* member is a catalogue trim (`Sport, SXT`
   without an SXT says nothing), and dropped option text blocks a trim that has a longer sibling (`EX with leather` vs
   EX / EX-L). A 40-vehicle sample of new exacts read right after that. Dev re-match of every `vin_candidates`
   vehicle: `vin_exact` 60,000 → 69,352, `vin_candidates` 59,192 → 49,840, total matched unchanged (126,836). Prod not
   shipped.
2. **Trim mappings** (§2.2) + Trims tab + MCP tools + `narrowed_by` on the vehicle page (§2.3). **In dev 2026-10-28**
   (gyopart c6a7bb7; images `sha-c6a7bb79b120`; dev DB at migration 0007, applied by hand). Built differently from
   §2.3 in one respect: ambiguous matches have no discrepancy rows, so the worker records on each vehicle which
   steps narrowed it (`car_id_match_steps`: engine, fuel, trim, trim_mapping, trim_noise) and the trim text it
   couldn't read while the candidates' trims still differ (`car_id_trim_unread`); the Trims tab groups by
   (decode make, model, that text). Noise-only text is recorded as `trim_noise` and never listed. A trim mapping
   for a text beats the normaliser; one for the decode's model beats a make-wide one; duplicates are refused
   (edit = delete + create). Preview counts the covered VIN-matched vehicles that end exact / narrower /
   unchanged / wider. Dev after the re-match: 21,699 vehicles over 1,634 groups (1,223 distinct texts); 9,616
   vehicles' text recorded as noise. Verified against dev: list 0.23 s, previews 0.1–1.1 s, a noise and a map
   round trip (create → worker re-match → delete) left no mappings behind. MCP: `preview_trim_mapping`,
   `create_trim_mapping`, `delete_trim_mapping` (agent-made only), `list_trim_mappings`; the group tools take
   `kind: "trim"` keys.
3. **Suggestions table and review page** (§3.2–3.3), first fed by MCP sessions only. **In dev 2026-10-30** (gyopart
   e5393de; images `sha-e5393debac7c`; dev DB at migration 0008, applied by hand). `admin_api/api/suggestions.py`,
   page `/suggestions` (Waiting / Approved / Rejected / Stale), MCP `suggest_fix` and `list_suggestions`; no approve
   on the MCP. As built, beyond §3.2–3.3:
   - Filing refuses a proposal that isn't for its group (decode, trim text or yard strings must be the key's;
     `ignore_group` only for decode and yard groups), a group that already has one waiting, a fix rejected for that
     group before (matched on a hash of kind + group + normalised proposal), and a preview that would do nothing:
     no open vehicles, no matches (decode / yard), or any `wider` (trim).
   - Stale = the group has no open vehicles left; checked whenever suggestions are listed or a card's live preview
     runs. A group that only changed shows up as the live preview differing from the filed one: Approve then asks
     again, and the server refuses an approve whose preview no longer holds.
   - Tweak opens the group's own fix form (MapPanel, TrimPanel, RulePanel) filled from the proposal and saves
     through the suggestion's approve; `edited` keeps the final kind, proposal and preview in `final`. The created
     fix's `created_by` reads `agent-suggested:<model> (approved by <user>)`, or `(edited by <user>)`; not the MCP's
     `agent:` prefix, so agent delete tools can't remove it.
   - The group panel on the discrepancies page links to a waiting suggestion; the nav shows how many wait.
   Verified against dev with a script in the admin pod: filed → duplicate refused → live preview equal → approve with
   altered numbers refused → approved (173 Sonatas exact via the worker) → mapping removed (all 173 back); an edited
   approval; reject, then the same fix refused; a stale one after settling its group directly. Verification rows and
   mappings deleted; Trims tab back to 21,699 / 1,634. The SPA was type-checked and built, not clicked through.
4. **Text adapter + bake-off** in the GPU scheduler (§3.5).
5. **Suggester job** (§3.4) in dev, then prod, decode groups first.
