import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, CatalogItem, CityStore, Mall, MallPrice, MarketSummary, PriceRow, query, Suggestion } from "../api";
import { addItems, newDraft, readDrafts, saveDraft } from "../drafts";
import { longDate, peso, timeAgo } from "../format";
import { Icon, IconButton } from "../icons";
import { LiveBadge, useLive } from "../live";
import { useLocation } from "../location";
import { ProductImage, SearchBox } from "../SearchBox";
import { StoreMapDialog } from "../StoreMap";
import { ModalSubject, PriceModal } from "./PriceModal";

type SortKey = "commodity" | "price" | "change_pct";
const PAGE_SIZE = 25;

export function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <span className="muted">No history yet</span>;
  const low = Math.min(...values);
  const span = Math.max(...values) - low || 1;
  const points = values.map((v, i) => `${(i / (values.length - 1)) * 76 + 2},${22 - ((v - low) / span) * 18}`).join(" ");
  const label = `From ${peso(values[0])} to ${peso(values[values.length - 1])} over ${values.length} reports`;
  return (
    <svg className="spark" viewBox="0 0 80 26" role="img" aria-label={label}>
      <title>{label}</title>
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const percent = (value: number | null) => {
  const size = Math.abs(value ?? 0);
  return size < 0.1 ? "under 0.1%" : `${size}%`;
};

export function Change({ row }: { row: PriceRow }) {
  if (row.kind === "srp") return <span className="pill srp">Official SRP</span>;
  if (row.change === null) return <span className="muted">New</span>;
  if (row.change === 0) return <span className="muted">No change</span>;
  const up = row.change > 0;
  return (
    <span className={up ? "up" : "down"}>
      {up ? "▲" : "▼"} {peso(Math.abs(row.change))} ({percent(row.change_pct)})
    </span>
  );
}

function CityPanel({ onBrowse }: { onBrowse: (store: CityStore) => void }) {
  const [mapped, setMapped] = useState<CityStore | null>(null);
  const { city, busy, error, locate, chooseCity, clear } = useLocation();
  const [name, setName] = useState("");
  const [all, setAll] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (name.trim()) chooseCity(name.trim());
  }

  return (
    <section className="panel city">
      <div className="city-head">
        <div>
          <h2>{city ? `📍 ${city.city}, ${city.region}` : busy ? "Finding your city…" : "Find your city"}</h2>
          <p className="muted">
            {city
              ? city.stores_available
                ? `${city.store_count} supermarkets and malls found. Official SRPs apply to all of them.`
                : "The store map is busy, so stores can't be listed right now. Official SRPs still apply across your city."
              : "See which official prices apply to you and every mall and supermarket in your city."}
          </p>
        </div>
        <div className="city-actions">
          <IconButton icon={city ? "refresh" : "pin"} label={busy ? "Finding your city" : city ? "Refresh location" : "Use my location"} className="primary" onClick={locate} disabled={busy} />
          {city && <IconButton icon="close" label="Clear location" onClick={clear} />}
        </div>
      </div>
      {!city && (
        <form className="city-form" onSubmit={submit}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Or type a city, like Davao City" aria-label="City name" />
          <button className="icon-btn" aria-label="Find city" title="Find city" disabled={busy || !name.trim()}><Icon name="search" /></button>
        </form>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {city && !city.metro_manila && (
        <p className="note">Daily market prices are measured in Metro Manila by the DA, so use them as a reference outside Metro Manila. SRPs below are set for {city.island}.</p>
      )}
      {city && city.stores.length > 0 && (
        <>
          <ul className="stores">
            {(all ? city.stores : city.stores.slice(0, 8)).map((s) => (
              <li key={`${s.name}${s.latitude}`}>
                <button onClick={() => setMapped(s)}>
                  <strong>{s.name}</strong>
                  <small>{s.type} · {s.distance_km.toFixed(1)} km straight-line</small>
                </button>
              </li>
            ))}
          </ul>
          {city.stores.length > 8 && <button className="link" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${city.stores.length}`}</button>}
          <p className="hint">Tap a store for its 3D map and route. {city.attribution}.</p>
        </>
      )}
      {mapped && (
        <StoreMapDialog store={{ store_name: mapped.name, latitude: mapped.latitude, longitude: mapped.longitude }}
          detail={`${mapped.type} · ${mapped.distance_km.toFixed(1)} km straight-line`}
          onClose={() => setMapped(null)} onBrowse={() => onBrowse(mapped)} />
      )}
    </section>
  );
}

export function PriceBoard({ compact }: { compact?: boolean }) {
  const { city } = useLocation();
  const [summary, setSummary] = useState<MarketSummary | null>(null);
  const [rows, setRows] = useState<PriceRow[] | null>(null);
  const [term, setTerm] = useState("");
  const [source, setSource] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; up: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [subject, setSubject] = useState<ModalSubject | null>(null);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [matches, setMatches] = useState<Set<string> | null>(null);
  const [aisles, setAisles] = useState<{ name: string; count: number }[]>([]);
  const [malls, setMalls] = useState<Mall[]>([]);
  const [mall, setMall] = useState("");
  const [area, setArea] = useState("here");
  const [places, setPlaces] = useState<{ name: string; prices: number }[]>([]);
  const areaCity = area === "here" ? city?.city : area === "all" ? undefined : area;
  const [mallPrices, setMallPrices] = useState<MallPrice[]>([]);
  const island = city?.island;
  const { version } = useLive();

  useEffect(() => {
    api<MarketSummary>("/market/summary").then(setSummary).catch((e) => setError(e.message));
  }, [version]);

  useEffect(() => {
    api<{ results: PriceRow[] }>(`/market/prices${query({ island })}`)
      .then((r) => { setRows(r.results); setError(null); })
      .catch((e) => setError(e.message));
  }, [island, version]);

  useEffect(() => {
    api<{ name: string; count: number }[]>("/market/aisles").then(setAisles).catch(() => setAisles([]));
  }, []);

  useEffect(() => {
    const words = term.trim();
    if (!words) { setCatalog([]); setMatches(null); return; }
    let live = true;
    const timer = setTimeout(() => {
      api<CatalogItem[]>(`/market/catalog${query({ q: words, limit: 24 })}`)
        .then((found) => { if (live) setCatalog(found); })
        .catch(() => { if (live) setCatalog([]); });
      api<{ results: PriceRow[] }>(`/market/prices${query({ q: words, island })}`)
        .then((found) => { if (live) setMatches(new Set(found.results.map((r) => r.id))); })
        .catch(() => { if (live) setMatches(null); });
    }, 250);
    return () => { live = false; clearTimeout(timer); };
  }, [term, island]);

  useEffect(() => {
    api<Mall[]>(`/market/malls${query({ city: areaCity })}`).then(setMalls).catch(() => setMalls([]));
    api<{ name: string; prices: number }[]>("/market/cities").then(setPlaces).catch(() => setPlaces([]));
  }, [areaCity, version]);

  useEffect(() => {
    const words = term.trim();
    if (!mall && !words) { setMallPrices([]); return; }
    let live = true;
    const timer = setTimeout(() => {
      api<{ results: MallPrice[] }>(`/market/mall-prices${query({ mall, q: words, city: areaCity })}`)
        .then((found) => { if (live) setMallPrices(found.results); })
        .catch(() => { if (live) setMallPrices([]); });
    }, 250);
    return () => { live = false; clearTimeout(timer); };
  }, [mall, term, areaCity, version]);

  // Stores found near the shopper can be picked before any of them has prices.
  const mallOptions = useMemo(() => {
    const local = area === "here" ? city?.stores ?? [] : [];
    const extra = local.map((s) => s.name).filter((name, index, all) =>
      all.indexOf(name) === index && !malls.some((m) => name.toLowerCase().startsWith(`${m.name.toLowerCase()} `)));
    return [...malls, ...extra.map((name) => ({ name, prices: 0, stores: 1 }))];
  }, [malls, city, area]);

  function browseStore(store: CityStore) {
    const known = malls.find((m) => store.name.toLowerCase().startsWith(`${m.name.toLowerCase()} `));
    setArea("here");
    setMall(known?.name ?? store.name);
  }

  const categories = useMemo(
    () => [...new Set((rows ?? []).filter((r) => !source || r.source === source).map((r) => r.category))].sort(),
    [rows, source],
  );

  const shown = useMemo(() => {
    const list = (rows ?? []).filter((r) =>
      (!source || r.source === source) && (!category || r.category === category) && (!matches || matches.has(r.id)));
    if (!sort) return list; // Food first, as the server orders it.
    const direction = sort.up ? 1 : -1;
    return [...list].sort((a, b) => {
      if (sort.key === "commodity") return direction * a.commodity.localeCompare(b.commodity);
      if (sort.key === "price") return direction * (a.price - b.price);
      return direction * ((a.change_pct ?? 0) - (b.change_pct ?? 0));
    });
  }, [rows, matches, source, category, sort]);

  const brands = catalog;

  useEffect(() => setPage(1), [term, source, category, sort, island]);
  const pages = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  const visible = shown.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const toggle = (key: SortKey) => setSort((s) => ({ key, up: s?.key === key ? !s.up : key !== "change_pct" }));
  const arrow = (key: SortKey) => (sort?.key === key ? (sort.up ? " ↑" : " ↓") : "");
  const aria = (key: SortKey) => (sort?.key === key ? (sort.up ? "ascending" : "descending") : "none");

  function addToDraft(row: PriceRow) {
    const base = readDrafts()[0] ?? newDraft("My list");
    const label = [row.commodity, row.specification].filter(Boolean).join(", ");
    saveDraft(addItems(base, [{ query: label, quantity: 1, priceId: row.id, label }]));
    setAdded(row.id);
  }

  function pickSuggestion(item: Suggestion) {
    const row = rows?.find((r) => r.id === item.id);
    if (row) { setSubject({ kind: "price", row }); return; }
    const found = catalog.find((c) => c.id === item.id);
    setSubject({ kind: "brand", item: found ?? {
      id: item.id, name: item.name, brand: "", category: item.category, size: item.size, variant: "",
      barcode: null, image_url: item.image_url, source: "", keywords: "",
      auto_price: item.price === null ? null : { price: item.price, kind: "estimate", label: item.price_label ?? "Estimate" },
    } });
  }

  function addMallPrice(price: MallPrice) {
    const base = readDrafts()[0] ?? newDraft("My list");
    saveDraft(addItems(base, [{ query: price.item_name, quantity: 1 }]));
    setAdded(`${price.store_name}${price.item_name}`);
  }

  function addBrand(item: CatalogItem) {
    const base = readDrafts()[0] ?? newDraft("My list");
    saveDraft(addItems(base, [{ query: `${item.name} ${item.size}`, quantity: 1 }]));
    setAdded(item.id);
  }

  const srp = summary?.sources.find((s) => s.id === "dti_srp");
  const dpi = summary?.sources.find((s) => s.id === "da_dpi");

  return (
    <div className="board">
      {!compact && (
        <div className="tiles3d">
          <div className="tile3d"><span>Official prices tracked</span><strong>{summary?.items ?? "–"}</strong><small>Government prices across {summary?.categories ?? "–"} categories, from the DTI and DA</small></div>
          <div className="tile3d"><span>Market prices updated</span><strong className="date">{longDate(dpi?.report_date ?? null)}</strong><small>Latest DA Daily Price Index: average prices in Metro Manila wet markets</small></div>
          <div className="tile3d"><span>SRP bulletin in force</span><strong className="date">{longDate(srp?.report_date ?? null)}</strong><small>The DTI's suggested retail price list that stores should follow nationwide</small></div>
          <div className="tile3d"><span>Moved since last report</span><strong><b className="up">▲{summary?.rising ?? 0}</b> <b className="down">▼{summary?.falling ?? 0}</b></strong><small>Items that went up ▲ or down ▼ in the latest market report</small></div>
        </div>
      )}

      <CityPanel onBrowse={browseStore} />

      <section className="panel table-panel">
        <div className="controls">
          <SearchBox value={term} onChange={setTerm} onPick={pickSuggestion} label="Search prices" placeholder="Try bigas, itlog, Piatos, dog food…" />
          <select value={source} aria-label="Price type" onChange={(e) => { setSource(e.target.value); setCategory(""); }}>
            <option value="">All prices</option>
            <option value="dti_srp">Standard price (DTI SRP)</option>
            <option value="da_dpi">Market price (DA, Metro Manila)</option>
          </select>
          <select value={category} aria-label="Category" onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {categories.map((c) => <option key={c}>{c}</option>)}
          </select>
          <select value={area} aria-label="Location" onChange={(e) => { setArea(e.target.value); setMall(""); }}>
            <option value="here">{city ? `Near me (${city.city})` : "Near me"}</option>
            <option value="all">All locations</option>
            {places.filter((p) => p.name !== city?.city).map((p) => <option key={p.name} value={p.name}>{p.name} ({p.prices})</option>)}
          </select>
          <select value={mall} aria-label="Mall" onChange={(e) => setMall(e.target.value)}>
            <option value="">All malls</option>
            {mallOptions.map((m) => <option key={m.name} value={m.name}>{m.name}{m.prices ? ` (${m.prices})` : ""}</option>)}
          </select>
        </div>
        <p className="hint filter-help">Search a product, or pick a <b>location</b> then a <b>mall</b> to see only that mall's real prices. Price type chooses official standard prices or daily market prices.</p>
        <div className="aisles" role="group" aria-label="Browse by aisle">
          {aisles.map(({ name }) => (
            <button key={name} className={`chip${term === name ? " on" : ""}`} aria-pressed={term === name} onClick={() => setTerm(term === name ? "" : name)}>{name}</button>
          ))}
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        {!rows && !error && <p className="muted pad">Loading official prices…</p>}
        {rows && rows.length === 0 && <p className="muted pad">Official prices are being collected. Check back in a few minutes.</p>}
        {rows && rows.length > 0 && shown.length === 0 && brands.length === 0 && <p className="muted pad">Nothing matches. Try one word, like “rice”.</p>}
        {mall && mallPrices.length === 0 && (
          <p className="note">No real {mall} prices{term.trim() ? ` for “${term.trim()}”` : ""} yet{areaCity ? ` in ${areaCity}` : ""}. Shopped there? Share your receipt from My List to be the first.</p>
        )}
        {mallPrices.length > 0 && (
          <div className="brand-results">
            <h3>{mall ? `Prices at ${mall}` : "Prices at malls"}</h3>
            <p className="hint">Real prices from stores and shoppers, with the date they were checked.</p>
            <div className="brand-grid">
              {mallPrices.map((price) => {
                const key = `${price.store_name}${price.item_name}`;
                return (
                  <article className="brand-card" key={key}>
                    <ProductImage category={price.item_name} large />
                    <strong>{price.item_name}</strong>
                    <small>{price.store_name}{price.city ? `, ${price.city}` : ""}</small>
                    <b className="brand-price">{peso(price.price)}<small>{price.origin}, {timeAgo(price.reported_at)}</small></b>
                    <IconButton icon={added === key ? "check" : "plus"} label={added === key ? "Added" : "Add to draft"} onClick={() => addMallPrice(price)} disabled={added === key} />
                  </article>
                );
              })}
            </div>
          </div>
        )}
        {brands.length > 0 && (
          <div className="brand-results">
            <h3>Found in stores</h3>
            <p className="hint">≈ marks an estimate, not a store price. Tap a product for details.</p>
            <div className="brand-grid">
              {brands.slice(0, 24).map((item) => (
                <article className="brand-card clickable" key={item.id} tabIndex={0}
                  onClick={() => setSubject({ kind: "brand", item })}
                  onKeyDown={(e) => { if (e.key === "Enter") setSubject({ kind: "brand", item }); }}>
                  <ProductImage src={item.image_url} category={`${item.category} ${item.name}`} large />
                  <strong>{item.name}</strong>
                  <small>{item.variant && <b className="size-tag">{item.variant}</b>} {item.size} · {item.category}</small>
                  {item.auto_price && <b className="brand-price">{item.auto_price.kind === "store" ? "" : "≈ "}{item.auto_price.low ? `${peso(item.auto_price.low)} to ${peso(item.auto_price.high ?? item.auto_price.price)}` : peso(item.auto_price.price)}<small>{item.auto_price.label}</small></b>}
                  <IconButton icon={added === item.id ? "check" : "plus"} label={added === item.id ? "Added" : "Add to draft"} onClick={(e) => { e.stopPropagation(); addBrand(item); }} disabled={added === item.id} />
                </article>
              ))}
            </div>
          </div>
        )}
        {shown.length > 0 && (
          <>
            <p className="result-count">{shown.length} {shown.length === 1 ? "price" : "prices"} <LiveBadge /></p>
            <details className="table-help">
              <summary>How to read this table</summary>
              <dl>
                <div><dt>Item</dt><dd>The product and its size or grade. Tap a row for details and its price history.</dd></div>
                <div><dt>Category</dt><dd>The product group it belongs to in the official report.</dd></div>
                <div><dt>Price</dt><dd>The official price per unit. A shelf price can differ.</dd></div>
                <div><dt>Change</dt><dd>The move since the last report. “Official SRP” prices stay fixed until a new bulletin.</dd></div>
                <div><dt>Trend</dt><dd>The price over recent reports, shown as a small line.</dd></div>
                <div><dt>Applies to</dt><dd>Where the price is valid, such as nationwide or Metro Manila.</dd></div>
              </dl>
            </details>
            <div className="table-wrap">
              <table className="prices">
                <thead>
                  <tr>
                    <th aria-sort={aria("commodity")}><button onClick={() => toggle("commodity")}>Item{arrow("commodity")}</button></th>
                    <th title="The product group in the official report">Category</th>
                    <th className="num" aria-sort={aria("price")}><button onClick={() => toggle("price")}>Price{arrow("price")}</button></th>
                    <th aria-sort={aria("change_pct")}><button onClick={() => toggle("change_pct")}>Change{arrow("change_pct")}</button></th>
                    <th title="The price over recent reports">Trend</th>
                    <th title="Where this price is valid">Applies to</th>
                    <th><span className="sr">Add</span></th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => (
                    <tr key={row.id} className="clickable" tabIndex={0} aria-label={`${row.commodity}, ${peso(row.price)}. Open details`}
                      onClick={() => setSubject({ kind: "price", row })}
                      onKeyDown={(e) => { if (e.key === "Enter") setSubject({ kind: "price", row }); }}>
                      <td data-label="Item"><span className="item-cell"><ProductImage category={`${row.category} ${row.commodity}`} /><span><strong>{row.commodity}</strong>{row.specification && <small>{row.specification}</small>}</span></span></td>
                      <td data-label="Category">{row.category}</td>
                      <td data-label="Price" className="num"><span className="price">{peso(row.price)}</span><small>per {row.unit}</small></td>
                      <td data-label="Change"><Change row={row} /></td>
                      <td data-label="Trend" className="trend-cell">{row.kind === "srp" ? <span className="muted">Fixed by bulletin</span> : <Sparkline values={row.trend} />}</td>
                      <td data-label="Applies to">{row.region}</td>
                      <td className="row-add">
                        <IconButton icon={added === row.id ? "check" : "plus"} label={added === row.id ? "Added" : "Add to draft"} onClick={(e) => { e.stopPropagation(); addToDraft(row); }} disabled={added === row.id} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {pages > 1 && (
              <nav className="pager" aria-label="Pages">
                <button className="mini" disabled={page === 1} onClick={() => setPage(1)}>First</button>
                <button className="mini" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button>
                <span>Page <b>{page}</b> of {pages}</span>
                <button className="mini" disabled={page === pages} onClick={() => setPage(page + 1)}>Next</button>
                <button className="mini" disabled={page === pages} onClick={() => setPage(pages)}>Last</button>
              </nav>
            )}
          </>
        )}
      </section>

      {subject && (
        <PriceModal subject={subject} onClose={() => setSubject(null)}
          added={added === (subject.kind === "price" ? subject.row.id : subject.item.id)}
          onAdd={() => (subject.kind === "price" ? addToDraft(subject.row) : addBrand(subject.item))} />
      )}

      {summary && (
        <section className="sources">
          <h2>Where these prices come from</h2>
          {summary.sources.map((s) => (
            <p key={s.id}>
              <a href={s.source_url} target="_blank" rel="noreferrer"><b>{s.label}</b></a>, {longDate(s.report_date)}. {s.coverage}.
            </p>
          ))}
          <p className="muted">Prices are updated when each agency publishes, not by the minute. They are official references and may differ from a store's shelf price.</p>
        </section>
      )}
    </div>
  );
}
