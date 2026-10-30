import { Hero3D, useTilt } from "../site/Hero3D";
import { PriceBoard } from "../site/PriceBoard";
import { DraftEditor, DraftList, QuickCompare } from "./Drafts";

const TABS = [
  ["/shop", "Prices", "₱"],
  ["/shop/compare", "Multi search", "☰"],
  ["/shop/drafts", "Drafts", "✎"],
];

export function Shop({ path }: { path: string }) {
  const [, , section, id] = path.split("/");
  const { scene, tilt } = useTilt();
  let page;
  if (section === "compare") page = <QuickCompare />;
  else if (section === "drafts") page = id ? <DraftEditor key={id} id={id} /> : <DraftList />;
  else page = <PriceBoard compact />;

  const active = `/shop${section ? `/${section}` : ""}`;
  return (
    <div className="shop">
      <header className="shop-hero" onPointerMove={tilt}>
        <a className="brand" href="#/"><img className="brand-mark" src="./logo.png" alt="" /> Grocery Price Finder</a>
        {!section && (
          <div className="shop-hero-body">
            <div>
              <p className="eyebrow">Official Philippine prices</p>
              <h1>Today's prices</h1>
            </div>
            <Hero3D scene={scene} count={3} />
          </div>
        )}
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
