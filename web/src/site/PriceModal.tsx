import { useEffect, useRef, useState } from "react";
import { CatalogItem, PriceRow } from "../api";
import { longDate, peso } from "../format";

export type ModalSubject = { kind: "price"; row: PriceRow } | { kind: "brand"; item: CatalogItem };

function TrendChart({ row }: { row: PriceRow }) {
  const [hover, setHover] = useState<number | null>(null);
  const values = row.trend;
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
        <span>Last {values.length} reports</span>
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

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  return (
    <dialog ref={dialog} className="modal" onClose={onClose}
      onClick={(e) => { if (e.target === dialog.current) dialog.current?.close(); }}>
      <div className="modal-card">
        <button className="modal-close" aria-label="Close" onClick={() => dialog.current?.close()}>✕</button>
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
            <TrendChart row={subject.row} />
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
            <p className="muted">{subject.item.size} · {subject.item.category}</p>
            <p className="note">No official price is published for this product. Add it to your draft and enter the price on the shelf.</p>
          </>
        )}
        <button className="btn primary block" onClick={onAdd} disabled={added}>{added ? "Added to draft" : "Add to draft"}</button>
      </div>
    </dialog>
  );
}
