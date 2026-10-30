import { useEffect, useRef, useState } from "react";
import { BasketItem, BasketResponse, postJson } from "../api";
import {
  addItems, deleteDraft, Draft, DraftItem, MAX_ITEMS, newDraft, parseItems, readDrafts, saveDraft, useDrafts,
} from "../drafts";
import { distance, peso } from "../format";
import { useLocation } from "../location";
import { navigate } from "../router";
import { OfferRow } from "./Search";
import { LocationBar } from "./Shop";

/** The Multi tab: type or paste a list, compare, and optionally keep it as a draft. */
export function QuickCompare() {
  const [draft, setDraft] = useState<Draft>(() => newDraft());
  return (
    <>
      <h1>Search multiple items</h1>
      <p className="muted">Type or paste your list. One item per line, or separate with commas.</p>
      <ListEditor draft={draft} onChange={setDraft} bulk />
      {draft.items.length > 0 && (
        <button
          className="btn block"
          onClick={async () => {
            const saved = await saveDraft({ ...draft, name: draft.name || "My list" });
            navigate(`/shop/drafts/${saved.id}`);
          }}
        >
          Save as draft
        </button>
      )}
    </>
  );
}

export function DraftList() {
  const { drafts, reload } = useDrafts();
  const [confirming, setConfirming] = useState<string | null>(null);

  async function create() {
    const saved = await saveDraft(newDraft());
    navigate(`/shop/drafts/${saved.id}`);
  }

  return (
    <>
      <h1>Drafts</h1>
      <p className="muted">Lists you're still working on. Saved on this device only.</p>
      <button className="btn primary block" onClick={create}>New draft</button>
      {drafts?.length === 0 && <p className="muted empty">No drafts yet. Start one, or save a list from the Multi tab.</p>}
      {drafts?.map((d) => (
        <div className="draft-row" key={d.id}>
          <a href={`#/shop/drafts/${d.id}`}>
            <strong>{d.name || "Untitled draft"}</strong>
            <small>{d.items.length} {d.items.length === 1 ? "item" : "items"} · edited {new Date(d.updatedAt).toLocaleDateString()}</small>
          </a>
          {confirming === d.id ? (
            <span className="confirm">
              <button className="mini danger" onClick={async () => { await deleteDraft(d.id); setConfirming(null); reload(); }}>Delete</button>
              <button className="mini" onClick={() => setConfirming(null)}>Keep</button>
            </span>
          ) : (
            <button className="mini" aria-label={`Delete ${d.name || "untitled draft"}`} onClick={() => setConfirming(d.id)}>✕</button>
          )}
        </div>
      ))}
    </>
  );
}

export function DraftEditor({ id }: { id: string }) {
  const [draft, setDraft] = useState<Draft | null | undefined>(undefined);
  const [saved, setSaved] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const latest = useRef<Draft | null>(null);

  useEffect(() => {
    readDrafts().then((all) => setDraft(all.find((d) => d.id === id) ?? null));
  }, [id]);

  // Autosave so a closed app never loses a list.
  function change(next: Draft) {
    setDraft(next);
    setSaved(false);
    latest.current = next;
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      await saveDraft(next);
      latest.current = null;
      setSaved(true);
    }, 400);
  }

  useEffect(() => () => {
    clearTimeout(timer.current);
    if (latest.current) saveDraft(latest.current);
  }, []);

  if (draft === undefined) return <p className="muted">Loading…</p>;
  if (draft === null) return <p className="muted">This draft no longer exists. <a href="#/shop/drafts">Back to drafts</a></p>;

  return (
    <>
      <a className="link" href="#/shop/drafts">‹ Drafts</a>
      <input
        className="title-input"
        placeholder="Name this draft"
        aria-label="Draft name"
        value={draft.name}
        onChange={(e) => change({ ...draft, name: e.target.value })}
      />
      <p className="hint">{saved ? "Saved on this device" : "Saving…"}</p>
      <ListEditor draft={draft} onChange={change} />
    </>
  );
}

function ListEditor({ draft, onChange, bulk }: { draft: Draft; onChange: (draft: Draft) => void; bulk?: boolean }) {
  const { place } = useLocation();
  const [text, setText] = useState("");
  const [radius, setRadius] = useState("");
  const [result, setResult] = useState<BasketResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const add = () => {
    const parsed = parseItems(text);
    if (!parsed.length) return;
    onChange(addItems(draft, parsed));
    setText("");
    setResult(null);
  };

  const update = (id: string, patch: Partial<DraftItem>) => {
    onChange({ ...draft, items: draft.items.map((i) => (i.id === id ? { ...i, ...patch } : i)) });
    setResult(null);
  };

  const remove = (id: string) => {
    onChange({ ...draft, items: draft.items.filter((i) => i.id !== id) });
    setResult(null);
  };

  async function compare(items = draft.items) {
    setBusy(true);
    setError(null);
    try {
      setResult(await postJson<BasketResponse>("/products/multi-search", {
        items: items.map((i) => ({ query: i.query, quantity: i.quantity, product_id: i.productId })),
        ...(place ? { latitude: place.latitude, longitude: place.longitude } : {}),
        ...(place && radius ? { radius_km: Number(radius) } : {}),
      }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function pick(query: string, item: BasketItem, productId: string) {
    const candidate = item.candidates.find((c) => c.product_id === productId)!;
    const items = draft.items.map((i) => (
      i.query === query
        ? { ...i, productId, productLabel: `${candidate.product_name}, ${candidate.brand}, ${candidate.package_size}` }
        : i
    ));
    onChange({ ...draft, items });
    compare(items);
  }

  const full = draft.items.length >= MAX_ITEMS;

  return (
    <>
      <div className="adder">
        {bulk ? (
          <textarea
            rows={4}
            value={text}
            placeholder={"rice 5kg\n2 x cooking oil\neggs, soy sauce"}
            aria-label="Items to add"
            onChange={(e) => setText(e.target.value)}
          />
        ) : (
          <input
            type="text"
            value={text}
            placeholder="Add items, separated by commas"
            aria-label="Items to add"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          />
        )}
        <button className="btn" onClick={add} disabled={!text.trim() || full}>Add</button>
      </div>
      {full && <p className="hint">A list can hold up to {MAX_ITEMS} items.</p>}

      {draft.items.length === 0 && !bulk && <p className="muted empty">Nothing here yet. Add your first item above.</p>}

      {draft.items.length > 0 && (
        <ul className="items">
          {draft.items.map((item) => (
            <li key={item.id}>
              <span className="item-name">
                {item.query}
                {item.productLabel && <small>{item.productLabel}</small>}
              </span>
              <span className="stepper">
                <button aria-label={`Fewer ${item.query}`} disabled={item.quantity <= 1} onClick={() => update(item.id, { quantity: item.quantity - 1 })}>−</button>
                <b>{item.quantity}</b>
                <button aria-label={`More ${item.query}`} disabled={item.quantity >= 999} onClick={() => update(item.id, { quantity: item.quantity + 1 })}>+</button>
              </span>
              <button className="mini" aria-label={`Remove ${item.query}`} onClick={() => remove(item.id)}>✕</button>
            </li>
          ))}
        </ul>
      )}

      {draft.items.length > 0 && (
        <>
          <LocationBar />
          {place && (
            <label className="inline-field">Only stores within
              <select value={radius} onChange={(e) => { setRadius(e.target.value); setResult(null); }}>
                <option value="">Any distance</option>
                {[2, 5, 10, 25].map((km) => <option key={km} value={km}>{km} km</option>)}
              </select>
            </label>
          )}
          <button className="btn primary block" disabled={busy} onClick={() => compare()}>
            {busy ? "Comparing…" : `Compare ${draft.items.length} ${draft.items.length === 1 ? "item" : "items"}`}
          </button>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {result && <Basket data={result} onPick={pick} />}
    </>
  );
}

function Basket({ data, onPick }: { data: BasketResponse; onPick: (query: string, item: BasketItem, productId: string) => void }) {
  const { best_single_store: best, split_basket: split, split_savings: savings } = data;
  const problems = data.items.filter((i) => i.status !== "matched");
  const matchedCount = data.items.length - problems.length;

  return (
    <div className="basket">
      <h2>Your basket</h2>
      {problems.map((item) => (
        <p className="warn" key={item.query}>
          ▲ <b>{item.query}</b>: {item.status === "no_match" ? "no matching product found" : "no current price in range"}. Not included in totals.
        </p>
      ))}

      {matchedCount > 0 && (
        <div className="totals">
          <div className="total-card">
            <span>Best single store</span>
            {best ? (
              <>
                <strong className="price">{peso(best.total)}</strong>
                <a href={`#/shop/store/${best.store_id}`}>{best.store_name}</a>
                {best.distance_km !== null && <small>{distance(best.distance_km)}</small>}
              </>
            ) : <small>No single store has every item.</small>}
          </div>
          <div className="total-card">
            <span>Cheapest per item</span>
            <strong className="price">{peso(split.total)}</strong>
            <small>across {split.store_count} {split.store_count === 1 ? "store" : "stores"}</small>
            {!!savings && <small className="save">Saves {peso(savings)} before travel costs</small>}
          </div>
        </div>
      )}

      {data.stores.length > 0 && (
        <>
          <h3>Total at each store</h3>
          <ul className="store-totals">
            {data.stores.map((s) => (
              <li key={s.store_id}>
                <a href={`#/shop/store/${s.store_id}`}>{s.store_name}</a>
                <small>
                  {s.items_found} of {matchedCount} items
                  {s.distance_km !== null ? ` · ${distance(s.distance_km)}` : ""}
                  {s.items_missing.length > 0 ? ` · missing ${s.items_missing.join(", ")}` : ""}
                </small>
                <span className="price">{peso(s.total)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <h3>Item by item</h3>
      {data.items.filter((i) => i.status === "matched").map((item) => (
        <section className="product-card" key={item.query}>
          <header>
            <div>
              <h2>{item.query}{item.quantity > 1 ? ` × ${item.quantity}` : ""}</h2>
            </div>
          </header>
          {item.candidates.length > 1 && (
            <label className="inline-field">Exact product
              <select value={item.selected_product_id ?? ""} onChange={(e) => onPick(item.query, item, e.target.value)}>
                {item.candidates.map((c) => (
                  <option key={c.product_id} value={c.product_id}>
                    {c.product_name}, {c.brand}, {c.package_size} (from {peso(c.min_price)})
                  </option>
                ))}
              </select>
            </label>
          )}
          {item.offers.slice(0, 3).map((o) => <OfferRow key={o.store_id} offer={o} />)}
        </section>
      ))}
      <p className="hint">Prices come from each store's last update and may differ at checkout. Only identical products and sizes are compared.</p>
    </div>
  );
}
