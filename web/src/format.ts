import type { PriceStatus } from "./site/Dashboard";

export const peso = (value: number) =>
  `₱${value.toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export const longDate = (iso: string | null) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-PH", { month: "long", day: "numeric", year: "numeric" }) : "Not loaded yet";

export const STATUS_META: Record<PriceStatus, { label: string; icon: string }> = {
  fresh: { label: "Fresh", icon: "●" },
  aging: { label: "Aging", icon: "◐" },
  stale: { label: "Stale", icon: "▲" },
  unavailable: { label: "Unavailable", icon: "✕" },
  unknown: { label: "Unknown", icon: "?" },
};

export const mapUrl = (latitude: number, longitude: number) =>
  `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
