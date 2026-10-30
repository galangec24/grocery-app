const base: string = import.meta.env.VITE_API_URL || "";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export type Kind = "srp" | "prevailing";

export interface PriceRow {
  id: string;
  source: "dti_srp" | "da_dpi";
  source_label: string;
  kind: Kind;
  group: string;
  category: string;
  commodity: string;
  specification: string;
  unit: string;
  region: string;
  price: number;
  previous_price: number | null;
  change: number | null;
  change_pct: number | null;
  report_date: string;
  source_url: string;
  trend: number[];
}

export interface SourceInfo {
  id: string;
  label: string;
  coverage: string;
  report_date: string | null;
  rows: number;
  source_url: string;
}

export interface MarketSummary {
  sources: SourceInfo[];
  items: number;
  categories: number;
  rising: number;
  falling: number;
  top_rising: PriceRow[];
  top_falling: PriceRow[];
  generated_at: string;
}

export interface Candidate {
  id: string;
  commodity: string;
  specification: string;
  unit: string;
  price: number;
  source_label: string;
  region: string;
}

export interface BasketLine {
  query: string;
  quantity: number;
  status: "matched" | "no_match";
  selected: PriceRow | null;
  line_total: number;
  candidates: Candidate[];
}

export interface BasketResponse {
  lines: BasketLine[];
  total: number;
  items_matched: number;
  items_unmatched: number;
}

export interface CityStore {
  name: string;
  type: "Mall" | "Supermarket";
  latitude: number;
  longitude: number;
  distance_km: number;
}

export interface CityInfo {
  city: string;
  region: string;
  island: "Luzon" | "Visayas" | "Mindanao";
  metro_manila: boolean;
  store_count: number;
  stores_available: boolean;
  stores: CityStore[];
  attribution: string;
}

type Tokens = { access_token: string; refresh_token: string };
const TOKENS = "grocery_admin_tokens";

export const adminSession = {
  get(): Tokens | null {
    const raw = sessionStorage.getItem(TOKENS);
    return raw ? JSON.parse(raw) : null;
  },
  set(tokens: Tokens) {
    sessionStorage.setItem(TOKENS, JSON.stringify(tokens));
  },
  clear() {
    sessionStorage.removeItem(TOKENS);
  },
};

function describe(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error, /, "");
  return `Request failed (${status})`;
}

async function send(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${base}/api/v1${path}`, init);
  } catch {
    throw new ApiError("Can't reach the price server. It may be waking up, so please try again in a minute.", 0);
  }
}

export async function api<T>(path: string, init: RequestInit = {}, authed = false): Promise<T> {
  const withAuth = (): RequestInit => {
    const tokens = adminSession.get();
    return tokens
      ? { ...init, headers: { ...init.headers, Authorization: `Bearer ${tokens.access_token}` } }
      : init;
  };
  let response = await send(path, authed ? withAuth() : init);

  const tokens = adminSession.get();
  if (authed && response.status === 401 && tokens) {
    const renewed = await send("/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refresh_token }),
    });
    if (renewed.ok) {
      adminSession.set({ ...tokens, access_token: (await renewed.json()).access_token });
      response = await send(path, withAuth());
    } else {
      adminSession.clear();
    }
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(describe(body.detail, response.status), response.status);
  }
  return response.json();
}

export const postJson = <T,>(path: string, body: unknown, authed = false) =>
  api<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, authed);

export function query(params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "" && value !== false) search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
