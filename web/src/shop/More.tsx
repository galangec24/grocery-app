import { useState } from "react";
import { api, ApiError, getServerUrl, isNative, setServerUrl } from "../api";

export function MoreLinks() {
  const [url, setUrl] = useState(getServerUrl());
  const [result, setResult] = useState<string | null>(null);

  async function check() {
    setResult("Checking…");
    await setServerUrl(url);
    try {
      await api("/health");
      setResult("Connected.");
    } catch (e) {
      setResult(e instanceof ApiError ? e.message : "Couldn't connect.");
    }
  }

  return (
    <>
      <h1>More</h1>
      {isNative ? (
        <section className="card">
          <h2>Server</h2>
          <p className="muted">The address of the Grocery Price Finder backend.</p>
          <input className="field" type="url" value={url} aria-label="Server address" onChange={(e) => setUrl(e.target.value)} />
          <button className="btn primary block" onClick={check}>Save and test</button>
          {result && <p className="hint" role="status">{result}</p>}
        </section>
      ) : (
        <>
          <a className="row-link" href="#/"><span>About the app</span></a>
          <a className="row-link" href="#/dashboard"><span>Administrator dashboard</span></a>
        </>
      )}
      <section className="card">
        <h2>Your privacy</h2>
        <p className="muted">
          Location is used only when you ask for it, to measure distance to stores. It's sent with that
          search and isn't stored by this app. Drafts stay on this device.
        </p>
      </section>
    </>
  );
}
