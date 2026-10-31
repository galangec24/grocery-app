import { createRoot } from "react-dom/client";
import { LiveProvider } from "./live";
import { LocationProvider } from "./location";
import { navigate, useRoute } from "./router";
import { Shop } from "./shop/Shop";
import { Dashboard } from "./site/Dashboard";
import { Landing } from "./site/Landing";
import "./styles.css";

function App() {
  const { pathname } = useRoute();
  if (pathname.startsWith("/dashboard")) return <Dashboard />;
  if (pathname.startsWith("/shop")) {
    return <LiveProvider><LocationProvider><Shop path={pathname} /></LocationProvider></LiveProvider>;
  }
  if (pathname !== "/") navigate("/");
  return <LiveProvider><LocationProvider><Landing /></LocationProvider></LiveProvider>;
}

createRoot(document.getElementById("root")!).render(<App />);
