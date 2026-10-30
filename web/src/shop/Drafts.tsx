import { useEffect, useRef, useState } from "react";
import { BasketLine, BasketResponse, postJson } from "../api";
import { addItems, deleteDraft, Draft, DraftItem, MAX_ITEMS, newDraft, parseItems, readDrafts, saveDraft, useDrafts } from "../drafts";
import { peso } from "../format";
import { useLocation } from "../location";
import { navigate } from "../router";

/** The Multi search tab: type or paste a list, total it, and optionally keep it as a draft. */
export function QuickCompare() {
  const [draft, setDraft] = useState<Draft>(() => newDraft());
  return (
    <>
      <h1>Search multiple items</h1>
      <p className="muted">Type or paste your list. One item per line, or separate with commas.</p>
      <ListEditor draft={draft} onChange={setDraft} bulk />
      {draft.items.length > 0 && (
        <button className="btn block" onClick={() => navigate(`/shop/drafts/${saveDraft({ ...draft, name: draft.name || "My list" }).id}`)}>
          Save as draft
        </button>
      )}
    </>
  );
}

export function DraftList() {
  const { drafts, reload } = useDrafts();
  const [confirming, setConfirming] = useState<string | null>(null);

  return (
    <>
      <h1>Drafts</h1>
      <p className="muted">Lists you're still working on. Saved on this device only.</p>
      <button className="btn primary block" onClick={() => navigate(`/shop/drafts/${saveDraft(newDraft()).id}`)}>New draft</button>
      {drafts.length === 0 && <p className="muted empty">No drafts yet. Start one, or save a list from Multi search.</p>}
      {drafts.map((d) => (
        <div className="draft-row" key={d.id}>
          <a href={`#/shop/drafts/${d.id}`}>
            <strong>{d.name || "Untitled draft"}</strong>
            <small>{d.items.length} {d.items.length === 1 ? "item" : "items"} · edited {new Date(d.updatedAt).toLocaleDateString()}</small>
          </a>
          {confirming === d.id ? (
            <span className="confirm">
              <button className="mini danger" onClick={() => { deleteDraft(d.id); setConfirming(null); reload(); }}>Delete</button>
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
    <>
      <a className="link" href="#/shop/drafts">‹ Drafts</a>
      <input className="title-input" placeholder="Name this draft" aria-label="Draft name" value={draft.name}
        onChange={(e) => change({ ...draft, name: e.target.value })} />
      <p className="hint">{saved ? "Saved on this device" : "Saving…"}</p>
      <ListEditor draft={draft} onChange={change} />
    </>
  );
}

function ListEditor({ draft, onChange, bulk }: { draft: Draft; onChange: (draft: Draft) => void; bulk?: boolean }) {
  const { city } = useLocation();
  const [text, setText] = useState("");
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
      setResult(await postJson<BasketResponse>("/market/basket", {
        items: items.map((i) => ({ query: i.query, quantity: i.quantity, price_id: i.priceId })),
        ...(city ? { island: city.island } : {}),
      }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function pick(line: BasketLine, priceId: string) {
    const candidate = line.candidates.find((c) => c.id === priceId)!;
    const label = [candidate.commodity, candidate.specification].filter(Boolean).join(", ");
    const items = draft.items.map((i) => (i.query === line.query ? { ...i, priceId, label } : i));
    onChange({ ...draft, items });
    compare(items);
  }

  const full = draft.items.length >= MAX_ITEMS;

  return (
    <>
      <div className="adder">
        {bulk ? (
          <textarea rows={4} value={text} placeholder={"bear brand\n2 x tilapia\neggs, sardines"} aria-label="Items to add" onChange={(e) => setText(e.target.value)} />
        ) : (
          <input type="text" value={text} placeholder="Add items, separated by commas" aria-label="Items to add"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} />
        )}
        <button className="btn" onClick={add} disabled={!text.trim() || full}>Add</button>
      </div>
      {full && <p className="hint">A list can hold up to {MAX_ITEMS} items.</p>}
      {draft.items.length === 0 && !bulk && <p className="muted empty">Nothing here yet. Add your first item above.</p>}

      {draft.items.length > 0 && (
        <>
          <ul className="items">
            {draft.items.map((item) => (
              <li key={item.id}>
                <span className="item-name">{item.query}{item.label && item.label !== item.query && <small>{item.label}</small>}</span>
                <span className="stepper">
                  <button aria-label={`Fewer ${item.query}`} disabled={item.quantity <= 1} onClick={() => update(item.id, { quantity: item.quantity - 1 })}>−</button>
                  <b>{item.quantity}</b>
                  <button aria-label={`More ${item.query}`} disabled={item.quantity >= 999} onClick={() => update(item.id, { quantity: item.quantity + 1 })}>+</button>
                </span>
                <button className="mini" aria-label={`Remove ${item.query}`} onClick={() => remove(item.id)}>✕</button>
              </li>
            ))}
          </ul>
          <button className="btn primary block" disabled={busy} onClick={() => compare()}>
            {busy ? "Totalling…" : `Total ${draft.items.length} ${draft.items.length === 1 ? "item" : "items"}`}
          </button>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {result && <Basket data={result} onPick={pick} />}
    </>
  );
}

function Basket({ data, onPick }: { data: BasketResponse; onPick: (line: BasketLine, id: string) => void }) {
  return (
    <div className="basket">
      <div className="basket-total">
        <span>Estimated total at official prices</span>
        <strong>{peso(data.total)}</strong>
        <small>{data.items_matched} of {data.lines.length} items found</small>
      </div>
      {data.lines.map((line) => line.status === "no_match" ? (
        <p className="warn" key={line.query}>▲ <b>{line.query}</b>: not in the official lists, so it isn't in the total.</p>
      ) : (
        <div className="basket-line" key={line.query}>
          <div>
            <strong>{line.selected!.commodity}{line.selected!.specification ? `, ${line.selected!.specification}` : ""}</strong>
            <small>{peso(line.selected!.price)} per {line.selected!.unit} × {line.quantity} · {line.selected!.source_label}</small>
          </div>
          <span className="price">{peso(line.line_total)}</span>
          {line.candidates.length > 1 && (
            <label className="inline-field">Change item
              <select value={line.selected!.id} onChange={(e) => onPick(line, e.target.value)}>
                {!line.candidates.some((c) => c.id === line.selected!.id) && <option value={line.selected!.id}>{line.selected!.commodity}</option>}
                {line.candidates.map((c) => (
                  <option key={c.id} value={c.id}>{c.commodity}{c.specification ? `, ${c.specification}` : ""} ({peso(c.price)})</option>
                ))}
              </select>
            </label>
          )}
        </div>
      ))}
      <p className="hint">Market prices are Metro Manila averages per kilo or piece. Quantities count those units. Shelf prices may differ.</p>
    </div>
  );
}
