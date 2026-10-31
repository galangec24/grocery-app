import { useEffect, useRef, useState } from "react";
import { api, CatalogItem, PricePoint, PriceRow, query, Suggestion } from "../api";
import { Icon } from "../icons";
import { ProductImage } from "../SearchBox";
import { longDate, peso } from "../format";

export type ModalSubject = { kind: "price"; row: PriceRow } | { kind: "brand"; item: CatalogItem };

function GuidePrice({ item }: { item: CatalogItem }) {
  const guess = item.auto_price;
  if (!guess) return <p className="note">No price yet. Add it to your list and enter the shelf price.</p>;
  return (
    <>
      <p className="modal-price">≈ {guess.low ? `${peso(guess.low)} to ${peso(guess.high ?? guess.price)}` : peso(guess.price)}</p>
      <p className="note">{guess.label}. Seen the real price? Add it to your list and share it to help other shoppers.</p>
    </>
  );
}

function BrandPrices({ item }: { item: CatalogItem }) {
  const [points, setPoints] = useState<PricePoint[] | null>(null);

  useEffect(() => {
    api<{ points: PricePoint[] }>(`/market/catalog/${encodeURIComponent(item.id)}/prices`)
      .then((r) => setPoints(r.points)).catch(() => setPoints([]));
  }, [item.id]);

  if (points === null) return <p className="muted">Checking for prices…</p>;
  if (points.length === 0) return <GuidePrice item={item} />;
  const latest = points[points.length - 1];
  return (
    <>
      <p className="modal-price">{peso(latest.price)}</p>
      <p className="muted">{latest.store}, {longDate(latest.date.slice(0, 10))} ({latest.origin})</p>
      <TrendChart values={points.map((p) => p.price)} label="Reported prices" />
      <ul className="plain">
        {[...points].reverse().slice(0, 6).map((p) => (
          <li className="purchase-row" key={p.date + p.store}>
            <span>{p.store}<small>{longDate(p.date.slice(0, 10))} · {p.origin}</small></span>
            <span className="price">{peso(p.price)}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function TrendChart({ values, label }: { values: number[]; label: string }) {
  const [hover, setHover] = useState<number | null>(null);
  if (values.length < 2) return null;
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const width = 480;
  const height = 130;
  const x = (i: number) => 8 + (i / (values.length - 1)) * (width - 16);
  const y = (v: number) => height - 12 - ((v - low) / span) * (height - 28);
  const shown = hover ?? values.length - 1;

  return (
    <figure className="trend">
      <figcaption>
        <span>{label}</span>
        <b>{peso(values[shown])}</b>
      </figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Price from ${peso(values[0])} to ${peso(values[values.length - 1])}`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          setHover(Math.round(((e.clientX - box.left) / box.width) * (values.length - 1)));
        }}>
        <polyline points={values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <line x1={x(shown)} x2={x(shown)} y1="6" y2={height - 6} className="trend-cursor" />
        <circle cx={x(shown)} cy={y(values[shown])} r="5" fill="currentColor" stroke="#fff" strokeWidth="2" />
      </svg>
      <p className="hint">Lowest {peso(low)}, highest {peso(high)}</p>
    </figure>
  );
}

export function PriceModal({ subject, onClose, onAdd, added }: {
  subject: ModalSubject; onClose: () => void; onAdd: () => void; added: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [photo, setPhoto] = useState(subject.kind === "brand" ? subject.item.image_url : null);
  const name = subject.kind === "price" ? subject.row.commodity : subject.item.name;
  const category = subject.kind === "price" ? subject.row.category : subject.item.category;

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  useEffect(() => {
    if (photo) return;
    api<Suggestion[]>(`/market/suggest${query({ q: name, limit: 3 })}`)
      .then((found) => setPhoto(found.find((f) => f.image_url)?.image_url ?? null))
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name]);

  return (
    <dialog ref={dialog} className="modal" onClose={onClose}
      onClick={(e) => { if (e.target === dialog.current) dialog.current?.close(); }}>
      <div className="modal-card">
        <button className="modal-close" aria-label="Close" onClick={() => dialog.current?.close()}><Icon name="close" size={18} /></button>
        <ProductImage src={photo} category={`${category} ${name}`} large />
        {subject.kind === "price" ? (
          <>
            <p className="modal-kind">{subject.row.kind === "srp" ? "Official standard price" : "Daily market price"}</p>
            <h2>{subject.row.commodity}</h2>
            {subject.row.specification && <p className="muted">{subject.row.specification}</p>}
            <p className="modal-price">{peso(subject.row.price)}<small> per {subject.row.unit}</small></p>
            {subject.row.change !== null && subject.row.change !== 0 && (
              <p className={subject.row.change > 0 ? "up" : "down"}>
                {subject.row.change > 0 ? "▲" : "▼"} {peso(Math.abs(subject.row.change))} since the last report
              </p>
            )}
            <TrendChart values={subject.row.trend} label={`Last ${subject.row.trend.length} reports`} />
            <dl>
              <div><dt>Category</dt><dd>{subject.row.category}</dd></div>
              <div><dt>Applies to</dt><dd>{subject.row.region}</dd></div>
              <div><dt>Source</dt><dd>{subject.row.source_label}</dd></div>
              <div><dt>Report date</dt><dd>{longDate(subject.row.report_date)}</dd></div>
            </dl>
            <a className="link" href={subject.row.source_url} target="_blank" rel="noreferrer">View the official document</a>
          </>
        ) : (
          <>
            <p className="modal-kind">Found in stores</p>
            <h2>{subject.item.name}</h2>
            <p className="muted">{subject.item.variant && `${subject.item.variant}, `}{subject.item.size} · {subject.item.category}</p>
            <BrandPrices item={subject.item} />
          </>
        )}
        <button className="btn primary block with-icon" onClick={onAdd} disabled={added}><Icon name={added ? "check" : "plus"} />{added ? "Added to draft" : "Add to draft"}</button>
      </div>
    </dialog>
  );
}
