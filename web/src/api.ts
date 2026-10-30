import { Capacitor } from "@capacitor/core";
import { Preferences } from "@capacitor/preferences";

export const isNative = Capacitor.isNativePlatform();
const DEFAULT_NATIVE_URL = import.meta.env.VITE_API_URL || "http://10.0.2.2:8000";
const SERVER_KEY = "server_url";

let base: string = isNative ? DEFAULT_NATIVE_URL : import.meta.env.VITE_API_URL || "";

export async function loadServerUrl() {
  if (!isNative) return;
  const { value } = await Preferences.get({ key: SERVER_KEY });
  if (value) base = value;
}

export const getServerUrl = () => base;

export async function setServerUrl(url: string) {
  base = url.trim().replace(/\/+$/, "");
  await Preferences.set({ key: SERVER_KEY, value: base });
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export interface Offer {
  product_id: string;
  product_name: string;
  brand: string;
  package_size: string;
  category: string;
  store_id: string;
  store_name: string;
  store_address: string;
  latitude: number;
  longitude: number;
  price: number;
  currency: string;
  distance_km: number | null;
  availability: "available" | "unavailable" | "unknown";
  price_status: PriceStatus;
  last_synced_at: string | null;
  labels: string[];
}

export type PriceStatus = "fresh" | "aging" | "stale" | "unavailable" | "unknown";

export interface SearchResponse {
  results: Offer[];
  stale_results: Offer[];
  stale_hidden: number;
  generated_at: string;
}

export interface Candidate {
  product_id: string;
  product_name: string;
  brand: string;
  package_size: string;
  min_price: number;
  store_count: number;
}

export interface BasketItem {
  query: string;
  quantity: number;
  status: "matched" | "no_match" | "no_eligible_price";
  selected_product_id: string | null;
  candidates: Candidate[];
  offers: Offer[];
  stale_offers: Offer[];
}

export interface StoreBasket {
  store_id: string;
  store_name: string;
  distance_km: number | null;
  total: number;
  items_found: number;
  items_missing: string[];
}

export interface BasketResponse {
  items: BasketItem[];
  stores: StoreBasket[];
  best_single_store: StoreBasket | null;
  split_basket: {
    total: number;
    store_count: number;
    lines: {
      query: string;
      product_name: string;
      package_size: string;
      store_id: string;
      store_name: string;
      quantity: number;
      unit_price: number;
      line_total: number;
    }[];
  };
  split_savings: number | null;
  generated_at: string;
}

export interface StoreInfo {
  store_id: string;
  name: string;
  address: string;
  organization: string;
  latitude: number;
  longitude: number;
  distance_km: number | null;
}

export interface Stats {
  retailers: number;
  stores: number;
  products: number;
  listings: number;
  sample_data: boolean;
  public_demo_login: boolean;
}

export interface Category {
  id: string;
  name: string;
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
    throw new ApiError(
      isNative
        ? `Can't reach the server at ${base}. Check the address in More > Server.`
        : "Can't reach the server. Check that the backend is running.",
      0,
    );
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
