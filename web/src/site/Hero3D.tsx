import { PointerEvent, RefObject, useEffect, useRef, useState } from "react";
import { api, PriceRow } from "../api";
import { peso } from "../format";

const ITEMS = ["Premium Rice, Local", "Tilapia", "Saba Philippines Sardines", "Chicken Egg (White, Medium)"];

export function useTilt() {
  const scene = useRef<HTMLDivElement>(null);
  function tilt(event: PointerEvent<HTMLElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width - 0.5;
    const y = (event.clientY - box.top) / box.height - 0.5;
    scene.current?.style.setProperty("--ry", `${x * 16}deg`);
    scene.current?.style.setProperty("--rx", `${-y * 12}deg`);
  }
  return { scene, tilt };
}

/** Real current prices floating on cards in perspective. */
export function Hero3D({ scene, count = 4 }: { scene: RefObject<HTMLDivElement | null>; count?: number }) {
  const [rows, setRows] = useState<PriceRow[]>([]);

  useEffect(() => {
    api<{ results: PriceRow[] }>("/market/prices")
      .then((r) => setRows(ITEMS.slice(0, count).flatMap((name) => r.results.find((row) => row.commodity === name) ?? [])))
      .catch(() => setRows([]));
  }, [count]);

  return (
    <div className="scene" ref={scene} aria-hidden={rows.length === 0}>
      <div className="stack">
        {rows.map((row, index) => (
          <article className="float-card" key={row.id} style={{ "--i": index } as React.CSSProperties}>
            <span>{row.kind === "srp" ? "DTI standard price" : "DA market price"}</span>
            <strong>{row.commodity}</strong>
            <em>{peso(row.price)}<small> / {row.unit}</small></em>
          </article>
        ))}
      </div>
    </div>
  );
}
