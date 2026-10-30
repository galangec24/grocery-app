import { PriceBoard } from "../site/PriceBoard";
import { DraftEditor, DraftList, QuickCompare } from "./Drafts";

const TABS = [
  ["/shop", "Prices", "₱"],
  ["/shop/compare", "Multi search", "☰"],
  ["/shop/drafts", "Drafts", "✎"],
];

export function Shop({ path }: { path: string }) {
  const [, , section, id] = path.split("/");
  let page;
  if (section === "compare") page = <QuickCompare />;
  else if (section === "drafts") page = id ? <DraftEditor key={id} id={id} /> : <DraftList />;
  else page = <><h1>Today's prices</h1><PriceBoard compact /></>;

  const active = `/shop${section ? `/${section}` : ""}`;
  return (
    <div className="shop">
      <header className="shop-bar">
        <a className="brand" href="#/"><span className="brand-mark">₱</span> Grocery Price Finder</a>
      </header>
      <main className="shop-page">{page}</main>
      <nav className="tabs" aria-label="Main">
        {TABS.map(([to, label, icon]) => (
          <a key={to} href={`#${to}`} className={active === to ? "on" : ""} aria-current={active === to ? "page" : undefined}>
            <span aria-hidden>{icon}</span>{label}
          </a>
        ))}
      </nav>
    </div>
  );
}
