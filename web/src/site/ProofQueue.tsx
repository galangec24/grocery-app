import { useEffect, useState } from "react";
import { adminSession, api, postJson } from "../api";
import { peso, timeAgo } from "../format";
import { Icon, IconButton } from "../icons";

interface Proof {
  id: string;
  item_name: string;
  store_name: string;
  city: string;
  price: number;
  created_at: string;
  has_photo: boolean;
  submitter: { approved: number; rejected: number };
  comparison: {
    verdict: "consistent" | "needs_checking" | "no_reference";
    checks: { label: string; price: number; difference_pct: number; ok: boolean }[];
  };
}

const VERDICT = {
  consistent: ["good", "● Matches our references"],
  needs_checking: ["bad", "▲ Needs checking"],
  no_reference: ["", "○ Nothing to compare yet"],
} as const;

function ProofPhoto({ id }: { id: string }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let made: string | null = null;
    const base = import.meta.env.VITE_API_URL || "";
    fetch(`${base}/api/v1/admin/proofs/${id}/photo`, { headers: { Authorization: `Bearer ${adminSession.get()?.access_token}` } })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => { if (blob) { made = URL.createObjectURL(blob); setUrl(made); } })
      .catch(() => undefined);
    return () => { if (made) URL.revokeObjectURL(made); };
  }, [id]);

  return url
    ? <a href={url} target="_blank" rel="noreferrer"><img className="proof-photo" src={url} alt="Proof submitted by a shopper" /></a>
    : <span className="proof-photo empty" />;
}

function ProofCard({ proof, onDecided }: { proof: Proof; onDecided: (message: string) => void }) {
  const [price, setPrice] = useState(String(proof.price));
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tone, label] = VERDICT[proof.comparison.verdict];

  async function decide(action: "approve" | "reject") {
    setError(null);
    try {
      await postJson(`/admin/proofs/${proof.id}/${action}`, action === "approve" ? { price: Number(price) } : { reason }, true);
      onDecided(action === "approve" ? "Price published." : "Proof rejected and its photo deleted.");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <article className="proof-card">
      {proof.has_photo ? <ProofPhoto id={proof.id} /> : <span className="proof-photo empty" />}
      <div className="proof-body">
        <strong>{proof.item_name}</strong>
        <small>{proof.store_name}, {proof.city} · {timeAgo(proof.created_at)} · shopper history: {proof.submitter.approved} approved, {proof.submitter.rejected} rejected</small>
        <span className={`health ${tone}`}>{label}</span>
        {proof.comparison.checks.length > 0 && (
          <ul className="plain proof-checks">
            {proof.comparison.checks.map((check) => (
              <li key={check.label}>
                <span>{check.label}</span>
                <span>{peso(check.price)} <b className={check.ok ? "down" : "up"}>{check.difference_pct > 0 ? "+" : ""}{check.difference_pct}%</b></span>
              </li>
            ))}
          </ul>
        )}
        {rejecting ? (
          <div className="proof-actions">
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why? The shopper sees this" aria-label="Reason for rejecting" />
            <IconButton icon="check" label="Confirm reject" className="danger" disabled={!reason.trim()} onClick={() => decide("reject")} />
            <IconButton icon="close" label="Cancel" onClick={() => setRejecting(false)} />
          </div>
        ) : (
          <div className="proof-actions">
            <label className="proof-price">₱<input type="number" min="0.01" step="0.01" value={price} aria-label="Price to publish" onChange={(e) => setPrice(e.target.value)} /></label>
            <button className="btn primary with-icon" disabled={!(Number(price) > 0)} onClick={() => decide("approve")}><Icon name="check" />Approve</button>
            <IconButton icon="ban" label="Reject" onClick={() => setRejecting(true)} />
          </div>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </div>
    </article>
  );
}

export function ProofQueue({ onChanged }: { onChanged: () => void }) {
  const [proofs, setProofs] = useState<Proof[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = () => api<Proof[]>("/admin/proofs", {}, true).then(setProofs).catch(() => setProofs([]));
  useEffect(() => { load(); }, []);

  return (
    <section className="card">
      <h2>Price proofs to review {proofs && proofs.length > 0 && <span className="count-badge">{proofs.length}</span>}</h2>
      <p className="muted">Shoppers' photos are compared with what we already know. Two shoppers who agree at the same store are verified automatically.</p>
      {notice && <p className="notice" role="status">{notice}</p>}
      {proofs?.length === 0 && <p className="muted">Nothing waiting for review.</p>}
      <div className="proof-list">
        {proofs?.map((proof) => (
          <ProofCard key={proof.id} proof={proof} onDecided={(message) => { setNotice(message); load(); onChanged(); }} />
        ))}
      </div>
    </section>
  );
}
