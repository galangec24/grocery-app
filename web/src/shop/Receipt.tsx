import { BasketResponse } from "../api";
import { useBudget } from "../budget";
import { Draft } from "../drafts";
import { peso } from "../format";

export function Receipt({ draft, data, inCart }: { draft: Draft; data: BasketResponse | null; inCart: number | null }) {
  const { budget } = useBudget();
  const left = budget === null ? null : budget - (data?.total ?? 0);
  const waiting = data?.lines.filter((l) => l.status === "needs_price" || l.status === "no_match") ?? [];

  return (
    <div className="receipt" aria-label="Receipt">
      <header>
        <strong>GROCERY PRICE FINDER</strong>
        <span>{draft.name || "Shopping list"}</span>
        <span>{new Date().toLocaleString("en-PH", { dateStyle: "medium", timeStyle: "short" })}</span>
      </header>
      <div className="rule" />
      {(!data || data.lines.length === 0) && <p className="receipt-empty">Your items will print here.</p>}
      {data?.lines.filter((l) => l.status === "matched" || l.status === "custom").map((line) => (
        <div className={`receipt-line${draft.items.find((i) => i.query === line.query)?.checked ? " done" : ""}`} key={line.query}>
          <span className="name">{line.status === "custom" ? line.query : line.label}</span>
          <span>{line.quantity} x {line.unit_price.toFixed(2)}{line.status === "custom" ? " *" : ""}</span>
          <span>{line.line_total.toFixed(2)}</span>
        </div>
      ))}
      {waiting.length > 0 && <div className="rule" />}
      {waiting.map((line) => (
        <div className="receipt-line waiting" key={line.query}>
          <span className="name">{line.label}</span>
          <span>{line.quantity} x ?</span>
          <span>--</span>
        </div>
      ))}
      {data && data.lines.length > 0 && (
        <>
          <div className="rule double" />
          <div className="receipt-sum total"><span>TOTAL</span><span>{peso(data.total)}</span></div>
          {inCart !== null && <div className="receipt-sum"><span>IN CART</span><span>{peso(inCart)}</span></div>}
          {budget !== null && <div className="receipt-sum"><span>BUDGET</span><span>{peso(budget)}</span></div>}
          {left !== null && <div className={`receipt-sum${left < 0 ? " over" : ""}`}><span>{left < 0 ? "OVER BY" : "LEFT"}</span><span>{peso(Math.abs(left))}</span></div>}
          <div className="rule" />
          <p className="receipt-note">{data.items_matched} of {data.lines.length} items counted{waiting.length ? ", others need a price" : ""}</p>
          <p className="receipt-note">* Your own shelf price. Others are official prices and may differ at checkout.</p>
        </>
      )}
    </div>
  );
}
