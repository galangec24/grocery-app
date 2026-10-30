import { useEffect, useState } from "react";
import { api, Stats } from "../api";
import { peso } from "../format";

const APK_PATH = "downloads/grocery-price-finder.apk";

const STEPS = [
  ["Search", "Look up one product, or paste your whole grocery list at once."],
  ["Compare", "See every participating branch ranked by price, distance and how recent the price is."],
  ["Decide", "Pick the lowest price, the nearest store, or the best price close to you."],
];

const FEATURES = [
  ["Search many items at once", "Paste a list and get a basket total for each store, plus what you'd pay by splitting the trip."],
  ["Save your list as a draft", "Build a list over the week and come back to it. Drafts stay on your device, with no account needed."],
  ["Honest price freshness", "Every price shows when it was last updated. Out-of-date prices are never ranked with current ones."],
  ["Like-for-like comparison", "A 1 kg bag never competes with a 5 kg bag. Only the same product and size are compared."],
  ["Location when you want it", "Use your location once, or just choose your area. The app never tracks you in the background."],
  ["One place for every retailer", "Supermarkets keep their own systems. The platform brings authorized prices together."],
];

const SAMPLE = [
  { store: "Supermarket A", price: 85, away: "4.2 km", updated: "2 min ago", label: "Lowest Price" },
  { store: "Supermarket B", price: 89, away: "1.1 km", updated: "1 min ago", label: "Best Nearby Price" },
  { store: "Supermarket C", price: 92, away: "0.6 km", updated: "just now", label: "Nearest Store" },
];

export function Landing() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [apkReady, setApkReady] = useState(false);

  useEffect(() => {
    api<Stats>("/stats").then(setStats).catch(() => setStats(null));
    fetch(APK_PATH, { method: "HEAD" })
      .then((r) => setApkReady(r.ok && !(r.headers.get("content-type") ?? "").includes("html")))
      .catch(() => setApkReady(false));
  }, []);

  return (
    <div className="site">
      <header className="site-nav">
        <a className="brand" href="#/"><span className="brand-mark">₱</span> Grocery Price Finder</a>
        <nav>
          <a href="#/shop">Open app</a>
          <a href="#/dashboard">Dashboard</a>
        </nav>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">One search. Every participating supermarket.</p>
          <h1>Know where your groceries cost less before you leave home.</h1>
          <p className="lede">
            Compare prices across supermarkets near you, see how recent each price is, and turn your
            whole shopping list into a basket total for every store.
          </p>
          <div className="actions">
            <a className="btn primary" href="#/shop">Try the web app</a>
            {apkReady
              ? <a className="btn" href={APK_PATH} download>Download Android APK</a>
              : <span className="btn disabled" title="The APK has not been built yet">Android APK coming soon</span>}
          </div>
          {stats && (
            <p className="hero-stats">
              <b>{stats.retailers}</b> retailers · <b>{stats.stores}</b> branches · <b>{stats.products}</b> products
              {stats.sample_data && <span className="tag">Sample data</span>}
            </p>
          )}
        </div>
        <figure className="phone" aria-label="Example comparison using illustrative prices">
          <p className="phone-title">Cooking Oil · 1 L</p>
          {SAMPLE.map((row) => (
            <div className="phone-row" key={row.store}>
              <div>
                <strong>{row.store}</strong>
                <small>{row.away} · updated {row.updated}</small>
                <span className="label">{row.label}</span>
              </div>
              <span className="price">{peso(row.price)}</span>
            </div>
          ))}
          <figcaption>Illustrative prices</figcaption>
        </figure>
      </section>

      <section className="steps">
        {STEPS.map(([title, text], index) => (
          <div key={title}>
            <span className="step-number">{index + 1}</span>
            <h3>{title}</h3>
            <p>{text}</p>
          </div>
        ))}
      </section>

      <section className="features">
        <h2>Built for how people actually shop</h2>
        <div className="feature-grid">
          {FEATURES.map(([title, text]) => (
            <article key={title}>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="retailers">
        <div>
          <h2>For mall administrators and supermarket supervisors</h2>
          <p>
            Connect your existing inventory through an approved API or a CSV upload, then monitor
            synchronization, rejected records and price freshness from the dashboard. Each
            organization can only reach its own data.
          </p>
        </div>
        <a className="btn primary" href="#/dashboard">Open the dashboard</a>
      </section>

      <footer className="site-footer">
        <p>Prices shown are the listed retail price last received from each retailer and may differ at checkout.</p>
      </footer>
    </div>
  );
}
