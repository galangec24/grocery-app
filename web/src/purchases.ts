/** Saved shopping trips. Kept on the device, like drafts, so no account is needed. */
export interface PurchaseLine {
  name: string;
  quantity: number;
  unitPrice: number;
  lineTotal: number;
}

export interface Purchase {
  id: string;
  name: string;
  date: string; // YYYY-MM-DD
  total: number;
  budget: number | null;
  lines: PurchaseLine[];
}

const KEY = "purchases_v1";

export function readPurchases(): Purchase[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? "[]") as Purchase[];
    return parsed.sort((a, b) => b.date.localeCompare(a.date));
  } catch {
    return [];
  }
}

export function savePurchase(purchase: Omit<Purchase, "id">): Purchase {
  const saved = { ...purchase, id: crypto.randomUUID() };
  localStorage.setItem(KEY, JSON.stringify([saved, ...readPurchases()]));
  return saved;
}

export function deletePurchase(id: string) {
  localStorage.setItem(KEY, JSON.stringify(readPurchases().filter((p) => p.id !== id)));
}

export const monthOf = (date: string) => date.slice(0, 7);

export function monthsBetween(from: string, to: string): string[] {
  const months: string[] = [];
  let [year, month] = from.split("-").map(Number);
  const [endYear, endMonth] = to.split("-").map(Number);
  while ((year < endYear || (year === endYear && month <= endMonth)) && months.length < 120) {
    months.push(`${year}-${String(month).padStart(2, "0")}`);
    month += 1;
    if (month > 12) { month = 1; year += 1; }
  }
  return months;
}

export function shiftMonth(month: string, by: number): string {
  const [year, m] = month.split("-").map(Number);
  const date = new Date(year, m - 1 + by, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

/** The period of equal length just before the chosen one, for comparison. */
export function previousRange(from: string, to: string): [string, string] {
  const length = monthsBetween(from, to).length;
  return [shiftMonth(from, -length), shiftMonth(from, -1)];
}

export const inRange = (purchases: Purchase[], from: string, to: string) =>
  purchases.filter((p) => monthOf(p.date) >= from && monthOf(p.date) <= to);

export const sumTotal = (purchases: Purchase[]) =>
  Math.round(purchases.reduce((sum, p) => sum + p.total, 0) * 100) / 100;

export function topItems(purchases: Purchase[], limit = 8) {
  const items = new Map<string, { name: string; quantity: number; spent: number }>();
  for (const line of purchases.flatMap((p) => p.lines)) {
    const entry = items.get(line.name) ?? { name: line.name, quantity: 0, spent: 0 };
    entry.quantity += line.quantity;
    entry.spent += line.lineTotal;
    items.set(line.name, entry);
  }
  return [...items.values()].sort((a, b) => b.spent - a.spent).slice(0, limit);
}

export function toCsv(purchases: Purchase[]): string {
  const cell = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`;
  const rows = [["Date", "Purchase", "Item", "Quantity", "Unit price", "Line total"].map(cell).join(",")];
  for (const p of purchases) {
    for (const l of p.lines) rows.push([p.date, p.name, l.name, l.quantity, l.unitPrice, l.lineTotal].map(cell).join(","));
  }
  return rows.join("\r\n");
}
