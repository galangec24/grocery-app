import { createContext, ReactNode, useContext, useMemo, useState } from "react";
import { peso } from "./format";

const KEY = "budget_v1";

interface BudgetState {
  budget: number | null;
  spent: number;
  setBudget: (value: number | null) => void;
  setSpent: (value: number) => void;
}

const BudgetContext = createContext<BudgetState>(null!);
export const useBudget = () => useContext(BudgetContext);

export function BudgetProvider({ children }: { children: ReactNode }) {
  const [budget, set] = useState<number | null>(() => {
    const saved = Number(localStorage.getItem(KEY));
    return saved > 0 ? saved : null;
  });
  const [spent, setSpent] = useState(0);

  const value = useMemo<BudgetState>(() => ({
    budget, spent, setSpent,
    setBudget(next) {
      set(next);
      if (next) localStorage.setItem(KEY, String(next));
      else localStorage.removeItem(KEY);
    },
  }), [budget, spent]);

  return <BudgetContext.Provider value={value}>{children}</BudgetContext.Provider>;
}

/** Always on screen, so the shopper sees what's left as the list changes. */
export function BudgetBar() {
  const { budget, spent, setBudget } = useBudget();
  const left = budget === null ? 0 : budget - spent;
  const used = budget ? Math.min((spent / budget) * 100, 100) : 0;
  const over = budget !== null && left < 0;
  const near = budget !== null && !over && used >= 80;

  return (
    <div className={`budget-bar${over ? " over" : near ? " near" : ""}`}>
      <label>
        <span>My budget</span>
        <span className="budget-input">₱
          <input type="number" min="0" inputMode="decimal" placeholder="Amount" value={budget ?? ""}
            aria-label="Budget in pesos"
            onChange={(e) => setBudget(Number(e.target.value) > 0 ? Number(e.target.value) : null)} />
        </span>
      </label>
      {budget === null ? (
        <p className="budget-text">List total: <b>{peso(spent)}</b></p>
      ) : (
        <div className="budget-meter">
          <p className="budget-text">
            {peso(spent)} used · <b>{over ? `${peso(-left)} over budget` : `${peso(left)} left`}</b>
          </p>
          <div className="meter" role="progressbar" aria-valuenow={Math.round(used)} aria-valuemin={0} aria-valuemax={100} aria-label="Budget used">
            <span style={{ width: `${used}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}
