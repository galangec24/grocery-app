import { createContext, FormEvent, ReactNode, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, postJson, shopperSession } from "./api";
import { Icon } from "./icons";

interface Shopper {
  id: string;
  email: string;
  full_name: string;
}

interface AccountState {
  user: Shopper | null;
  ask: () => void;
  signOut: () => void;
}

const AccountContext = createContext<AccountState>(null!);
export const useAccount = () => useContext(AccountContext);

export function AccountProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Shopper | null>(null);
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    if (!shopperSession.get()) return;
    api<Shopper>("/users/me", {}, "shopper").then(setUser).catch(() => shopperSession.clear());
  }, []);

  const value = useMemo<AccountState>(() => ({
    user,
    ask: () => setAsking(true),
    signOut() {
      shopperSession.clear();
      setUser(null);
    },
  }), [user]);

  return (
    <AccountContext.Provider value={value}>
      {children}
      {asking && <AccountDialog onClose={() => setAsking(false)} onDone={setUser} />}
    </AccountContext.Provider>
  );
}

function AccountDialog({ onClose, onDone }: { onClose: () => void; onDone: (user: Shopper) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<"login" | "register">("register");
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { dialog.current?.showModal(); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const body = mode === "register" ? form : { email: form.email, password: form.password };
      const result = await postJson<{ access_token: string; refresh_token: string; user: Shopper }>(`/auth/${mode}`, body);
      shopperSession.set(result);
      onDone(result.user);
      dialog.current?.close();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <dialog ref={dialog} className="modal" onClose={onClose}>
      <form className="modal-card account-card" onSubmit={submit}>
        <button type="button" className="modal-close" aria-label="Close" onClick={() => dialog.current?.close()}><Icon name="close" size={18} /></button>
        <h2>{mode === "register" ? "Join the price community" : "Welcome back"}</h2>
        <p className="muted">Sign in to share what you paid and help shoppers in your city. Lists and drafts work without an account.</p>
        {mode === "register" && (
          <label>Your name<input required minLength={2} autoComplete="name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
        )}
        <label>Email<input required type="email" autoComplete="username" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label>Password<input required type="password" minLength={mode === "register" ? 10 : 1} autoComplete={mode === "register" ? "new-password" : "current-password"} placeholder={mode === "register" ? "At least 10 characters" : ""} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn primary block">{mode === "register" ? "Create account" : "Sign in"}</button>
        <button type="button" className="link" onClick={() => { setMode(mode === "register" ? "login" : "register"); setError(null); }}>
          {mode === "register" ? "Already have an account? Sign in" : "New here? Create an account"}
        </button>
      </form>
    </dialog>
  );
}

/** Photos are shrunk on the device, which saves data and storage. */
export async function shrinkPhoto(file: File, longestSide = 1280, quality = 0.72): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, longestSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("That photo couldn't be read"))), "image/jpeg", quality);
  });
}
