import { useEffect, useState } from "react";

const current = () => window.location.hash.replace(/^#/, "") || "/";

export function useRoute() {
  const [path, setPath] = useState(current);
  useEffect(() => {
    const update = () => {
      setPath(current());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  const [pathname, search = ""] = path.split("?");
  return { pathname, params: new URLSearchParams(search) };
}

export const navigate = (path: string) => {
  window.location.hash = path;
};
