import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, Offer, query, SearchResponse, StoreInfo } from "../api";
import { addItems, newDraft, readDrafts, saveDraft, useDrafts } from "../drafts";
import { distance, mapUrl, peso, STATUS_META, stockText, timeAgo } from "../format";
import { useLocation } from "../location";
import { navigate } from "../router";
import { LocationBar } from "./Shop";

const SORTS = [
  ["price_asc", "Lowest price"],
  ["distance_asc", "Nearest"],
  ["best_nearby", "Best nearby"],
  ["freshness", "Freshest"],
];

const coords = (place: ReturnType<typeof useLocation>["place"]) =>
  place ? { latitude: place.latitude, longitude: place.longitude } : {};

export function OfferRow({ offer, stale }: { offer: Offer; stale?: boolean }) {
  const meta = STATUS_META[offer.price_status];
  return (
    <a className={`offer${stale ? " stale" : ""}`} href={`#/shop/store/${offer.store_id}`}>
      <div className="offer-main">
        <strong>{offer.store_name}</strong>
        <small>
          {[distance(offer.distance_km), stockText(offer)].filter(Boolean).join(" · ")}
        </small>
        <small className={`fresh-${offer.price_status}`}>
          {meta.icon} {meta.label}, updated {timeAgo(offer.last_synced_at)}
        </small>
        {offer.labels.length > 0 && (
          <div className="labels">{offer.labels.map((l) => <span className="label" key={l}>{l}</span>)}</div>
        )}
      </div>
      <span className="price">{peso(offer.price)}</span>
    </a>
  );
}

function group(offers: Offer[]) {
  const groups = new Map<string, Offer[]>();
  for (const offer of offers) groups.set(offer.product_id, [...(groups.get(offer.product_id) ?? []), offer]);
  return [...groups.values()];
}

export function AddToDraft({ productId, query: name, label }: { productId: string; query: string; label: string }) {
  const [open, setOpen] = useState(false);
  const { drafts, reload } = useDrafts();
  const [done, setDone] = useState<string | null>(null);

  async function add(id: string | null) {
    const all = await readDrafts();
    const base = all.find((d) => d.id === id) ?? newDraft("My list");
    const saved = await saveDraft(addItems(base, [{ query: name, quantity: 1, productId, productLabel: label }]));
    setOpen(false);
    setDone(saved.id);
    reload();
  }

  if (done) return <a className="mini" href={`#/shop/drafts/${done}`}>Added. View draft</a>;
  if (!open) return <button className="mini" onClick={() => (drafts?.length ? setOpen(true) : add(null))}>Add to draft</button>;
  return (
    <span className="draft-picker">
      {drafts?.map((d) => <button className="mini" key={d.id} onClick={() => add(d.id)}>{d.name || "Untitled draft"}</button>)}
      <button className="mini" onClick={() => add(null)}>New draft</button>
    </span>
  );
}

export function SearchPage({ initial, category }: { initial: string; category: string | null }) {
  const { place } = useLocation();
  const [term, setTerm] = useState(initial);
  const [submitted, setSubmitted] = useState(initial);
  const [sort, setSort] = useState("price_asc");
  const [radius, setRadius] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [inStock, setInStock] = useState(false);
  const [freshOnly, setFreshOnly] = useState(false);
  const [showStale, setShowStale] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const canSearch = !!submitted.trim() || !!category;

  useEffect(() => {
    if (!canSearch) { setData(null); return; }
    let live = true;
    setLoading(true);
    const params = query({
      q: submitted, category_id: category, ...coords(place), sort_by: sort,
      radius_km: place ? radius : "", max_price: maxPrice,
      availability: inStock ? "available" : "", price_status: freshOnly ? "fresh" : "",
      include_stale: showStale,
    });
    api<SearchResponse>(`/products/search${params}`)
      .then((r) => { if (live) { setData(r); setError(null); } })
      .catch((e) => { if (live) setError(e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [submitted, category, place, sort, radius, maxPrice, inStock, freshOnly, showStale, canSearch]);

  const groups = useMemo(() => group(data?.results ?? []), [data]);

  function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitted(term);
  }

  return (
    <>
      <form className="search-box" onSubmit={submit}>
        <input type="search" autoFocus={!initial && !category} placeholder="Name, brand, category or size" value={term}
          onChange={(e) => setTerm(e.target.value)} aria-label="Search products" />
        <button className="btn primary">Search</button>
      </form>
      <LocationBar />

      <div className="chips sort" role="group" aria-label="Sort by">
        {SORTS.map(([value, label]) => (
          <button key={value} className={`chip${sort === value ? " on" : ""}`} aria-pressed={sort === value} onClick={() => setSort(value)}>
            {label}
          </button>
        ))}
        <button className={`chip${showFilters ? " on" : ""}`} aria-expanded={showFilters} onClick={() => setShowFilters(!showFilters)}>Filters</button>
      </div>

      {showFilters && (
        <div className="filters">
          <label>Within
            <select value={radius} onChange={(e) => setRadius(e.target.value)} disabled={!place}>
              <option value="">Any distance</option>
              {[2, 5, 10, 25].map((km) => <option key={km} value={km}>{km} km</option>)}
            </select>
          </label>
          <label>Max price (₱)
            <input type="number" min="0" inputMode="decimal" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} />
          </label>
          <label className="check"><input type="checkbox" checked={inStock} onChange={(e) => setInStock(e.target.checked)} /> Confirmed in stock only</label>
          <label className="check"><input type="checkbox" checked={freshOnly} onChange={(e) => setFreshOnly(e.target.checked)} /> Fresh prices only</label>
          <label className="check"><input type="checkbox" checked={showStale} onChange={(e) => setShowStale(e.target.checked)} /> Show outdated prices separately</label>
          {!place && <p className="hint">Choose your area to filter and sort by distance.</p>}
        </div>
      )}

      {error && <p className="error" role="alert">{error}</p>}
      {loading && !data && <p className="muted">Searching…</p>}
      {!canSearch && <p className="muted">Try “rice”, “cooking oil 1L” or a brand name.</p>}
      {data && !error && groups.length === 0 && !loading && (
        <p className="muted">No current prices match. Try fewer words or widen your filters.</p>
      )}

      {groups.map((offers) => {
        const first = offers[0];
        const label = `${first.brand} · ${first.package_size}`;
        return (
          <section className="product-card" key={first.product_id}>
            <header>
              <a href={`#/shop/product/${first.product_id}`}>
                <h2>{first.product_name}</h2>
                <small>{label}</small>
              </a>
              <AddToDraft productId={first.product_id} query={`${first.product_name} ${first.package_size}`} label={label} />
            </header>
            {offers.slice(0, 3).map((o) => <OfferRow key={o.store_id} offer={o} />)}
            {offers.length > 3 && <a className="see-all" href={`#/shop/product/${first.product_id}`}>See all {offers.length} stores</a>}
          </section>
        );
      })}

      {!!data?.stale_hidden && (
        <p className="hint">{data.stale_hidden} outdated {data.stale_hidden === 1 ? "price is" : "prices are"} hidden. Turn it on under Filters to see them.</p>
      )}
      {!!data?.stale_results.length && <StaleSection offers={data.stale_results} />}
      {groups.length > 0 && <p className="hint">Distances are straight-line, not road distance. Prices may differ at checkout.</p>}
    </>
  );
}

function StaleSection({ offers }: { offers: Offer[] }) {
  return (
    <section className="stale-box">
      <h2>▲ Outdated prices</h2>
      <p>These haven't been updated recently and may no longer be current. They aren't included in the ranking above.</p>
      {offers.map((o) => (
        <div key={o.product_id + o.store_id}>
          <small>{o.product_name} · {o.package_size}</small>
          <OfferRow offer={o} stale />
        </div>
      ))}
    </section>
  );
}

export function ProductPage({ id }: { id: string }) {
  const { place } = useLocation();
  const [data, setData] = useState<{ product: { name: string; brand: string; package_size: string; category: string; barcode: string | null }; results: Offer[]; stale_results: Offer[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<typeof data>(`/products/${id}/prices${query(coords(place))}`).then(setData).catch((e) => setError(e.message));
  }, [id, place]);
  useEffect(load, [load]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  const { product } = data;
  const label = `${product.brand} · ${product.package_size}`;
  return (
    <>
      <button className="link" onClick={() => history.back()}>‹ Back</button>
      <h1>{product.name}</h1>
      <p className="muted">{label} · {product.category}</p>
      <LocationBar />
      <AddToDraft productId={id} query={`${product.name} ${product.package_size}`} label={label} />
      <h2>Prices</h2>
      {data.results.length === 0 && <p className="muted">No current prices for this product.</p>}
      {data.results.map((o) => <OfferRow key={o.store_id} offer={o} />)}
      {data.stale_results.length > 0 && <StaleSection offers={data.stale_results} />}
    </>
  );
}

export function StorePage({ id }: { id: string }) {
  const { place } = useLocation();
  const [store, setStore] = useState<StoreInfo | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<StoreInfo>(`/stores/${id}${query(coords(place))}`),
      api<Offer[]>(`/stores/${id}/products`),
    ]).then(([s, o]) => { setStore(s); setOffers(o); }).catch((e) => setError(e.message));
  }, [id, place]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!store) return <p className="muted">Loading…</p>;
  const shown = offers.filter((o) => `${o.product_name} ${o.brand}`.toLowerCase().includes(filter.toLowerCase()));
  return (
    <>
      <button className="link" onClick={() => history.back()}>‹ Back</button>
      <h1>{store.name}</h1>
      <p className="muted">{store.address}</p>
      {store.distance_km !== null && <p className="muted">{distance(store.distance_km)} (straight-line)</p>}
      <a className="btn primary block" href={mapUrl(store.latitude, store.longitude)} target="_blank" rel="noreferrer">Open in maps</a>
      <h2>Products at this store</h2>
      <input className="field" type="search" placeholder="Filter this store" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter this store's products" />
      {shown.map((o) => (
        <button className="store-line" key={o.product_id} onClick={() => navigate(`/shop/product/${o.product_id}`)}>
          <span>{o.product_name}<small>{o.brand} · {o.package_size} · updated {timeAgo(o.last_synced_at)}</small></span>
          <span className="price">{peso(o.price)}</span>
        </button>
      ))}
    </>
  );
}
