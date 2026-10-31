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

export interface CatalogItem {
  id: string;
  name: string;
  brand: string;
  category: string;
  size: string;
  variant: string;
  barcode: string | null;
  image_url: string | null;
  source: string;
  keywords: string;
  auto_price: { price: number; kind: string; label: string } | null;
}

export interface BasketLine {
  query: string;
  quantity: number;
  status: "matched" | "custom" | "reported" | "estimated" | "needs_price" | "no_match";
  report: { store_name?: string; city?: string; price: number; reported_at?: string; origin: string; elsewhere?: boolean } | null;
  label: string;
  selected: PriceRow | null;
  unit_price: number;
  line_total: number;
  candidates: Candidate[];
}

export interface BasketResponse {
  lines: BasketLine[];
  total: number;
  items_matched: number;
  items_need_price: number;
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

export interface Suggestion {
  id: string;
  kind: "official" | "product";
  name: string;
  size: string;
  category: string;
  image_url: string | null;
  price: number | null;
  unit: string | null;
  price_label: string | null;
  price_id: string | null;
}

export interface LiveState {
  version: number;
  updated_at: string | null;
  checked_at: string | null;
}

export interface PricePoint {
  date: string;
  price: number;
  store: string;
  origin: string;
}

export interface StoreOffer {
  store_name: string;
  latitude: number;
  longitude: number;
  total: number;
  items_found: number;
  distance_km: number | null;
  lines: { query: string; item_name: string; price: number; reported_at: string }[];
}

export interface BestStores {
  best: StoreOffer | null;
  stores: StoreOffer[];
  items_total: number;
  items_priced: number;
}

export interface Route {
  path: number[][];
  distance_km: number;
  duration_min: number | null;
  road: boolean;
}

type Tokens = { access_token: string; refresh_token: string };

function tokenStore(storage: Storage, key: string) {
  return {
    get(): Tokens | null {
      const raw = storage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    },
    set(tokens: Tokens) {
      storage.setItem(key, JSON.stringify({ access_token: tokens.access_token, refresh_token: tokens.refresh_token }));
    },
    clear() {
      storage.removeItem(key);
    },
  };
}

// Administrators sign in per tab. Shoppers stay signed in on their own device.
export const adminSession = tokenStore(sessionStorage, "grocery_admin_tokens");
export const shopperSession = tokenStore(localStorage, "grocery_shopper_tokens");

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

export async function api<T>(path: string, init: RequestInit = {}, authed: boolean | "shopper" = false): Promise<T> {
  const session = authed === "shopper" ? shopperSession : adminSession;
  const withAuth = (): RequestInit => {
    const tokens = session.get();
    return tokens
      ? { ...init, headers: { ...init.headers, Authorization: `Bearer ${tokens.access_token}` } }
      : init;
  };
  let response = await send(path, authed ? withAuth() : init);

  const tokens = session.get();
  if (authed && response.status === 401 && tokens) {
    const renewed = await send("/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refresh_token }),
    });
    if (renewed.ok) {
      session.set({ ...tokens, access_token: (await renewed.json()).access_token });
      response = await send(path, withAuth());
    } else {
      session.clear();
    }
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(describe(body.detail, response.status), response.status);
  }
  return response.json();
}

export const postJson = <T,>(path: string, body: unknown, authed: boolean | "shopper" = false) =>
  api<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, authed);

export function query(params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "" && value !== false) search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
