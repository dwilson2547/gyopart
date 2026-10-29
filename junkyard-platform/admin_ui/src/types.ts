// API shapes, one-to-one with admin_api/api/*.py.

export type Tab = "fixable" | "gaps" | "nodecode" | "trims" | "ignored";

export type GroupKey = {
  kind: "decode" | "yard" | "trim";
  make: string | null; model: string | null; series: string | null; source: string | null;
  trim?: string | null; // trim groups: the trim text the matcher couldn't read
};

export type Group = {
  key: GroupKey; reasons: string[]; vehicles: number; yearMin: number | null; yearMax: number | null; yards: string[];
};

export type GroupPage = { groups: Group[]; total: number; page: number; pages: number };
export type Summary = Record<Tab, { groups: number; vehicles: number }>;

export type Count = { value: string | number | null; vehicles: number };
export type Sample = {
  id: number; vin: string | null; source: string; stock: string; year: number | null; make: string | null;
  model: string | null; trim: string | null; row: string | null; arrived: string | null; location: string;
  reason: string; series?: string | null;
};
export type ModelOption = { name: string; years: number[]; yearsInRange: number; score?: number };
export type MakeOption = { name: string; yearMin: number; yearMax: number };
export type ExistingMapping = {
  id: number; series: string | null; yearFrom: number | null; yearTo: number | null; make: string; model: string;
};

export type GroupDetail = {
  key: GroupKey; status: "open" | "ignored"; vehicles: number; yearMin: number | null; yearMax: number | null;
  byReason: Count[]; byYard: Count[]; byYear: Count[]; samples: Sample[];
  catalogueMake: string | null;
  // decode groups
  makeYears?: MakeOption | null; suggestions?: ModelOption[]; mappings?: ExistingMapping[];
  catalogueYears?: number[]; modelYears?: number[];
  // yard groups
  makeSuggestions?: { name: string; score: number }[]; modelSuggestions?: ModelOption[];
  modelSuggestionsMake?: string | null;
  // trim groups
  candidateTrims?: CandidateTrim[]; trimMappings?: TrimMappingRow[];
};

// ── matching v2: trims ────────────────────────────────────────────────────────────────────────

export type CandidateTrim = { name: string; vehicles: number; models: string[]; years: number[] };
export type TrimPreview = {
  vehicles: number; exact: number; exactBefore: number; narrower: number; unchanged: number; wider: number;
};
export type TrimMappingRow = {
  id: number; nhtsaMake: string; nhtsaModel: string | null; trim: string; yearFrom: number | null;
  yearTo: number | null; action: "map" | "noise"; trims: string[]; createdBy: string; createdAt: string;
  vehicles?: number;
};

export type Preview = { vehicles: number; wouldMatch: number; exact?: number; unmatched: Record<string, number> };
export type Yard = { source: string; vehicles: number; unmatched: number };

export type MappingRow = {
  id: number; nhtsaMake: string; nhtsaModel: string; nhtsaSeries: string | null; yearFrom: number | null;
  yearTo: number | null; make: string; model: string; createdBy: string; createdAt: string; vehicles: number;
  matched: number;
};
export type RuleRow = {
  id: number; scope: string; source: string | null; field: string; ruleType: string; raw: string; canonical: string;
  makeContext: string | null; appliedCount: number; createdBy: string; createdAt: string;
};

export const REASON_LABEL: Record<string, string> = {
  model_not_in_catalogue: "model name not in catalogue",
  make_not_in_catalogue: "make not in catalogue",
  year_not_in_catalogue: "year not in catalogue",
  model_year_gap: "model not in catalogue that year",
  no_vin: "no VIN",
  decode_failed: "VIN didn't decode",
  trim_unread: "trim text not understood",
};

// ── phase 3: vehicles ─────────────────────────────────────────────────────────────────────────

export type VehicleHit = {
  id: number; source: string; stock: string; location: string | null; year: number | null; make: string | null;
  model: string | null; trim: string | null; vin: string | null; matched: boolean; active: boolean;
};
export type CatCar = { id: number; year?: string; make?: string; model?: string; trim?: string | null;
  engine?: string | null; missing?: boolean };
export type VehicleDetail = VehicleHit & {
  yard: Record<string, string | number>;
  extras: Record<string, unknown>;
  match: { resolved: boolean; method: string | null; confidence: number | null; carId: number | null;
    attemptedAt: string | null; candidates: CatCar[]; candidateCount: number;
    steps: string[]; trimUnread: string | null };
  discrepancy: { reason: string | null; status: string; nhtsaYear: string | null; nhtsaMake: string | null;
    nhtsaModel: string | null; nhtsaSeries: string | null } | null;
  decode: { error: string | null; fetchedAt: string; raw: Record<string, string | null> } | null;
};
export type ScrapeJobInfo = {
  available: boolean; reason?: string; source: string;
  job?: { name: string; namespace: string; phase: string; suspended: boolean; running: boolean;
    lastRun: { result: string; reason: string | null; items: number | null; finishedAt: string | null; trigger: string } | null;
    lastSuccessAt: string | null; nextRunAt: string | null; runNowRequested: boolean };
};

export const STEP_LABEL: Record<string, string> = {
  engine: "engine", fuel: "fuel", trim: "trim (read from the decode)", trim_mapping: "trim (trim mapping)",
  trim_noise: "trim text is noise",
};

export const METHOD_LABEL: Record<string, string> = {
  vin_exact: "VIN decode → exactly one car", vin_candidates: "VIN decode → several possible cars",
  ymmt_match: "yard make/model (fuzzy)", rule_applied: "yard rule + make/model", manual: "picked by hand",
};
