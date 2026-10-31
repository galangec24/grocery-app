import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { useEffect, useRef, useState } from "react";
import { api, query, Route } from "./api";
import { Icon } from "./icons";
import { useLocation } from "./location";

const STYLE = "https://tiles.openfreemap.org/styles/liberty"; // Free, with 3D buildings.

interface Place {
  store_name: string;
  latitude: number;
  longitude: number;
}

function pin(kind: string, label: string) {
  const element = document.createElement("span"); // The map positions this, so the rotated pin sits inside.
  element.innerHTML = `<span class="pin ${kind}"><b>${label}</b></span>`;
  return element;
}

/** A tilted 3D map inside the app, from the shopper's real position to the store. */
export function RouteMap({ store }: { store: Place }) {
  const { position } = useLocation();
  const holder = useRef<HTMLDivElement>(null);
  const [route, setRoute] = useState<Route | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!position) return;
    api<Route>(`/location/route${query({ from_lat: position.latitude, from_lon: position.longitude, to_lat: store.latitude, to_lon: store.longitude })}`)
      .then(setRoute).catch(() => setRoute(null));
  }, [position, store.latitude, store.longitude]);

  useEffect(() => {
    let cleanup = () => {};
    let live = true;
    let glide: ReturnType<typeof setTimeout>;
    (async () => {
      const library = await import("maplibre-gl");
      await import("maplibre-gl/dist/maplibre-gl.css");
      const gl = ((library as unknown as { default?: typeof library }).default ?? library);
      gl.setWorkerUrl(workerUrl);
      if (!live || !holder.current) return;
      const target: [number, number] = [store.longitude, store.latitude];
      const map = new gl.Map({ container: holder.current, style: STYLE, center: target, zoom: 16, pitch: 60, bearing: -20, scrollZoom: false });
      cleanup = () => { clearTimeout(glide); map.remove(); };
      map.addControl(new gl.NavigationControl({ visualizePitch: true }));
      new gl.Marker({ element: pin("store", "₱"), anchor: "bottom" }).setLngLat(target).addTo(map);
      const here: [number, number] | null = position ? [position.longitude, position.latitude] : null;
      if (here) new gl.Marker({ element: pin("me", "•"), anchor: "bottom" }).setLngLat(here).addTo(map);
      map.on("load", () => {
        const path = route ? route.path.map(([lat, lon]) => [lon, lat] as [number, number]) : [];
        if (path.length > 1) {
          map.addSource("route", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: path } } });
          map.addLayer({
            id: "route", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" },
            paint: { "line-color": "#14532d", "line-width": 6, "line-opacity": .85, ...(route?.road ? {} : { "line-dasharray": [2, 2] }) },
          });
        }
        const points = [target, ...(here ? [here] : []), ...path];
        if (points.length > 1) {
          const bounds = new gl.LngLatBounds(points[0], points[0]);
          points.forEach((point) => bounds.extend(point));
          map.fitBounds(bounds, { padding: 60, pitch: 60, bearing: -20, duration: 0, maxZoom: 16.5 });
          // Show the whole trip, then glide in, because buildings only rise when close.
          glide = setTimeout(() => map.flyTo({ center: target, zoom: 16.4, pitch: 62, bearing: -20, duration: 2500 }), 1800);
        }
      });
    })().catch(() => { if (live) setFailed(true); });
    return () => { live = false; cleanup(); };
  }, [store.latitude, store.longitude, position, route]);

  if (failed) return <p className="note">The 3D map needs WebGL, which this browser has switched off.</p>;
  return (
    <>
      <div className="route-map" ref={holder} role="img" aria-label={`3D map from your location to ${store.store_name}`} />
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

export function StoreMapDialog({ store, detail, onClose, onBrowse }: {
  store: Place; detail: string; onClose: () => void; onBrowse?: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return (
    <dialog ref={dialog} className="modal map-dialog" onClose={onClose}
      onClick={(e) => { if (e.target === dialog.current) dialog.current?.close(); }}>
      <div className="modal-card">
        <button className="modal-close" aria-label="Close" onClick={() => dialog.current?.close()}><Icon name="close" size={18} /></button>
        <h2>{store.store_name}</h2>
        <p className="muted">{detail}</p>
        <RouteMap store={store} />
        {onBrowse && <button className="btn primary block" onClick={() => { onBrowse(); dialog.current?.close(); }}>See prices at this mall</button>}
      </div>
    </dialog>
  );
}
