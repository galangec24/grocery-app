import { Preferences } from "@capacitor/preferences";
import { useCallback, useEffect, useState } from "react";

/** Drafts live on the device so shoppers can use them without an account (spec 3.1). */
export interface DraftItem {
  id: string;
  query: string;
  quantity: number;
  productId?: string;
  productLabel?: string;
}

export interface Draft {
  id: string;
  name: string;
  items: DraftItem[];
  updatedAt: string;
}

const KEY = "drafts_v1";
export const MAX_ITEMS = 30;

export const newId = () => crypto.randomUUID();

export function newDraft(name = ""): Draft {
  return { id: newId(), name, items: [], updatedAt: new Date().toISOString() };
}

export async function readDrafts(): Promise<Draft[]> {
  const { value } = await Preferences.get({ key: KEY });
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as Draft[];
    return parsed.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  } catch {
    return [];
  }
}

async function writeDrafts(drafts: Draft[]) {
  await Preferences.set({ key: KEY, value: JSON.stringify(drafts) });
}

export async function saveDraft(draft: Draft) {
  const drafts = await readDrafts();
  const stamped = { ...draft, updatedAt: new Date().toISOString() };
  await writeDrafts([stamped, ...drafts.filter((d) => d.id !== draft.id)]);
  return stamped;
}

export async function deleteDraft(id: string) {
  await writeDrafts((await readDrafts()).filter((d) => d.id !== id));
}

export function useDrafts() {
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const reload = useCallback(() => {
    readDrafts().then(setDrafts);
  }, []);
  useEffect(reload, [reload]);
  return { drafts, reload };
}

/** Splits pasted text on new lines or commas. "2 x milk", "milk x2" and "3 eggs" set quantity. */
export function parseItems(text: string): { query: string; quantity: number }[] {
  const merged = new Map<string, { query: string; quantity: number }>();
  for (const raw of text.split(/[\n,]+/)) {
    let line = raw.trim();
    if (!line) continue;
    let quantity = 1;
    const leading = line.match(/^(\d{1,3})\s*x\s+(.+)$/i) ?? line.match(/^(\d{1,3})\s+(?![a-z]*\s*$)(?=[a-z])(.+)$/i);
    const trailing = line.match(/^(.+?)\s*x\s*(\d{1,3})$/i);
    if (leading && !/^(kg|g|l|ml|pcs?|pieces?)\b/i.test(leading[2])) {
      quantity = Number(leading[1]);
      line = leading[2];
    } else if (trailing) {
      quantity = Number(trailing[2]);
      line = trailing[1];
    }
    const key = line.toLowerCase();
    const existing = merged.get(key);
    if (existing) existing.quantity += Math.max(quantity, 1);
    else merged.set(key, { query: line, quantity: Math.max(quantity, 1) });
  }
  return [...merged.values()];
}

/** Adds to a draft, raising the quantity instead of duplicating an existing item. */
export function addItems(draft: Draft, additions: Omit<DraftItem, "id">[]): Draft {
  const items = [...draft.items];
  for (const addition of additions) {
    const index = items.findIndex((i) => i.query.toLowerCase() === addition.query.toLowerCase());
    if (index >= 0) items[index] = { ...items[index], quantity: Math.min(items[index].quantity + addition.quantity, 999) };
    else if (items.length < MAX_ITEMS) items.push({ ...addition, id: newId() });
  }
  return { ...draft, items };
}
