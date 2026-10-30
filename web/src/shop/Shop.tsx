import { useEffect, useState } from "react";
import { api, Category, isNative, StoreInfo } from "../api";
import { useDrafts } from "../drafts";
import { distance } from "../format";
import { AREAS, useLocation } from "../location";
import { navigate } from "../router";
import { DraftEditor, DraftList, QuickCompare } from "./Drafts";
import { ProductPage, SearchPage, StorePage } from "./Search";
import { MoreLinks } from "./More";

const TABS = [
  ["/shop", "Home", "⌂"],
  ["/shop/search", "Search", "⌕"],
  ["/shop/compare", "Multi", "☰"],
  ["/shop/drafts", "Drafts", "✎"],
  ["/shop/more", "More", "⋯"],
];

export function Shop({ path, params }: { path: string; params: URLSearchParams }) {
  const [, , section, id] = path.split("/");
  let page;
  if (section === "search") page = <SearchPage key={params.toString()} initial={params.get("q") ?? ""} category={params.get("category")} />;
  else if (section === "product") page = <ProductPage key={id} id={id} />;
  else if (section === "store") page = <StorePage key={id} id={id} />;
  else if (section === "compare") page = <QuickCompare />;
  else if (section === "drafts") page = id ? <DraftEditor key={id} id={id} /> : <DraftList />;
  else if (section === "more") page = <MoreLinks />;
  else page = <Home />;

  const active = `/shop${section ? `/${section}` : ""}`;
  return (
    <div className="shop">
      <main className="shop-page">{page}</main>
      <nav className="tabs" aria-label="Main">
        {TABS.map(([to, label, icon]) => (
          <a key={to} href={`#${to}`} className={active === to ? "on" : ""} aria-current={active === to ? "page" : undefined}>
            <span aria-hidden>{icon}</span>{label}
          </a>
        ))}
      </nav>
    </div>
  );
}

export function LocationBar() {
  const { place, locating, error, useDevice, chooseArea } = useLocation();
  return (
    <div className="location">
      <div className="location-row">
        <span aria-hidden>📍</span>
        <select
          aria-label="Your area"
          value={place?.source === "manual" ? place.label : ""}
          onChange={(e) => chooseArea(e.target.value)}
        >
          <option value="">{place?.source === "device" ? "Current location" : "Choose your area"}</option>
          {AREAS.map((a) => <option key={a.label}>{a.label}</option>)}
        </select>
        <button className="mini" onClick={useDevice} disabled={locating}>
          {locating ? "Locating…" : "Use my location"}
        </button>
      </div>
      {error && <p className="hint">{error}</p>}
    </div>
  );
}

function Home() {
  const [term, setTerm] = useState("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [stores, setStores] = useState<StoreInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const { place } = useLocation();
  const { drafts } = useDrafts();

  useEffect(() => {
    api<Category[]>("/categories").then(setCategories).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!place) { setStores([]); return; }
    api<StoreInfo[]>(`/stores/nearby?latitude=${place.latitude}&longitude=${place.longitude}&radius_km=25`)
      .then(setStores).catch((e) => setError(e.message));
  }, [place]);

  return (
    <>
      <header className="shop-head">
        <h1>Grocery Price Finder</h1>
        {!isNative && <a href="#/" className="back-site">About</a>}
      </header>
      <LocationBar />
      <form className="search-box" onSubmit={(e) => { e.preventDefault(); navigate(`/shop/search?q=${encodeURIComponent(term)}`); }}>
        <input type="search" placeholder="Search grocery products…" value={term} onChange={(e) => setTerm(e.target.value)} aria-label="Search grocery products" />
        <button className="btn primary">Search</button>
      </form>
      <a className="callout" href="#/shop/compare">
        <strong>Have a whole list?</strong>
        <span>Search many items at once and see each store's total →</span>
      </a>
      {error && <p className="error" role="alert">{error}</p>}

      {drafts && drafts.length > 0 && (
        <section>
          <h2>Continue a draft</h2>
          {drafts.slice(0, 2).map((d) => (
            <a className="row-link" key={d.id} href={`#/shop/drafts/${d.id}`}>
              <span>{d.name || "Untitled draft"}</span>
              <small>{d.items.length} {d.items.length === 1 ? "item" : "items"}</small>
            </a>
          ))}
        </section>
      )}

      <section>
        <h2>Categories</h2>
        <div className="chips">
          {categories.map((c) => <a className="chip" key={c.id} href={`#/shop/search?category=${c.id}`}>{c.name}</a>)}
        </div>
      </section>

      {stores.length > 0 && (
        <section>
          <h2>Nearby stores</h2>
          {stores.slice(0, 4).map((s) => (
            <a className="row-link" key={s.store_id} href={`#/shop/store/${s.store_id}`}>
              <span>{s.name}</span>
              <small>{distance(s.distance_km)}</small>
            </a>
          ))}
        </section>
      )}
    </>
  );
}
