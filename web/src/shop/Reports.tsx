import { useEffect, useMemo, useState } from "react";
import { useBudget } from "../budget";
import { peso } from "../format";
import { deletePurchase, inRange, monthOf, monthsBetween, previousRange, Purchase, readPurchases, shiftMonth, sumTotal, topItems, toCsv } from "../purchases";

const thisMonth = () => new Date().toISOString().slice(0, 7);
const monthLabel = (month: string) =>
  new Date(`${month}-01T00:00:00`).toLocaleDateString("en-PH", { month: "short", year: "numeric" });

export function Reports() {
  const { setSpent } = useBudget();
  const [purchases, setPurchases] = useState<Purchase[]>(readPurchases);
  const now = thisMonth();
  const [from, setFrom] = useState(now);
  const [to, setTo] = useState(now);
  const [confirming, setConfirming] = useState<string | null>(null);
  useEffect(() => setSpent(0), [setSpent]);

  const year = now.slice(0, 4);
  const presets: [string, string, string][] = [
    ["This month", now, now],
    ["Last month", shiftMonth(now, -1), shiftMonth(now, -1)],
    ["Last 3 months", shiftMonth(now, -2), now],
    ["Last 6 months", shiftMonth(now, -5), now],
    ["This year", `${year}-01`, `${year}-12`],
    ["Last year", `${Number(year) - 1}-01`, `${Number(year) - 1}-12`],
  ];

  const start = from <= to ? from : to;
  const end = from <= to ? to : from;
  const months = monthsBetween(start, end);
  const shown = useMemo(() => inRange(purchases, start, end), [purchases, start, end]);
  const [priorFrom, priorTo] = previousRange(start, end);
  const total = sumTotal(shown);
  const prior = sumTotal(inRange(purchases, priorFrom, priorTo));
  const top = topItems(shown);

  const byMonth = months.map((month) => ({ month, total: sumTotal(shown.filter((p) => monthOf(p.date) === month)) }));
  const peak = Math.max(...byMonth.map((m) => m.total), 1);

  function exportCsv() {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([toCsv(shown)], { type: "text/csv" }));
    link.download = `grocery-report-${start}-to-${end}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  const change = total - prior;

  return (
    <div className="reports">
      <section className="panel">
        <div className="presets" role="group" aria-label="Report period">
          {presets.map(([label, a, b]) => (
            <button key={label} className={`chip${start === a && end === b ? " on" : ""}`} onClick={() => { setFrom(a); setTo(b); }}>{label}</button>
          ))}
        </div>
        <div className="range">
          <label>From<input type="month" value={from} onChange={(e) => e.target.value && setFrom(e.target.value)} /></label>
          <label>To<input type="month" value={to} onChange={(e) => e.target.value && setTo(e.target.value)} /></label>
          <button className="btn" onClick={exportCsv} disabled={shown.length === 0}>Export CSV</button>
          <button className="btn" onClick={() => window.print()} disabled={shown.length === 0}>Print</button>
        </div>
      </section>

      <div className="tiles3d">
        <div className="tile3d"><span>Spent in this period</span><strong className="date">{peso(total)}</strong><small>{monthLabel(start)}{start !== end ? ` to ${monthLabel(end)}` : ""}</small></div>
        <div className="tile3d"><span>Previous period</span><strong className="date">{peso(prior)}</strong><small>{monthLabel(priorFrom)}{priorFrom !== priorTo ? ` to ${monthLabel(priorTo)}` : ""}</small></div>
        <div className="tile3d">
          <span>Change</span>
          <strong className="date">{prior === 0 ? "No earlier data" : <b className={change > 0 ? "up" : change < 0 ? "down" : ""}>{change > 0 ? "▲" : change < 0 ? "▼" : ""} {peso(Math.abs(change))}</b>}</strong>
          <small>{prior > 0 ? `${Math.abs(Math.round((change / prior) * 100))}% ${change >= 0 ? "more" : "less"} than before` : "Save more purchases to compare"}</small>
        </div>
        <div className="tile3d"><span>Purchases saved</span><strong>{shown.length}</strong><small>{shown.length ? `${peso(total / shown.length)} on average` : "None in this period"}</small></div>
      </div>

      {purchases.length === 0 ? (
        <section className="panel"><p className="muted empty">No purchases saved yet. Finish a list, then click Save this purchase on the receipt.</p></section>
      ) : (
        <>
          {months.length > 1 && (
            <section className="panel">
              <h2>Spending by month</h2>
              <div className="month-chart" role="img" aria-label={`Spending by month, highest ${peso(peak)}`}>
                {byMonth.map((m) => (
                  <div className="month-col" key={m.month} title={`${monthLabel(m.month)}: ${peso(m.total)}`}>
                    <span className="month-value">{m.total ? peso(m.total) : ""}</span>
                    <span className="month-bar" style={{ height: `${(m.total / peak) * 100}%` }} />
                    <small>{monthLabel(m.month).split(" ")[0]}</small>
                  </div>
                ))}
              </div>
            </section>
          )}

          <div className="two-col">
            <section className="panel">
              <h2>Where the money went</h2>
              {top.length === 0 && <p className="muted">Nothing in this period.</p>}
              <table>
                <tbody>
                  {top.map((item) => (
                    <tr key={item.name}><td className="wrap">{item.name}</td><td className="num">× {item.quantity}</td><td className="num">{peso(item.spent)}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="panel">
              <h2>Saved purchases</h2>
              {shown.length === 0 && <p className="muted">Nothing in this period.</p>}
              <ul className="plain">
                {shown.map((p) => (
                  <li className="purchase-row" key={p.id}>
                    <span><b>{p.name}</b><small>{new Date(`${p.date}T00:00:00`).toLocaleDateString("en-PH", { dateStyle: "medium" })} · {p.lines.length} items</small></span>
                    <span className="price">{peso(p.total)}</span>
                    {confirming === p.id ? (
                      <button className="mini danger" onClick={() => { deletePurchase(p.id); setPurchases(readPurchases()); setConfirming(null); }}>Delete</button>
                    ) : (
                      <button className="mini" aria-label={`Delete ${p.name}`} onClick={() => setConfirming(p.id)}>✕</button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
