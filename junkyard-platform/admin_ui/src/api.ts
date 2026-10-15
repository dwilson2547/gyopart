// The admin API (admin_api/api). Errors carry FastAPI's detail: a string, {field, message} from our own
// checks, or a list of pydantic validation errors.

export type FieldError = { field: string; message: string };

export class ApiError extends Error {
  status: number;
  field: string | null;
  constructor(status: number, detail: unknown) {
    let msg = `HTTP ${status}`;
    let field: string | null = null;
    if (typeof detail === "string") msg = detail;
    else if (detail && typeof detail === "object" && "message" in detail) {
      msg = String((detail as FieldError).message);
      field = (detail as FieldError).field ?? null;
    } else if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as { msg?: string; loc?: unknown[] };
      msg = (first.msg ?? msg).replace(/^Value error, /, "");
      field = (first.loc ?? []).slice(1).join(".") || null;
    }
    super(msg);
    this.status = status;
    this.field = field;
  }
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const r = await fetch(url, {
    method, headers, credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new ApiError(r.status, (data as { detail?: unknown } | null)?.detail);
  return data as T;
}

export const get = <T>(url: string) => call<T>("GET", url);
export const post = <T>(url: string, body?: unknown) => call<T>("POST", url, body);
export const del = <T>(url: string) => call<T>("DELETE", url);

export function qs(params: Record<string, string | number | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}
