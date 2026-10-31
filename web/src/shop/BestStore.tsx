import { useEffect, useMemo, useState } from "react";
import { BestStores, postJson } from "../api";
import { peso, timeAgo } from "../format";
import { useLocation } from "../location";
import { RouteMap } from "../StoreMap";

export function BestStore({ items, total, official }: { items: string[]; total: number; official: number }) {
  const { city, position } = useLocation();
  const [data, setData] = useState<BestStores | null>(null);
  const signature = useMemo(() => JSON.stringify(items), [items]);

  useEffect(() => {
    if (items.length === 0) { setData(null); return; }
    let live = true;
    const timer = setTimeout(() => {
      postJson<BestStores>("/market/best-stores", {
        items, city: city?.city,
        ...(position ? { latitude: position.latitude, longitude: position.longitude } : {}),
      }).then((r) => { if (live) setData(r); }).catch(() => undefined);
    }, 500);
    return () => { live = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, city?.city, position]);

  if (items.length === 0) return null;
  const best = data?.best;
  const closest = city?.stores[0];

  if (!best && closest) {
    return (
      <section className="best-store">
        <p className="eyebrow">Your closest store</p>
        <h3>{closest.name}</h3>
        <p className="best-total">{peso(total)}</p>
        <p className="best-meta">
          {closest.type} · {closest.distance_km.toFixed(1)} km away
          {official > 0 ? ` · official SRPs apply to ${official} ${official === 1 ? "item" : "items"}` : ""}
        </p>
        <RouteMap store={{ store_name: closest.name, latitude: closest.latitude, longitude: closest.longitude }} />
        <p className="hint">The cheapest store will appear here once store prices near you are known.</p>
      </section>
    );
  }
  if (!best) return null;

  return (
    <section className="best-store">
      <p className="eyebrow">Cheapest store for your list</p>
      <h3>{best.store_name}</h3>
      <p className="best-total">{peso(best.total)}</p>
      {data!.saving > 0 && <p className="saving">You save up to {peso(data!.saving)} compared with other stores</p>}
      <p className="best-meta">
        {best.items_found} of {data!.items_total} items at this store
        {best.distance_km !== null && ` · ${best.distance_km.toFixed(1)} km away`}
      </p>
      <RouteMap store={best} />
      <ul className="best-lines">
        {best.lines.map((line) => (
          <li key={line.query}><span>{line.item_name}</span><span>{peso(line.price)}</span><small>verified {timeAgo(line.reported_at)}</small></li>
        ))}
      </ul>
      {data!.stores.length > 1 && (
        <details>
          <summary>Compare {data!.stores.length} stores</summary>
          <ul className="best-lines">
            {data!.stores.map((s) => (
              <li key={`${s.store_name}${s.latitude}`}><span>{s.store_name}</span><span>{peso(s.total)}</span><small>{s.items_found} items{s.distance_km !== null ? ` · ${s.distance_km.toFixed(1)} km` : ""}</small></li>
            ))}
          </ul>
        </details>
      )}
      <p className="hint">Based on recent store prices. They may have changed.</p>
    </section>
  );
}
