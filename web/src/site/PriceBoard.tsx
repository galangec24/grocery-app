import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, MarketSummary, PriceRow, query } from "../api";
import { addItems, newDraft, readDrafts, saveDraft } from "../drafts";
import { longDate, mapUrl, peso } from "../format";
import { useLocation } from "../location";

type SortKey = "commodity" | "price" | "change_pct";

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

function CityPanel() {
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
          <h2>{city ? `${city.city}, ${city.region}` : "Find your city"}</h2>
          <p className="muted">
            {city
              ? city.stores_available
                ? `${city.store_count} supermarkets and malls found. Official SRPs apply to all of them.`
                : "The store map is busy, so stores can't be listed right now. Official SRPs still apply across your city."
              : "See which official prices apply to you and every mall and supermarket in your city."}
          </p>
        </div>
        <div className="city-actions">
          <button className="btn primary" onClick={locate} disabled={busy}>{busy ? "Locating…" : "Use my location"}</button>
          {city && <button className="btn" onClick={clear}>Clear</button>}
        </div>
      </div>
      {!city && (
        <form className="city-form" onSubmit={submit}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Or type a city, like Davao City" aria-label="City name" />
          <button className="btn" disabled={busy || !name.trim()}>Find</button>
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
                <a href={mapUrl(s.latitude, s.longitude)} target="_blank" rel="noreferrer">
                  <strong>{s.name}</strong>
                  <small>{s.type} · {s.distance_km.toFixed(1)} km straight-line</small>
                </a>
              </li>
            ))}
          </ul>
          {city.stores.length > 8 && <button className="link" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${city.stores.length}`}</button>}
          <p className="hint">{city.attribution}. Store-by-store prices will appear once retailers connect their data.</p>
        </>
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
  const island = city?.island;

  useEffect(() => {
    api<MarketSummary>("/market/summary").then(setSummary).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    api<{ results: PriceRow[] }>(`/market/prices${query({ island })}`)
      .then((r) => { setRows(r.results); setError(null); })
      .catch((e) => setError(e.message));
  }, [island]);

  const categories = useMemo(
    () => [...new Set((rows ?? []).filter((r) => !source || r.source === source).map((r) => r.category))].sort(),
    [rows, source],
  );

  const shown = useMemo(() => {
    const words = term.toLowerCase().split(/\s+/).filter(Boolean);
    const list = (rows ?? []).filter((r) => {
      const text = `${r.commodity} ${r.specification} ${r.category} ${r.group}`.toLowerCase();
      return (!source || r.source === source) && (!category || r.category === category)
        && words.every((w) => text.includes(w) || (w.endsWith("s") && text.includes(w.slice(0, -1))));
    });
    if (!sort) return list; // Food first, as the server orders it.
    const direction = sort.up ? 1 : -1;
    return [...list].sort((a, b) => {
      if (sort.key === "commodity") return direction * a.commodity.localeCompare(b.commodity);
      if (sort.key === "price") return direction * (a.price - b.price);
      return direction * ((a.change_pct ?? 0) - (b.change_pct ?? 0));
    });
  }, [rows, term, source, category, sort]);

  const toggle = (key: SortKey) => setSort((s) => ({ key, up: s?.key === key ? !s.up : key !== "change_pct" }));
  const arrow = (key: SortKey) => (sort?.key === key ? (sort.up ? " ↑" : " ↓") : "");
  const aria = (key: SortKey) => (sort?.key === key ? (sort.up ? "ascending" : "descending") : "none");

  function addToDraft(row: PriceRow) {
    const base = readDrafts()[0] ?? newDraft("My list");
    const label = [row.commodity, row.specification].filter(Boolean).join(", ");
    saveDraft(addItems(base, [{ query: label, quantity: 1, priceId: row.id, label }]));
    setAdded(row.id);
  }

  const srp = summary?.sources.find((s) => s.id === "dti_srp");
  const dpi = summary?.sources.find((s) => s.id === "da_dpi");

  return (
    <div className="board">
      {!compact && (
        <div className="tiles3d">
          <div className="tile3d"><span>Official prices tracked</span><strong>{summary?.items ?? "–"}</strong><small>{summary?.categories ?? "–"} categories</small></div>
          <div className="tile3d"><span>Market prices updated</span><strong className="date">{longDate(dpi?.report_date ?? null)}</strong><small>DA Daily Price Index</small></div>
          <div className="tile3d"><span>SRP bulletin in force</span><strong className="date">{longDate(srp?.report_date ?? null)}</strong><small>DTI, nationwide</small></div>
          <div className="tile3d"><span>Moved since last report</span><strong><b className="up">▲{summary?.rising ?? 0}</b> <b className="down">▼{summary?.falling ?? 0}</b></strong><small>Metro Manila markets</small></div>
        </div>
      )}

      <CityPanel />

      <section className="panel table-panel">
        <div className="controls">
          <input type="search" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Search rice, sardines, tilapia, Bear Brand…" aria-label="Search prices" />
          <select value={source} aria-label="Price type" onChange={(e) => { setSource(e.target.value); setCategory(""); }}>
            <option value="">All prices</option>
            <option value="dti_srp">Standard price (DTI SRP)</option>
            <option value="da_dpi">Market price (DA, Metro Manila)</option>
          </select>
          <select value={category} aria-label="Category" onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {categories.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        {!rows && !error && <p className="muted pad">Loading official prices…</p>}
        {rows && rows.length === 0 && <p className="muted pad">Official prices are being collected. Check back in a few minutes.</p>}
        {rows && rows.length > 0 && shown.length === 0 && <p className="muted pad">Nothing matches. Try one word, like “rice”.</p>}
        {shown.length > 0 && (
          <>
            <p className="result-count">{shown.length} {shown.length === 1 ? "price" : "prices"}</p>
            <div className="table-wrap">
              <table className="prices">
                <thead>
                  <tr>
                    <th aria-sort={aria("commodity")}><button onClick={() => toggle("commodity")}>Item{arrow("commodity")}</button></th>
                    <th>Category</th>
                    <th className="num" aria-sort={aria("price")}><button onClick={() => toggle("price")}>Price{arrow("price")}</button></th>
                    <th aria-sort={aria("change_pct")}><button onClick={() => toggle("change_pct")}>Change{arrow("change_pct")}</button></th>
                    <th>Trend</th>
                    <th>Applies to</th>
                    <th><span className="sr">Add</span></th>
                  </tr>
                </thead>
                <tbody>
                  {shown.slice(0, 250).map((row) => (
                    <tr key={row.id}>
                      <td data-label="Item"><strong>{row.commodity}</strong>{row.specification && <small>{row.specification}</small>}</td>
                      <td data-label="Category">{row.category}</td>
                      <td data-label="Price" className="num"><span className="price">{peso(row.price)}</span><small>per {row.unit}</small></td>
                      <td data-label="Change"><Change row={row} /></td>
                      <td data-label="Trend" className="trend-cell">{row.kind === "srp" ? <span className="muted">Fixed by bulletin</span> : <Sparkline values={row.trend} />}</td>
                      <td data-label="Applies to">{row.region}</td>
                      <td className="row-add">
                        <button className="mini" onClick={() => addToDraft(row)} disabled={added === row.id}>{added === row.id ? "Added" : "Add to draft"}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {shown.length > 250 && <p className="hint pad">Showing the first 250. Search to narrow the list.</p>}
          </>
        )}
      </section>

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
