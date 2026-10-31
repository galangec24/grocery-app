import { useEffect, useId, useRef, useState } from "react";
import { api, query, Suggestion } from "./api";
import { peso } from "./format";
import { Icon } from "./icons";
import { useLocation } from "./location";

const PICTURES: [RegExp, string][] = [
  [/rice|corn|grain|legume/i, "🍚"], [/fish|seafood|sardine|tuna/i, "🐟"], [/beef|pork|meat|livestock/i, "🥩"],
  [/poultry|chicken|egg/i, "🍗"], [/vegetable/i, "🥦"], [/fruit/i, "🍌"], [/spice|condiment|sauce|vinegar/i, "🧂"],
  [/milk|dairy/i, "🥛"], [/coffee|tea/i, "☕"], [/water|beverage|drink|juice/i, "🥤"], [/bread|bakery/i, "🍞"],
  [/noodle|pasta/i, "🍜"], [/snack|junk|chip|biscuit|candy|chocolate/i, "🍿"], [/pet|dog|cat/i, "🐾"],
  [/perfume|beauty|fragrance|soap|personal/i, "🧴"], [/baby|diaper/i, "🍼"], [/appliance/i, "🔌"],
  [/kitchen|utensil/i, "🍳"], [/candle/i, "🕯️"], [/battery|batteries/i, "🔋"], [/school|office/i, "✏️"],
];

/** A product photo, or a picture for its category when no photo exists. */
export function ProductImage({ src, category, large }: { src?: string | null; category?: string; large?: boolean }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  const className = `product-image${large ? " large" : ""}`;
  if (src && !failed) return <img className={className} src={src} alt="" loading="lazy" onError={() => setFailed(true)} />;
  const picture = PICTURES.find(([pattern]) => pattern.test(category ?? ""))?.[1] ?? "🛒";
  return <span className={`${className} placeholder`} aria-hidden="true">{picture}</span>;
}

/** Search as you type, with a photo and the best known price on every result. */
export function SearchBox({ value, onChange, onPick, onSubmit, placeholder, label }: {
  value: string;
  onChange: (text: string) => void;
  onPick: (item: Suggestion) => void;
  onSubmit?: (text: string) => void;
  placeholder: string;
  label: string;
}) {
  const { city } = useLocation();
  const [items, setItems] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [busy, setBusy] = useState(false);
  const holder = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    const text = value.trim();
    if (!text) { setItems([]); setBusy(false); return; }
    let live = true;
    setBusy(true);
    const timer = setTimeout(() => {
      api<Suggestion[]>(`/market/suggest${query({ q: text, island: city?.island, city: city?.city, limit: 8 })}`)
        .then((found) => { if (live) { setItems(found); setActive(-1); } })
        .catch(() => { if (live) setItems([]); })
        .finally(() => { if (live) setBusy(false); });
    }, 220);
    return () => { live = false; clearTimeout(timer); };
  }, [value, city?.island, city?.city]);

  useEffect(() => {
    const close = (event: MouseEvent) => { if (!holder.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function pick(item: Suggestion) {
    setOpen(false);
    onPick(item);
  }

  function onKey(event: React.KeyboardEvent) {
    if (event.key === "Escape") setOpen(false);
    if (event.key === "ArrowDown" && items.length) { event.preventDefault(); setOpen(true); setActive((active + 1) % items.length); }
    if (event.key === "ArrowUp" && items.length) { event.preventDefault(); setActive((active - 1 + items.length) % items.length); }
    if (event.key === "Enter") {
      event.preventDefault();
      if (open && active >= 0) pick(items[active]);
      else if (onSubmit && value.trim()) { setOpen(false); onSubmit(value); }
    }
  }

  return (
    <div className="searchbox" ref={holder}>
      <Icon name="search" />
      <input type="search" role="combobox" aria-expanded={open && items.length > 0} aria-controls={listId} aria-label={label} aria-autocomplete="list"
        value={value} placeholder={placeholder} autoComplete="off"
        onChange={(e) => { onChange(e.target.value); setActive(-1); setOpen(true); }}
        onFocus={() => setOpen(true)} onKeyDown={onKey} />
      {open && value.trim() !== "" && (
        <ul className="suggestions" id={listId} role="listbox">
          {items.map((item, index) => (
            <li key={item.id} role="option" aria-selected={index === active} className={index === active ? "on" : ""}
              onMouseEnter={() => setActive(index)} onMouseDown={(e) => { e.preventDefault(); pick(item); }}>
              <ProductImage src={item.image_url} category={`${item.category} ${item.name}`} />
              <span className="suggest-name">
                <strong>{item.name}</strong>
                <small>{[item.size, item.category].filter(Boolean).join(" · ")}</small>
              </span>
              <span className="suggest-price">
                {item.price !== null ? <b>{item.kind === "product" && item.price_label?.startsWith("Estimate") ? "≈ " : ""}{peso(item.price)}</b> : <em>Add a price</em>}
                <small>{item.price_label}</small>
              </span>
            </li>
          ))}
          {!busy && items.length === 0 && <li className="suggest-empty">No match. Press Enter to add it anyway.</li>}
          {busy && items.length === 0 && <li className="suggest-empty">Searching…</li>}
        </ul>
      )}
    </div>
  );
}
