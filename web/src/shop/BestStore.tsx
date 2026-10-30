import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, BestStores, postJson, query, Route } from "../api";
import { peso, timeAgo } from "../format";
import { useLocation } from "../location";

const pin = (className: string, label: string) => L.divIcon({
  className: "", iconSize: [34, 42], iconAnchor: [17, 42],
  html: `<span class="pin ${className}"><b>${label}</b></span>`,
});

/** An in-app map from the shopper's real position to the store, with the road route. */
function RouteMap({ store }: { store: { store_name: string; latitude: number; longitude: number } }) {
  const { position } = useLocation();
  const holder = useRef<HTMLDivElement>(null);
  const [route, setRoute] = useState<Route | null>(null);

  useEffect(() => {
    if (!position) return;
    api<Route>(`/location/route${query({ from_lat: position.latitude, from_lon: position.longitude, to_lat: store.latitude, to_lon: store.longitude })}`)
      .then(setRoute).catch(() => setRoute(null));
  }, [position, store.latitude, store.longitude]);

  useEffect(() => {
    if (!holder.current) return;
    const map = L.map(holder.current, { scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "© OpenStreetMap contributors",
    }).addTo(map);
    const target: L.LatLngTuple = [store.latitude, store.longitude];
    L.marker(target, { icon: pin("store", "₱") }).addTo(map).bindTooltip(store.store_name);
    const points: L.LatLngTuple[] = [target];
    if (position) {
      const here: L.LatLngTuple = [position.latitude, position.longitude];
      L.marker(here, { icon: pin("me", "•") }).addTo(map).bindTooltip("You are here");
      points.push(here);
    }
    if (route) {
      const line = L.polyline(route.path as L.LatLngTuple[], { color: "#14532d", weight: 5, opacity: .85, dashArray: route.road ? undefined : "8 8" }).addTo(map);
      map.fitBounds(line.getBounds().pad(0.15));
    } else if (points.length > 1) {
      map.fitBounds(L.latLngBounds(points).pad(0.25));
    } else {
      map.setView(target, 15);
    }
    return () => { map.remove(); };
  }, [store.latitude, store.longitude, store.store_name, position, route]);

  return (
    <>
      <div className="route-map" ref={holder} role="img" aria-label={`Map from your location to ${store.store_name}`} />
      {route && (
        <p className="route-facts">
          <b>{route.distance_km.toFixed(1)} km</b>{route.road ? " by road" : " straight-line"}
          {route.duration_min !== null && <> · about <b>{route.duration_min} min</b> by car</>}
        </p>
      )}
      {!position && <p className="hint">Allow location to see the route from where you are.</p>}
    </>
  );
}

export function BestStore({ items }: { items: string[] }) {
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

  return (
    <section className="best-store">
      <p className="eyebrow">Cheapest store for your list</p>
      {!best ? (
        <p className="best-empty">
          No shopper has reported these prices{city ? ` in ${city.city}` : ""} yet. Share what you see below, and the cheapest store will appear here for everyone.
        </p>
      ) : (
        <>
          <h3>{best.store_name}</h3>
          <p className="best-total">{peso(best.total)}</p>
          <p className="best-meta">
            {best.items_found} of {data!.items_total} items at this store
            {best.distance_km !== null && ` · ${best.distance_km.toFixed(1)} km away`}
          </p>
          <RouteMap store={best} />
          <ul className="best-lines">
            {best.lines.map((line) => (
              <li key={line.query}><span>{line.item_name}</span><span>{peso(line.price)}</span><small>reported {timeAgo(line.reported_at)}</small></li>
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
          <p className="hint">Based on prices other shoppers reported in the last 30 days. Prices may have changed.</p>
        </>
      )}
    </section>
  );
}
