import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api, LiveState } from "./api";
import { timeAgo } from "./format";

const POLL_MS = 30000;
const LiveContext = createContext<LiveState>({ version: 0, updated_at: null, checked_at: null });

/** The version number changes whenever prices do, so screens reload by themselves. */
export const useLive = () => useContext(LiveContext);

export function LiveProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LiveState>({ version: 0, updated_at: null, checked_at: null });

  useEffect(() => {
    const check = () => {
      if (document.hidden) return;
      api<LiveState>("/market/live").then(setState).catch(() => undefined);
    };
    check();
    const timer = setInterval(check, POLL_MS);
    document.addEventListener("visibilitychange", check);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
    };
  }, []);

  return <LiveContext.Provider value={state}>{children}</LiveContext.Provider>;
}

export function LiveBadge() {
  const { checked_at: checked, updated_at: updated } = useLive();
  if (!checked && !updated) return null;
  return (
    <span className="live-badge" title={updated ? `Prices last changed ${timeAgo(updated)}` : undefined}>
      <i aria-hidden="true" /> Live · checked {timeAgo(checked)}
    </span>
  );
}
