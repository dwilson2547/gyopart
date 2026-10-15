// API shapes, one-to-one with admin_api/api/*.py.

export type Tab = "fixable" | "gaps" | "nodecode" | "ignored";

export type GroupKey = {
  kind: "decode" | "yard";
  make: string | null; model: string | null; series: string | null; source: string | null;
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
  reason: string;
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
};
