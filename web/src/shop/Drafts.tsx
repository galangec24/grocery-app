import { useEffect, useMemo, useRef, useState } from "react";
import { BasketLine, BasketResponse, postJson } from "../api";
import { useBudget } from "../budget";
import { addItems, deleteDraft, Draft, DraftItem, duplicateDraft, MAX_ITEMS, newDraft, parseItems, readDrafts, saveDraft, useDrafts } from "../drafts";
import { peso } from "../format";
import { savePurchase } from "../purchases";
import { useLocation } from "../location";
import { navigate } from "../router";
import { BestStore } from "./BestStore";
import { Calculator } from "./Calculator";
import { DateTimePicker } from "./DateTimePicker";
import { Receipt } from "./Receipt";

/** Type or paste a list, watch the receipt build, and optionally keep it as a draft. */
export function QuickCompare() {
  const [draft, setDraft] = useState<Draft>(() => newDraft());
  return (
    <ListEditor draft={draft} onChange={setDraft} bulk
      footer={draft.items.length > 0 && (
        <button className="btn block" onClick={() => navigate(`/shop/drafts/${saveDraft({ ...draft, name: draft.name || "My list" }).id}`)}>
          Save as draft
        </button>
      )} />
  );
}

export function DraftList() {
  const { drafts, reload } = useDrafts();
  const { setSpent } = useBudget();
  const [confirming, setConfirming] = useState<string | null>(null);
  const [term, setTerm] = useState("");
  useEffect(() => setSpent(0), [setSpent]);

  const shown = drafts.filter((d) => (d.name || "Untitled draft").toLowerCase().includes(term.toLowerCase()));

  return (
    <>
      <p className="muted intro">Lists you're still working on, saved on this device.</p>
      <div className="draft-tools">
        <button className="btn primary" onClick={() => navigate(`/shop/drafts/${saveDraft(newDraft()).id}`)}>New draft</button>
        {drafts.length > 3 && <input type="search" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Find a draft" aria-label="Find a draft" />}
      </div>
      {drafts.length === 0 && <p className="muted empty">No drafts yet. Start one, or save a list from My list.</p>}
      <div className="draft-grid">
        {shown.map((d) => {
          const done = d.items.filter((i) => i.checked).length;
          return (
            <article className="draft-card" key={d.id}>
              <a href={`#/shop/drafts/${d.id}`}>
                <strong>{d.name || "Untitled draft"}</strong>
                <span className="draft-total">{d.lastTotal ? peso(d.lastTotal) : "No total yet"}</span>
                <small>{d.items.length} {d.items.length === 1 ? "item" : "items"}{done ? `, ${done} in cart` : ""} · {new Date(d.updatedAt).toLocaleDateString()}</small>
              </a>
              <div className="draft-actions">
                {confirming === d.id ? (
                  <>
                    <button className="mini danger" onClick={() => { deleteDraft(d.id); setConfirming(null); reload(); }}>Delete</button>
                    <button className="mini" onClick={() => setConfirming(null)}>Keep</button>
                  </>
                ) : (
                  <>
                    <button className="mini" onClick={() => { duplicateDraft(d); reload(); }}>Duplicate</button>
                    <button className="mini" aria-label={`Delete ${d.name || "untitled draft"}`} onClick={() => setConfirming(d.id)}>Delete</button>
                  </>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </>
  );
}

export function DraftEditor({ id }: { id: string }) {
  const [draft, setDraft] = useState<Draft | null>(() => readDrafts().find((d) => d.id === id) ?? null);
  const [saved, setSaved] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const latest = useRef<Draft | null>(null);

  // Autosave so a closed tab never loses a list.
  function change(next: Draft) {
    setDraft(next);
    setSaved(false);
    latest.current = next;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      saveDraft(next);
      latest.current = null;
      setSaved(true);
    }, 400);
  }

  useEffect(() => () => {
    clearTimeout(timer.current);
    if (latest.current) saveDraft(latest.current);
  }, []);

  if (draft === null) return <p className="muted">This draft no longer exists. <a href="#/shop/drafts">Back to drafts</a></p>;

  return (
    <ListEditor draft={draft} onChange={change}
      header={(
        <div className="draft-head">
          <a className="link" href="#/shop/drafts">‹ All drafts</a>
          <input className="title-input" placeholder="Name this draft" aria-label="Draft name" value={draft.name}
            onChange={(e) => change({ ...draft, name: e.target.value })} />
          <p className="hint">{saved ? "Saved on this device" : "Saving…"}</p>
        </div>
      )} />
  );
}

function ListEditor({ draft, onChange, bulk, header, footer }: {
  draft: Draft; onChange: (draft: Draft) => void; bulk?: boolean; header?: React.ReactNode; footer?: React.ReactNode;
}) {
  const { city } = useLocation();
  const { budget, setSpent } = useBudget();
  const [text, setText] = useState("");
  const [purchaseDate, setPurchaseDate] = useState(() => new Date());
  const [storeIndex, setStoreIndex] = useState("");
  const [shareNote, setShareNote] = useState<string | null>(null);
  const [savedTrip, setSavedTrip] = useState(false);
  const [result, setResult] = useState<BasketResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const latest = useRef(draft);
  latest.current = draft;

  const signature = useMemo(
    () => JSON.stringify(draft.items.map((i) => [i.query, i.quantity, i.priceId, i.customPrice])),
    [draft.items],
  );

  // The receipt follows the list, so there is no button to press.
  useEffect(() => {
    if (draft.items.length === 0) {
      setResult(null);
      setSpent(0);
      return;
    }
    let live = true;
    const timer = setTimeout(async () => {
      try {
        const data = await postJson<BasketResponse>("/market/basket", {
          items: draft.items.map((i) => ({ query: i.query, quantity: i.quantity, price_id: i.priceId, custom_price: i.customPrice })),
          ...(city ? { island: city.island, city: city.city } : {}),
        });
        if (!live) return;
        setResult(data);
        setSpent(data.total);
        setError(null);
        if (latest.current.lastTotal !== data.total) onChange({ ...latest.current, lastTotal: data.total });
      } catch (e) {
        if (live) setError((e as Error).message);
      }
    }, 300);
    return () => { live = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, city?.island]);

  useEffect(() => () => setSpent(0), [setSpent]);

  const add = () => {
    const parsed = parseItems(text);
    if (!parsed.length) return;
    onChange(addItems(draft, parsed));
    setText("");
  };

  const update = (id: string, patch: Partial<DraftItem>) =>
    onChange({ ...draft, items: draft.items.map((i) => (i.id === id ? { ...i, ...patch } : i)) });

  const remove = (id: string) => onChange({ ...draft, items: draft.items.filter((i) => i.id !== id) });

  function pick(line: BasketLine, priceId: string) {
    const candidate = line.candidates.find((c) => c.id === priceId)!;
    const label = [candidate.commodity, candidate.specification].filter(Boolean).join(", ");
    onChange({ ...draft, items: draft.items.map((i) => (i.query === line.query ? { ...i, priceId, label, customPrice: undefined } : i)) });
  }

  async function share() {
    const lines = (result?.lines ?? []).map((l) => `${l.quantity} x ${l.label}${l.line_total ? ` - ${peso(l.line_total)}` : ""}`);
    const body = [draft.name || "My grocery list", ...lines, result ? `Total: ${peso(result.total)}` : ""].filter(Boolean).join("\n");
    if (navigator.share) {
      await navigator.share({ title: draft.name || "My grocery list", text: body }).catch(() => undefined);
    } else {
      await navigator.clipboard.writeText(body);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    }
  }

  function saveTrip() {
    if (!result) return;
    savePurchase({
      name: draft.name || "Shopping trip", total: result.total, budget,
      date: `${purchaseDate.getFullYear()}-${String(purchaseDate.getMonth() + 1).padStart(2, "0")}-${String(purchaseDate.getDate()).padStart(2, "0")}`,
      time: purchaseDate.toTimeString().slice(0, 5),
      lines: result.lines
        .filter((l) => l.line_total > 0)
        .map((l) => ({ name: l.status === "custom" ? l.query : l.label, quantity: l.quantity, unitPrice: l.unit_price, lineTotal: l.line_total })),
    });
    setSavedTrip(true);
  }

  async function sharePrices() {
    const store = city?.stores[Number(storeIndex)];
    if (!store || !city) return;
    const priced = draft.items.filter((i) => i.customPrice && i.customPrice > 0);
    try {
      const results = await Promise.all(priced.map((item) => postJson<{ held_for_review: boolean }>("/market/shelf-prices", {
        name: lineFor(item)?.label ?? item.query, store_name: store.name,
        latitude: store.latitude, longitude: store.longitude, city: city.city, price: item.customPrice,
      })));
      const held = results.filter((r) => r.held_for_review).length;
      setShareNote(`Thanks! ${priced.length - held} ${priced.length - held === 1 ? "price" : "prices"} shared with shoppers in ${city.city}.${held ? ` ${held} held for review.` : ""}`);
    } catch (e) {
      setShareNote((e as Error).message);
    }
  }

  const lineFor = (item: DraftItem) => result?.lines.find((l) => l.query === item.query);
  const full = draft.items.length >= MAX_ITEMS;
  const inCart = draft.items.some((i) => i.checked)
    ? (result?.lines ?? []).reduce((sum, l) => sum + (draft.items.find((i) => i.query === l.query)?.checked ? l.line_total : 0), 0)
    : null;

  return (
    <div className="workspace">
      <section className="panel list-panel">
        {header}
        <div className="adder">
          {bulk ? (
            <textarea rows={3} value={text} placeholder={"bear brand\n2 x tilapia\npiatos, mega sardines"} aria-label="Items to add" onChange={(e) => setText(e.target.value)} />
          ) : (
            <input type="text" value={text} placeholder="Add items, like piatos, 2 x tilapia" aria-label="Items to add"
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} />
          )}
          <button className="btn primary" onClick={add} disabled={!text.trim() || full}>Add</button>
        </div>
        {full && <p className="hint">A list can hold up to {MAX_ITEMS} items.</p>}
        {draft.items.length === 0 && <p className="muted empty">Nothing here yet. Add your first item above.</p>}

        {draft.items.length > 0 && (
          <ul className="items">
            {draft.items.map((item) => {
              const line = lineFor(item);
              const needsPrice = line?.status === "needs_price" || line?.status === "no_match" || line?.status === "reported" || item.customPrice !== undefined;
              return (
                <li key={item.id} className={item.checked ? "done" : ""}>
                  <input type="checkbox" checked={!!item.checked} aria-label={`${item.query} in cart`}
                    onChange={(e) => update(item.id, { checked: e.target.checked })} />
                  <span className="item-name">
                    {line?.status === "custom" ? item.query : line?.label ?? item.query}
                    {line?.selected && <small>{peso(line.selected.price)} per {line.selected.unit}</small>}
                    {line?.status === "needs_price" && <small>No price yet. Be the first to enter it.</small>}
                    {line?.status === "reported" && line.report && <small className="reported">₱{line.report.price.toFixed(2)} at {line.report.store_name}, {line.report.origin === "Open Prices" ? `Open Prices, ${new Date(line.report.reported_at).toLocaleDateString("en-PH", { dateStyle: "medium" })}` : "reported by a shopper"}</small>}
                    {line?.status === "no_match" && <small>Not in our lists. Enter a price to count it.</small>}
                    {line?.status === "matched" && line.candidates.length > 1 && (
                      <select className="swap" aria-label={`Change ${item.query}`} value={line.selected!.id} onChange={(e) => pick(line, e.target.value)}>
                        {!line.candidates.some((c) => c.id === line.selected!.id) && <option value={line.selected!.id}>{line.selected!.commodity}</option>}
                        {line.candidates.map((c) => <option key={c.id} value={c.id}>{c.commodity}{c.specification ? `, ${c.specification}` : ""} ({peso(c.price)})</option>)}
                      </select>
                    )}
                  </span>
                  {needsPrice && (
                    <span className="shelf-price">₱
                      <input type="number" min="0" step="0.25" inputMode="decimal" placeholder="Price" aria-label={`Shelf price of ${item.query}`}
                        value={item.customPrice ?? ""}
                        onChange={(e) => update(item.id, { customPrice: e.target.value === "" ? undefined : Number(e.target.value) })} />
                    </span>
                  )}
                  <span className="stepper">
                    <button aria-label={`Fewer ${item.query}`} disabled={item.quantity <= 1} onClick={() => update(item.id, { quantity: item.quantity - 1 })}>−</button>
                    <b>{item.quantity}</b>
                    <button aria-label={`More ${item.query}`} disabled={item.quantity >= 999} onClick={() => update(item.id, { quantity: item.quantity + 1 })}>+</button>
                  </span>
                  <button className="mini" aria-label={`Remove ${item.query}`} onClick={() => remove(item.id)}>✕</button>
                </li>
              );
            })}
          </ul>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        {draft.items.some((i) => i.customPrice) && (
          <div className="share-prices">
            <strong>Help other shoppers</strong>
            {city && city.stores.length > 0 ? (
              <>
                <p className="hint">Tell us where you saw these prices. Only the item, price and store are shared.</p>
                <div className="share-row">
                  <select aria-label="Store where you saw these prices" value={storeIndex} onChange={(e) => { setStoreIndex(e.target.value); setShareNote(null); }}>
                    <option value="">Choose the store</option>
                    {city.stores.map((store, index) => <option key={`${store.name}${store.latitude}`} value={index}>{store.name} ({store.distance_km.toFixed(1)} km)</option>)}
                  </select>
                  <button className="btn primary" disabled={storeIndex === ""} onClick={sharePrices}>Share prices</button>
                </div>
              </>
            ) : <p className="hint">Find your city on the Prices tab to share these prices.</p>}
            {shareNote && <p className="hint" role="status">{shareNote}</p>}
          </div>
        )}
        {footer}
      </section>

      <aside className="side">
        <Receipt draft={draft} data={result} inCart={inCart} />
        <BestStore items={draft.items.map((i) => i.query)} />
        {result && result.total > 0 && (
          <div className="save-trip">
            <DateTimePicker value={purchaseDate} onChange={(date) => { setPurchaseDate(date); setSavedTrip(false); }} />
            <button className="btn primary" disabled={savedTrip} onClick={saveTrip}>{savedTrip ? "Saved to Reports" : "Save this purchase"}</button>
          </div>
        )}
        {draft.items.length > 0 && (
          <div className="receipt-actions">
            <button className="btn" onClick={() => window.print()}>Print</button>
            <button className="btn" onClick={share}>{copied ? "Copied" : "Share list"}</button>
          </div>
        )}
        <Calculator onAdd={(name, price) => onChange(addItems(draft, [{ query: name, quantity: 1, customPrice: price }]))} />
      </aside>
    </div>
  );
}
