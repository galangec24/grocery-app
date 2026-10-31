import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, postJson } from "../api";
import { Icon, IconButton } from "../icons";

interface Account {
  id: string;
  email: string;
  full_name: string;
  status: string;
  roles: { role: string; organization: string | null }[];
}

interface Retailer {
  id: string;
  name: string;
  stores: number;
}

interface PriceSource {
  id: string;
  name: string;
  kind: string;
  permission: string;
  enabled: boolean;
  can_run: boolean;
  terms_url: string;
  notes: string;
  prices: number;
  last_import_at: string | null;
  connector_url: string | null;
}

const PERMISSION: Record<string, string> = {
  open_license: "Open license", granted: "Permission granted", pending: "Waiting for permission", refused: "Refused",
};

interface AgentStatus {
  live: { checked_at: string | null; updated_at: string | null };
  coverage: { products: number; priced: number; blank: number; updated: number } | null;
  runs: { started_at: string; status: string; data_changed: boolean; steps: { source: string; status: string; error?: string }[] }[];
}

interface ShelfReport {
  id: string;
  status: string;
  item_name: string;
  store_name: string;
  city: string;
  price: number;
}

interface CatalogEntry {
  id: string;
  name: string;
  category: string;
  size: string;
}

const ROLES = [
  ["system_admin", "System administrator"],
  ["mall_admin", "Mall administrator"],
  ["supervisor", "Supermarket supervisor"],
  ["integration_admin", "Integration administrator"],
];

const send = (path: string, method: string, body?: unknown) =>
  api(path, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined }, true);

/** System administrator tools. The server enforces the same rule for every action. */
export function AdminTools({ onChanged }: { onChanged: () => void }) {
  const [users, setUsers] = useState<Account[]>([]);
  const [retailers, setRetailers] = useState<Retailer[]>([]);
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [reports, setReports] = useState<ShelfReport[]>([]);
  const [sources, setSources] = useState<PriceSource[]>([]);
  const [agent, setAgent] = useState<AgentStatus | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [connector, setConnector] = useState("");
  const [mall, setMall] = useState({ name: "", kind: "retailer_api", terms_url: "" });
  const [manual, setManual] = useState({ retailer: "", branch: "", product: "", size: "", price: "" });
  const [feedResult, setFeedResult] = useState<string | null>(null);
  const [granting, setGranting] = useState<string | null>(null);
  const [proof, setProof] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", role: "supervisor", organization_id: "" });
  const [retailer, setRetailer] = useState("");
  const [item, setItem] = useState({ name: "", brand: "", category: "", size: "" });

  const load = useCallback(async () => {
    const [u, r, c, s, p, a] = await Promise.all([
      api<Account[]>("/admin/users", {}, true),
      api<Retailer[]>("/admin/organizations", {}, true),
      api<CatalogEntry[]>("/admin/catalog", {}, true),
      api<ShelfReport[]>("/admin/shelf-prices", {}, true),
      api<PriceSource[]>("/admin/sources", {}, true),
      api<AgentStatus>("/admin/agent", {}, true),
    ]);
    setUsers(u); setRetailers(r); setCatalog(c); setReports(s); setSources(p); setAgent(a);
  }, []);

  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);

  async function act(action: () => Promise<unknown>, message: string) {
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(message);
      await load();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function importFeed(source: PriceSource, file: File | undefined) {
    if (!file) return;
    const form = new FormData();
    form.set("file", file);
    act(async () => {
      const result = await api<{ imported: number; rejected: number; rejections: { row: number; reason: string }[] }>(
        `/admin/sources/${source.id}/import`, { method: "POST", body: form }, true,
      );
      setFeedResult(`${source.name}: ${result.imported} imported, ${result.rejected} rejected.${result.rejections[0] ? ` Row ${result.rejections[0].row}: ${result.rejections[0].reason}.` : ""}`);
    }, "Import finished.");
  }

  function addMall(event: FormEvent) {
    event.preventDefault();
    act(async () => {
      await postJson("/admin/sources", { ...mall, notes: "" }, true);
      setMall({ name: "", kind: "retailer_api", terms_url: "" });
    }, "Mall added. Record permission to switch it on.");
  }

  function updatePrice(event: FormEvent) {
    event.preventDefault();
    act(async () => {
      await postJson("/admin/prices", { ...manual, price: Number(manual.price) }, true);
      setManual({ retailer: "", branch: "", product: "", size: "", price: "" });
    }, "Price updated. Open apps will show it within 30 seconds.");
  }

  function addUser(event: FormEvent) {
    event.preventDefault();
    act(async () => {
      await postJson("/admin/users", { ...form, organization_id: form.organization_id || null }, true);
      setForm({ email: "", full_name: "", password: "", role: "supervisor", organization_id: "" });
    }, "Account created.");
  }

  function addRetailer(event: FormEvent) {
    event.preventDefault();
    act(async () => { await postJson("/admin/organizations", { name: retailer }, true); setRetailer(""); }, "Retailer added.");
  }

  function addItem(event: FormEvent) {
    event.preventDefault();
    act(async () => {
      await postJson("/admin/catalog", item, true);
      setItem({ name: "", brand: "", category: "", size: "" });
    }, "Product added to the catalog.");
  }

  return (
    <>
      {notice && <p className="notice" role="status">{notice}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      <section className="card">
        <div className="card-head">
          <h2>Price Agent</h2>
          <IconButton icon="refresh" label="Run the agent now" className="primary" onClick={() => act(() => postJson("/admin/agent/run", {}, true), "Agent started. Results appear below in a minute or two.")} />
        </div>
        <p className="muted">Checks every permitted source every 15 minutes while the server is awake, then saves the best supported price on each product.</p>
        {agent?.coverage && (
          <div className="agent-stats">
            <div><strong>{agent.coverage.products.toLocaleString()}</strong><small>Products</small></div>
            <div><strong>{agent.coverage.priced.toLocaleString()}</strong><small>With a price</small></div>
            <div><strong>{agent.coverage.blank.toLocaleString()}</strong><small>No evidence yet</small></div>
            <div><strong>{agent.coverage.products ? Math.round((agent.coverage.priced / agent.coverage.products) * 100) : 0}%</strong><small>Coverage</small></div>
          </div>
        )}
        {agent && agent.runs.length === 0 && <p className="muted">The agent hasn't finished a run yet.</p>}
        {agent && agent.runs.length > 0 && (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Started</th><th>Result</th><th>Prices changed</th><th>Sources</th></tr></thead>
              <tbody>
                {agent.runs.slice(0, 5).map((run) => (
                  <tr key={run.started_at}>
                    <td>{new Date(run.started_at).toLocaleString("en-PH", { dateStyle: "medium", timeStyle: "short" })}</td>
                    <td><span className={`health ${run.status === "ok" ? "good" : "bad"}`}>{run.status === "ok" ? "● Complete" : "▲ Partial"}</span></td>
                    <td>{run.data_changed ? "Yes" : "No"}</td>
                    <td className="wrap">{run.steps.map((step) => `${step.source}: ${step.status}`).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>Malls and price sources</h2>
        <p className="muted">Connect every mall here. Nothing is imported until permission is on record.</p>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Source</th><th>Permission</th><th className="num">Feed prices</th><th>Last import</th><th /></tr></thead>
            <tbody>
              {sources.map((source) => (
                <tr key={source.id}>
                  <td className="wrap"><b>{source.name}</b><small className="block">{source.notes}</small></td>
                  <td><span className={`health ${source.can_run ? "good" : "bad"}`}>{source.can_run ? "● " : "▲ "}{PERMISSION[source.permission]}</span></td>
                  <td className="num">{source.prices}</td>
                  <td>{source.last_import_at ? source.last_import_at.slice(0, 10) : "Never"}</td>
                  <td className="row-actions">
                    {source.can_run && source.kind !== "government" && source.kind !== "open_data" && source.kind !== "community" && (
                      <label className="mini">Import CSV<input type="file" accept=".csv,text/csv" hidden onChange={(e) => importFeed(source, e.target.files?.[0])} /></label>
                    )}
                    {source.can_run && source.connector_url && <IconButton icon="refresh" label="Activate the agent for this mall" onClick={() => act(() => postJson(`/admin/sources/${source.id}/run`, {}, true), `Agent started for ${source.name}.`)} />}
                    {source.can_run && source.kind.startsWith("retailer") && <IconButton icon="plusCircle" label={source.connector_url ? "Change API connector" : "Connect an API"} onClick={() => { setConnecting(source.id); setConnector(source.connector_url ?? ""); }} />}
                    {source.permission === "pending" && <button className="mini" onClick={() => { setGranting(source.id); setProof(""); }}>Record permission</button>}
                    {source.permission === "granted" && source.kind !== "community" && <button className="mini" onClick={() => act(() => send(`/admin/sources/${source.id}`, "PATCH", { permission: "pending" }), `${source.name} paused.`)}>Pause</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {granting && (
          <form className="admin-form" onSubmit={(e) => {
            e.preventDefault();
            act(() => send(`/admin/sources/${granting}`, "PATCH", { permission: "granted", enabled: true, notes: proof }), "Permission recorded.");
            setGranting(null);
          }}>
            <input required minLength={8} placeholder="Who granted permission, and when" aria-label="Permission record" value={proof} onChange={(e) => setProof(e.target.value)} />
            <button className="btn primary">Save permission</button>
          </form>
        )}
        {connecting && (
          <form className="admin-form" onSubmit={(e) => {
            e.preventDefault();
            act(() => send(`/admin/sources/${connecting}/connector`, "PUT", { url: connector }), "Connector saved. The agent will use it on its next run.");
            setConnecting(null);
          }}>
            <input required type="url" pattern="https://.*" placeholder="https://retailer.example/prices" aria-label="Connector address" value={connector} onChange={(e) => setConnector(e.target.value)} />
            <button className="btn primary">Save connector</button>
          </form>
        )}
        {feedResult && <p className="notice">{feedResult}</p>}
        <form className="admin-form" onSubmit={addMall}>
          <input required minLength={2} placeholder="Mall or retailer name" aria-label="Mall name" value={mall.name} onChange={(e) => setMall({ ...mall, name: e.target.value })} />
          <select aria-label="How it connects" value={mall.kind} onChange={(e) => setMall({ ...mall, kind: e.target.value })}>
            <option value="retailer_api">Retailer API</option>
            <option value="retailer_feed">CSV or Excel feed</option>
            <option value="retailer_website">Retailer website</option>
            <option value="comparison_site">Comparison site</option>
          </select>
          <input type="url" placeholder="Terms or agreement link (optional)" aria-label="Terms link" value={mall.terms_url} onChange={(e) => setMall({ ...mall, terms_url: e.target.value })} />
          <button className="btn primary with-icon"><Icon name="plus" />Add mall</button>
        </form>
        <p className="hint">CSV columns: <code>retailer, product, size, price, verified_at</code>. Add <code>branch</code>, <code>city</code>, <code>latitude</code> and <code>longitude</code> for a branch price. Without a branch, it counts as a chain price.</p>
      </section>

      <section className="card">
        <h2>Administrators and supervisors</h2>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th /></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.full_name}</td>
                  <td>{u.email}</td>
                  <td>{u.roles.map((r) => `${ROLES.find(([v]) => v === r.role)?.[1] ?? r.role}${r.organization ? `, ${r.organization}` : ""}`).join("; ")}</td>
                  <td><span className={`health ${u.status === "active" ? "good" : "bad"}`}>{u.status === "active" ? "● Active" : "▲ Suspended"}</span></td>
                  <td className="row-actions">
                    <button className="mini" onClick={() => act(
                      () => send(`/admin/users/${u.id}`, "PATCH", { status: u.status === "active" ? "suspended" : "active" }),
                      u.status === "active" ? `${u.full_name} suspended.` : `${u.full_name} restored.`,
                    )}>{u.status === "active" ? "Suspend" : "Restore"}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <form className="admin-form" onSubmit={addUser}>
          <input required placeholder="Full name" aria-label="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          <input required type="email" placeholder="Email" aria-label="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input required type="password" minLength={12} autoComplete="new-password" placeholder="Password, 12+ characters" aria-label="Password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <select aria-label="Role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {ROLES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          {form.role !== "system_admin" && (
            <select required aria-label="Retailer" value={form.organization_id} onChange={(e) => setForm({ ...form, organization_id: e.target.value })}>
              <option value="">Choose retailer</option>
              {retailers.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          )}
          <button className="btn primary">Add account</button>
        </form>
      </section>

      <section className="card">
        <h2>Update a price by hand</h2>
        <p className="muted">Without a branch, this counts as a chain price, shown as "branches may differ".</p>
        <form className="admin-form" onSubmit={updatePrice}>
          <input required minLength={2} placeholder="Mall or retailer" aria-label="Retailer" value={manual.retailer} onChange={(e) => setManual({ ...manual, retailer: e.target.value })} />
          <input placeholder="Branch (optional)" aria-label="Branch" value={manual.branch} onChange={(e) => setManual({ ...manual, branch: e.target.value })} />
          <input required minLength={2} placeholder="Product" aria-label="Product" value={manual.product} onChange={(e) => setManual({ ...manual, product: e.target.value })} />
          <input required placeholder="Size, like 85g" aria-label="Size" value={manual.size} onChange={(e) => setManual({ ...manual, size: e.target.value })} />
          <input required type="number" min="0.01" step="0.01" placeholder="Price" aria-label="Price" value={manual.price} onChange={(e) => setManual({ ...manual, price: e.target.value })} />
          <button className="btn primary with-icon"><Icon name="save" />Save price</button>
        </form>
      </section>

      <section className="card">
        <h2>Shopper-reported prices</h2>
        {reports.length === 0 && <p className="muted">No shopper has reported a price yet.</p>}
        {reports.length > 0 && (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Item</th><th>Store</th><th>City</th><th className="num">Price</th><th>Status</th><th /></tr></thead>
              <tbody>
                {reports.map((r) => (
                  <tr key={r.id}>
                    <td>{r.item_name}</td><td>{r.store_name}</td><td>{r.city}</td>
                    <td className="num">₱{r.price.toFixed(2)}</td>
                    <td><span className={`health ${r.status === "visible" ? "good" : "bad"}`}>{r.status === "visible" ? "● Visible" : "▲ Held for review"}</span></td>
                    <td className="row-actions">
                      {r.status !== "visible" && <button className="mini" onClick={() => act(() => postJson(`/admin/shelf-prices/${r.id}/approve`, {}, true), "Price approved.")}>Approve</button>}
                      <button className="mini" onClick={() => act(() => send(`/admin/shelf-prices/${r.id}`, "DELETE"), "Price removed.")}>Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="two-col">
        <section className="card">
          <h2>Retailers</h2>
          {retailers.length === 0 && <p className="muted">No retailers yet. Add one before creating its supervisors.</p>}
          <ul className="plain">
            {retailers.map((r) => <li key={r.id}><b>{r.name}</b> · {r.stores} {r.stores === 1 ? "branch" : "branches"}</li>)}
          </ul>
          <form className="admin-form" onSubmit={addRetailer}>
            <input required minLength={2} placeholder="Retailer name" aria-label="Retailer name" value={retailer} onChange={(e) => setRetailer(e.target.value)} />
            <button className="btn primary">Add retailer</button>
          </form>
        </section>

        <section className="card">
          <h2>Product catalog</h2>
          <p className="muted">Add a product so shoppers can find it. Catalog items hold no prices.</p>
          <ul className="plain">
            {catalog.map((c) => (
              <li className="purchase-row" key={c.id}>
                <span><b>{c.name}</b><small>{c.size} · {c.category}</small></span>
                <button className="mini" onClick={() => act(() => send(`/admin/catalog/${c.id}`, "DELETE"), `${c.name} removed.`)}>Remove</button>
              </li>
            ))}
          </ul>
          <form className="admin-form" onSubmit={addItem}>
            <input required placeholder="Product name" aria-label="Product name" value={item.name} onChange={(e) => setItem({ ...item, name: e.target.value })} />
            <input required placeholder="Brand" aria-label="Brand" value={item.brand} onChange={(e) => setItem({ ...item, brand: e.target.value })} />
            <input required placeholder="Category" aria-label="Category" value={item.category} onChange={(e) => setItem({ ...item, category: e.target.value })} />
            <input required placeholder="Size, like 100g" aria-label="Size" value={item.size} onChange={(e) => setItem({ ...item, size: e.target.value })} />
            <button className="btn primary">Add product</button>
          </form>
        </section>
      </div>
    </>
  );
}
