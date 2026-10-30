import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { isNative, loadServerUrl } from "./api";
import { LocationProvider } from "./location";
import { navigate, useRoute } from "./router";
import { Shop } from "./shop/Shop";
import { Dashboard } from "./site/Dashboard";
import { Landing } from "./site/Landing";
import "./styles.css";

function App() {
  const { pathname, params } = useRoute();
  const [ready, setReady] = useState(!isNative);

  useEffect(() => {
    if (isNative) loadServerUrl().then(() => setReady(true));
  }, []);

  if (!ready) return null;
  if (pathname.startsWith("/shop") || isNative) {
    const shopPath = isNative && !pathname.startsWith("/shop") ? "/shop" : pathname;
    return (
      <LocationProvider>
        <Shop path={shopPath} params={params} />
      </LocationProvider>
    );
  }
  if (pathname.startsWith("/dashboard")) return <Dashboard />;
  if (pathname !== "/") navigate("/");
  return <Landing />;
}

createRoot(document.getElementById("root")!).render(<App />);
