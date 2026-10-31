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

function GoogleLogo() {
  return (
    <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

function AccountDialog({ onClose, onDone }: { onClose: () => void; onDone: (user: Shopper) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<"login" | "register">("register");
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { dialog.current?.showModal(); }, []);

  async function withGoogle() {
    setError(null);
    try {
      const { googleIdToken } = await import("./google");
      const result = await postJson<{ access_token: string; refresh_token: string; user: Shopper }>("/auth/google", { id_token: await googleIdToken() });
      shopperSession.set(result);
      onDone(result.user);
      dialog.current?.close();
    } catch (e) {
      const code = (e as { code?: string }).code;
      if (code === "auth/popup-closed-by-user" || code === "auth/cancelled-popup-request") return;
      const notReady = code === "auth/operation-not-allowed" || code === "auth/configuration-not-found";
      setError(notReady ? "Google sign-in isn't switched on yet. Use your email for now." : (e as Error).message);
    }
  }

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
        <button type="button" className="google-btn" onClick={withGoogle}><GoogleLogo /><span>Continue with Google</span></button>
        <p className="or"><span>or use your email</span></p>
        {mode === "register" && (
          <label>Your name<span className="field"><Icon name="user" size={18} /><input required minLength={2} autoComplete="name" placeholder="Juan Dela Cruz" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></span></label>
        )}
        <label>Email<span className="field"><Icon name="mail" size={18} /><input required type="email" autoComplete="username" placeholder="you@example.com" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></span></label>
        <label>Password<span className="field"><Icon name="lock" size={18} /><input required type="password" minLength={mode === "register" ? 10 : 1} autoComplete={mode === "register" ? "new-password" : "current-password"} placeholder={mode === "register" ? "At least 10 characters" : "Your password"} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></span></label>
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
