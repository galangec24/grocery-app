import { useEffect, useRef, useState } from "react";

const WEEK = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
const pad = (n: number) => String(n).padStart(2, "0");
const iso = (date: Date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

export function DateTimePicker({ value, onChange }: { value: Date; onChange: (date: Date) => void }) {
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(new Date(value.getFullYear(), value.getMonth(), 1));
  const holder = useRef<HTMLDivElement>(null);
  const today = new Date();

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!holder.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const lead = month.getDay();
  const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const days = Array.from({ length: count }, (_, i) => new Date(month.getFullYear(), month.getMonth(), i + 1));
  const atLatest = month.getFullYear() === today.getFullYear() && month.getMonth() === today.getMonth();

  function pick(day: Date) {
    const next = new Date(day);
    next.setHours(value.getHours(), value.getMinutes());
    onChange(next);
  }

  function time(hours: number, minutes: number) {
    const next = new Date(value);
    next.setHours(hours, minutes);
    onChange(next);
  }

  const hour12 = value.getHours() % 12 || 12;
  const pm = value.getHours() >= 12;
  const setHour = (hour: number, afternoon: boolean) => time((hour % 12) + (afternoon ? 12 : 0), value.getMinutes());

  return (
    <div className="dt-picker" ref={holder}>
      <button type="button" className="dt-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span aria-hidden>🗓</span>
        <span>
          <small>Date of purchase</small>
          {value.toLocaleDateString("en-PH", { dateStyle: "medium" })}, {value.toLocaleTimeString("en-PH", { hour: "numeric", minute: "2-digit" })}
        </span>
      </button>
      {open && (
        <div className="dt-panel" role="dialog" aria-label="Choose date and time">
          <div className="dt-head">
            <button type="button" aria-label="Previous month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>‹</button>
            <strong>{month.toLocaleDateString("en-PH", { month: "long", year: "numeric" })}</strong>
            <button type="button" aria-label="Next month" disabled={atLatest} onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>›</button>
          </div>
          <div className="dt-grid">
            {WEEK.map((d) => <span key={d} className="dt-week">{d}</span>)}
            {Array.from({ length: lead }, (_, i) => <span key={`blank${i}`} />)}
            {days.map((day) => (
              <button type="button" key={iso(day)} disabled={day > today}
                className={`${iso(day) === iso(value) ? "on" : ""}${iso(day) === iso(today) ? " today" : ""}`}
                onClick={() => pick(day)}>
                {day.getDate()}
              </button>
            ))}
          </div>
          <div className="dt-time">
            <select aria-label="Hour" value={hour12} onChange={(e) => setHour(Number(e.target.value), pm)}>
              {Array.from({ length: 12 }, (_, i) => <option key={i + 1}>{i + 1}</option>)}
            </select>
            <span>:</span>
            <select aria-label="Minute" value={Math.floor(value.getMinutes() / 5) * 5} onChange={(e) => time(value.getHours(), Number(e.target.value))}>
              {Array.from({ length: 12 }, (_, i) => <option key={i} value={i * 5}>{pad(i * 5)}</option>)}
            </select>
            <div className="dt-ampm">
              <button type="button" className={pm ? "" : "on"} onClick={() => setHour(hour12, false)}>AM</button>
              <button type="button" className={pm ? "on" : ""} onClick={() => setHour(hour12, true)}>PM</button>
            </div>
          </div>
          <button type="button" className="btn primary block" onClick={() => setOpen(false)}>Done</button>
        </div>
      )}
    </div>
  );
}
