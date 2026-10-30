import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { adminSession, api, ApiError, postJson } from "../api";
import { peso, STATUS_META, timeAgo } from "../format";

interface Retailer {
  id: string;
  organization: string;
  integration_type: string;
  sync_interval_minutes: number;
  fresh_minutes: number;
  stale_minutes: number;
  status: string;
  last_successful_sync_at: string | null;
  can_sync: boolean;
  freshness: Record<PriceStatus, number>;
}

interface Overview {
  stores: number;
  products: number;
  listings: number;
  freshness: Record<PriceStatus, number>;
  integrations_total: number;
  integrations_failed: number;
  retailers: Retailer[];
}

interface Job {
  id: string;
  organization: string;
  started_at: string;
  status: string;
  records_processed: number;
  records_updated: number;
  records_rejected: number;
  error_summary: string | null;
  rejections: { row: number; reason: string }[];
}

interface Quality {
  price_discrepancies: { store: string; product: string; package_size: string; price: number; median_price: number }[];
}

interface Report {
  source: string;
  status: string;
  report_date: string | null;
  rows: number;
  error: string | null;
  checked_at: string;
  url: string;
}

interface Audit {
  action: string;
  actor: string | null;
  detail: string | null;
  created_at: string;
}

export type PriceStatus = "fresh" | "aging" | "stale" | "unavailable" | "unknown";

const ORDER: PriceStatus[] = ["fresh", "aging", "stale", "unavailable", "unknown"];

export function Dashboard() {
  const [signedIn, setSignedIn] = useState(!!adminSession.get());
  return (
    <div className="site dash">
      <header className="site-nav">
        <a className="brand" href="#/"><img className="brand-mark" src="./logo.png" alt="" /> Grocery Price Finder</a>
        <nav>
          <a href="#/shop">Open app</a>
          {signedIn && <button className="link" onClick={() => { adminSession.clear(); setSignedIn(false); }}>Sign out</button>}
        </nav>
      </header>
      {signedIn ? <Console onExpired={() => setSignedIn(false)} /> : <Login onDone={() => setSignedIn(true)} />}
    </div>
  );
}

function Login({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      adminSession.set(await postJson("/auth/login", { email, password }));
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <form className="login" onSubmit={submit}>
      <h1>Administrator sign in</h1>
      <p>For mall administrators, supervisors and system administrators.</p>
      <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></label>
      <label>Password<input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="btn primary" type="submit">Sign in</button>
    </form>
  );
}

function Console({ onExpired }: { onExpired: () => void }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [o, j, q, a, r] = await Promise.all([
        api<Overview>("/admin/overview", {}, true),
        api<Job[]>("/admin/sync-jobs?limit=12", {}, true),
        api<Quality>("/admin/data-quality", {}, true),
        api<Audit[]>("/admin/audit-logs", {}, true),
        api<Report[]>("/admin/market-reports", {}, true),
      ]);
      setOverview(o); setJobs(j); setQuality(q); setAudit(a); setReports(r); setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onExpired();
      else setError((e as Error).message);
    }
  }, [onExpired]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 30000);
    return () => clearInterval(timer);
  }, [load]);

  async function run(retailer: Retailer, action: "sync" | "test") {
    setNotice(null);
    try {
      if (action === "test") {
        const result = await postJson<{ ok: boolean; detail: string }>(`/admin/integrations/${retailer.id}/test`, {}, true);
        setNotice(`${retailer.organization}: ${result.detail}`);
      } else {
        const job = await postJson<Job>(`/admin/integrations/${retailer.id}/sync`, {}, true);
        setNotice(`${retailer.organization}: sync ${job.status}${job.error_summary ? ` (${job.error_summary})` : ""}`);
      }
      load();
    } catch (e) {
      setNotice((e as Error).message);
    }
  }

  if (error && !overview) return <p className="error page-error">{error}</p>;
  if (!overview) return <p className="muted page-error">Loading dashboard…</p>;

  const current = overview.freshness.fresh + overview.freshness.aging;
  const share = overview.listings ? Math.round((current / overview.listings) * 100) : 0;

  return (
    <main className="console">
      <div className="console-head">
        <h1>Dashboard</h1>
        <p className="muted">Refreshes every 30 seconds</p>
      </div>
      {notice && <p className="notice" role="status">{notice}</p>}

      {overview.listings > 0 && <section className="tiles">
        <Tile label="Listings tracked" value={overview.listings.toLocaleString()} note={`${overview.products} products, ${overview.stores} branches`} />
        <Tile label="Comparable prices" value={`${share}%`} note="Fresh or aging; the rest are not ranked" />
        <Tile label="Stale prices" value={overview.freshness.stale.toLocaleString()} note="Hidden from default results" />
        <Tile
          label="Integrations failing"
          value={`${overview.integrations_failed} of ${overview.integrations_total}`}
          note={overview.integrations_failed ? "Prices kept; shown as stale when too old" : "All connections healthy"}
          alert={overview.integrations_failed > 0}
        />
      </section>}

      <section className="card">
        <h2>Official price collection</h2>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Source</th><th>Report date</th><th className="num">Rows</th><th>Result</th><th>Checked</th><th>Note</th></tr></thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.url}>
                  <td><a href={r.url} target="_blank" rel="noreferrer">{r.source === "dti_srp" ? "DTI SRP" : "DA Daily Price Index"}</a></td>
                  <td>{r.report_date ?? "–"}</td>
                  <td className="num">{r.rows}</td>
                  <td><Health status={r.status === "ok" ? "succeeded" : r.status} /></td>
                  <td>{timeAgo(r.checked_at)}</td>
                  <td className="muted">{r.error}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {overview.retailers.length === 0 && (
        <section className="card">
          <h2>Retailers</h2>
          <p className="muted">No retailers have connected yet. Their shelf prices, integrations and sync history will appear here.</p>
        </section>
      )}

      {overview.retailers.length > 0 && <section className="card">
        <h2>Price freshness by retailer</h2>
        <FreshnessChart retailers={overview.retailers} />
      </section>}

      <section className="card">
        <h2>Integrations</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Retailer</th><th>Method</th><th>Health</th><th>Last success</th><th>Fresh within</th><th>Stale after</th><th /></tr>
            </thead>
            <tbody>
              {overview.retailers.map((r) => (
                <tr key={r.id}>
                  <td>{r.organization}</td>
                  <td>{r.integration_type.toUpperCase()}</td>
                  <td><Health status={r.status} /></td>
                  <td>{timeAgo(r.last_successful_sync_at)}</td>
                  <td className="num">{r.fresh_minutes} min</td>
                  <td className="num">{r.stale_minutes} min</td>
                  <td className="row-actions">
                    {r.can_sync && <>
                      <button className="mini" onClick={() => run(r, "test")}>Test</button>
                      <button className="mini" onClick={() => run(r, "sync")}>Sync now</button>
                    </>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="two-col">
        <CsvImport retailers={overview.retailers} onDone={load} />
        <section className="card">
          <h2>Possible price errors</h2>
          {quality?.price_discrepancies.length ? (
            <ul className="plain">
              {quality.price_discrepancies.slice(0, 6).map((d) => (
                <li key={d.store + d.product + d.package_size}>
                  <b>{d.product} {d.package_size}</b> at {d.store}: {peso(d.price)} vs typical {peso(d.median_price)}
                </li>
              ))}
            </ul>
          ) : <p className="muted">No listings are more than 25% away from the typical price.</p>}
        </section>
      </div>

      <section className="card">
        <h2>Recent sync jobs</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>When</th><th>Retailer</th><th>Result</th><th className="num">Processed</th><th className="num">Updated</th><th className="num">Rejected</th><th>Note</th></tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>{timeAgo(job.started_at)}</td>
                  <td>{job.organization}</td>
                  <td><Health status={job.status} /></td>
                  <td className="num">{job.records_processed}</td>
                  <td className="num">{job.records_updated}</td>
                  <td className="num">{job.records_rejected}</td>
                  <td className="muted">{job.error_summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2>Audit log</h2>
        {audit.length ? (
          <ul className="plain">
            {audit.slice(0, 8).map((a, i) => (
              <li key={i}><b>{a.action}</b> by {a.actor ?? "system"}, {timeAgo(a.created_at)}{a.detail ? ` (${a.detail})` : ""}</li>
            ))}
          </ul>
        ) : <p className="muted">No administrative actions recorded yet.</p>}
      </section>
    </main>
  );
}

function Tile({ label, value, note, alert }: { label: string; value: string; note: string; alert?: boolean }) {
  return (
    <div className={`tile${alert ? " alert" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function Health({ status }: { status: string }) {
  const good = status === "active" || status === "succeeded";
  const bad = status === "failed";
  return (
    <span className={`health ${good ? "good" : bad ? "bad" : ""}`}>
      {good ? "●" : bad ? "▲" : "○"} {status[0].toUpperCase() + status.slice(1)}
    </span>
  );
}

function FreshnessChart({ retailers }: { retailers: Retailer[] }) {
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const shown = ORDER.filter((s) => retailers.some((r) => r.freshness[s] > 0));

  return (
    <div className="chart" ref={root}>
      <ul className="legend">
        {shown.map((s) => (
          <li key={s}><i className={`swatch st-${s}`} />{STATUS_META[s].icon} {STATUS_META[s].label}</li>
        ))}
      </ul>
      {retailers.map((r) => {
        const total = ORDER.reduce((sum, s) => sum + r.freshness[s], 0);
        return (
          <div className="bar-row" key={r.id}>
            <span className="bar-name">{r.organization}</span>
            <div className="bar" role="img" aria-label={`${r.organization}: ${ORDER.filter((s) => r.freshness[s]).map((s) => `${r.freshness[s]} ${s}`).join(", ")}`}>
              {ORDER.filter((s) => r.freshness[s] > 0).map((s) => (
                <span
                  key={s}
                  className={`seg st-${s}`}
                  style={{ flexGrow: r.freshness[s] }}
                  onMouseMove={(e) => {
                    const box = root.current!.getBoundingClientRect();
                    setTip({
                      x: e.clientX - box.left,
                      y: e.clientY - box.top,
                      text: `${r.organization}: ${r.freshness[s]} ${STATUS_META[s].label.toLowerCase()} (${Math.round((r.freshness[s] / total) * 100)}%)`,
                    });
                  }}
                  onMouseLeave={() => setTip(null)}
                />
              ))}
            </div>
            <span className="bar-total">{total}</span>
          </div>
        );
      })}
      {tip && <div className="tooltip" style={{ left: tip.x, top: tip.y }}>{tip.text}</div>}
    </div>
  );
}

function CsvImport({ retailers, onDone }: { retailers: Retailer[]; onDone: () => void }) {
  const [integration, setIntegration] = useState(retailers[0]?.id ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true); setError(null); setResult(null);
    const form = new FormData();
    form.set("integration_id", integration);
    form.set("file", file);
    try {
      setResult(await api<Job>("/admin/imports/csv", { method: "POST", body: form }, true));
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Import prices from CSV</h2>
      <form className="csv" onSubmit={submit}>
        <label>Retailer
          <select value={integration} onChange={(e) => setIntegration(e.target.value)}>
            {retailers.map((r) => <option key={r.id} value={r.id}>{r.organization}</option>)}
          </select>
        </label>
        <label>CSV file<input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
        <p className="hint">Required columns: <code>store_id, retailer_product_id, price, currency</code>. Optional: <code>availability, barcode, price_effective_at</code>.</p>
        <button className="btn primary" disabled={!file || busy}>{busy ? "Importing…" : "Import"}</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {result && (
        <div className="import-result">
          <p><Health status={result.status} /> {result.records_processed} rows, {result.records_updated} updated, {result.records_rejected} rejected</p>
          {result.status === "failed" && <p className="error">{result.error_summary}</p>}
          {result.rejections.slice(0, 5).map((r) => <p className="muted" key={r.row}>Row {r.row}: {r.reason}</p>)}
        </div>
      )}
    </section>
  );
}
