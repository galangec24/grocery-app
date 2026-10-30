import { PointerEvent, useEffect, useRef, useState } from "react";
import { api, PriceRow } from "../api";
import { peso } from "../format";
import { PriceBoard } from "./PriceBoard";

const REPO = "galangec24/grocery-app";
const APK_URL = `https://github.com/${REPO}/releases/latest/download/grocery-price-finder.apk`;
const HERO_ITEMS = ["Premium Rice, Local", "Tilapia", "Saba Philippines Sardines", "Chicken Egg (White, Medium)"];

export function Landing() {
  const [hero, setHero] = useState<PriceRow[]>([]);
  const [apkReady, setApkReady] = useState(false);
  const scene = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<{ results: PriceRow[] }>("/market/prices")
      .then((r) => setHero(HERO_ITEMS.flatMap((name) => r.results.find((row) => row.commodity === name) ?? [])))
      .catch(() => setHero([]));
    fetch(`https://api.github.com/repos/${REPO}/releases/latest`)
      .then((r) => setApkReady(r.ok))
      .catch(() => setApkReady(false));
  }, []);

  function tilt(event: PointerEvent<HTMLDivElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width - 0.5;
    const y = (event.clientY - box.top) / box.height - 0.5;
    scene.current?.style.setProperty("--ry", `${x * 16}deg`);
    scene.current?.style.setProperty("--rx", `${-y * 12}deg`);
  }

  return (
    <div className="site">
      <div className="hero-wrap" onPointerMove={tilt}>
        <header className="site-nav">
          <a className="brand" href="#/"><span className="brand-mark">₱</span> Grocery Price Finder</a>
          <nav>
            <a href="#/shop">Open app</a>
            <a href="#/dashboard">Dashboard</a>
          </nav>
        </header>
        <section className="hero">
          <div>
            <p className="eyebrow">Official Philippine grocery prices</p>
            <h1>Know the fair price before you pay.</h1>
            <p className="lede">
              Check the government's standard prices for everyday groceries, follow daily market prices,
              and total up your whole shopping list.
            </p>
            <div className="actions">
              <button className="btn glow" onClick={() => document.getElementById("prices")?.scrollIntoView({ behavior: "smooth" })}>See today's prices</button>
              <a className="btn ghost" href="#/shop">Build a list</a>
              {apkReady && <a className="btn ghost" href={APK_URL}>Download for Android</a>}
            </div>
          </div>
          <div className="scene" ref={scene} aria-hidden={hero.length === 0}>
            <div className="stack">
              {hero.map((row, index) => (
                <article className="float-card" key={row.id} style={{ "--i": index } as React.CSSProperties}>
                  <span>{row.kind === "srp" ? "DTI standard price" : "DA market price"}</span>
                  <strong>{row.commodity}</strong>
                  <em>{peso(row.price)}<small> / {row.unit}</small></em>
                </article>
              ))}
            </div>
          </div>
        </section>
      </div>

      <main id="prices" className="board-wrap">
        <div className="section-head">
          <h2>Live price board</h2>
          <p className="muted">Standard prices from the DTI and daily market prices from the DA.</p>
        </div>
        <PriceBoard />
      </main>

      <section className="retailers">
        <div>
          <h2>For mall administrators and supermarket supervisors</h2>
          <p>Connect your inventory by API or CSV to show your store's own shelf prices beside the official ones. Each organization can only reach its own data.</p>
        </div>
        <a className="btn primary" href="#/dashboard">Open the dashboard</a>
      </section>

      <footer className="site-footer">
        <p>Data: Department of Trade and Industry, Department of Agriculture. Store locations © OpenStreetMap contributors. Not affiliated with any government agency.</p>
      </footer>
    </div>
  );
}
