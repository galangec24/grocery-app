import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, postJson } from "../api";

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
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", role: "supervisor", organization_id: "" });
  const [retailer, setRetailer] = useState("");
  const [item, setItem] = useState({ name: "", brand: "", category: "", size: "" });

  const load = useCallback(async () => {
    const [u, r, c, s] = await Promise.all([
      api<Account[]>("/admin/users", {}, true),
      api<Retailer[]>("/admin/organizations", {}, true),
      api<CatalogEntry[]>("/admin/catalog", {}, true),
      api<ShelfReport[]>("/admin/shelf-prices", {}, true),
    ]);
    setUsers(u); setRetailers(r); setCatalog(c); setReports(s);
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
          <h2>Official price collection</h2>
          <button className="mini" onClick={() => act(() => postJson("/admin/market/refresh", {}, true), "Checking the DTI and DA for new reports. Results appear below in a minute or two.")}>Check for new prices now</button>
        </div>
        <p className="muted">Prices are checked automatically through the day. Use this after an agency publishes a new report.</p>
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
