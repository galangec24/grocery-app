import { useState } from "react";

type Op = "+" | "-" | "×" | "÷";

const KEYS = ["7", "8", "9", "÷", "4", "5", "6", "×", "1", "2", "3", "-", "0", ".", "=", "+"];

function apply(a: number, b: number, op: Op) {
  if (op === "+") return a + b;
  if (op === "-") return a - b;
  if (op === "×") return a * b;
  return b === 0 ? NaN : a / b;
}

const tidy = (value: number) => (Number.isFinite(value) ? String(Math.round(value * 100) / 100) : "Error");

export function Calculator({ onAdd }: { onAdd: (name: string, price: number) => void }) {
  const [open, setOpen] = useState(false);
  const [entry, setEntry] = useState("0");
  const [stored, setStored] = useState<number | null>(null);
  const [op, setOp] = useState<Op | null>(null);
  const [fresh, setFresh] = useState(true);
  const [name, setName] = useState("");

  function press(key: string) {
    if (key === "=" || "+-×÷".includes(key)) {
      const current = Number(entry);
      const result = stored !== null && op && !fresh ? apply(stored, current, op) : current;
      setEntry(tidy(result));
      setStored(key === "=" || !Number.isFinite(result) ? null : result);
      setOp(key === "=" ? null : (key as Op));
      setFresh(true);
      return;
    }
    if (key === "." && !fresh && entry.includes(".")) return;
    setEntry(fresh ? (key === "." ? "0." : key) : entry === "0" && key !== "." ? key : entry + key);
    setFresh(false);
  }

  function clear() {
    setEntry("0");
    setStored(null);
    setOp(null);
    setFresh(true);
  }

  const value = Number(entry);
  const canAdd = name.trim() !== "" && Number.isFinite(value) && value > 0;

  if (!open) return <button className="btn block" onClick={() => setOpen(true)}>Open calculator</button>;

  return (
    <section className="calculator" aria-label="Calculator">
      <div className="calc-screen" aria-live="polite">
        <small>{stored !== null && op ? `${stored} ${op}` : " "}</small>
        <strong>{entry}</strong>
      </div>
      <div className="calc-keys">
        <button className="wide" onClick={clear}>Clear</button>
        <button onClick={() => { setEntry(entry.length > 1 ? entry.slice(0, -1) : "0"); }} aria-label="Delete last digit">⌫</button>
        {KEYS.map((key) => (
          <button key={key} className={"+-×÷=".includes(key) ? "op" : ""} onClick={() => press(key)}>{key}</button>
        ))}
      </div>
      <div className="calc-add">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Item name" aria-label="Item name for this amount" />
        <button className="btn primary" disabled={!canAdd} onClick={() => { onAdd(name.trim(), value); setName(""); clear(); }}>Add to receipt</button>
      </div>
      <button className="link" onClick={() => setOpen(false)}>Hide calculator</button>
    </section>
  );
}
