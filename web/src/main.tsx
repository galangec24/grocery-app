import { createRoot } from "react-dom/client";
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
    return <LocationProvider><Shop path={pathname} /></LocationProvider>;
  }
  if (pathname !== "/") navigate("/");
  return <LocationProvider><Landing /></LocationProvider>;
}

createRoot(document.getElementById("root")!).render(<App />);
