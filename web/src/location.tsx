import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { api, CityInfo, query } from "./api";

interface LocationState {
  city: CityInfo | null;
  busy: boolean;
  error: string | null;
  locate: () => void;
  chooseCity: (name: string) => Promise<void>;
  clear: () => void;
}

const LocationContext = createContext<LocationState>(null!);
export const useLocation = () => useContext(LocationContext);

export function LocationProvider({ children }: { children: ReactNode }) {
  const [city, setCity] = useState<CityInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const value = useMemo<LocationState>(() => {
    const resolve = async (params: Record<string, string | number>) => {
      setBusy(true);
      setError(null);
      try {
        setCity(await api<CityInfo>(`/location/resolve${query(params)}`));
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    };
    return {
      city, busy, error,
      // Asked only when the shopper taps it. The browser location is used once and not kept.
      locate() {
        if (!navigator.geolocation) {
          setError("This browser can't share a location. Type your city instead.");
          return;
        }
        setBusy(true);
        setError(null);
        navigator.geolocation.getCurrentPosition(
          ({ coords }) => resolve({ latitude: coords.latitude, longitude: coords.longitude }),
          () => {
            setBusy(false);
            setError("We couldn't get your location. Type your city and everything still works.");
          },
          { timeout: 12000 },
        );
      },
      chooseCity: (name) => resolve({ city: name }),
      clear: () => { setCity(null); setError(null); },
    };
  }, [city, busy, error]);

  // Finds the shopper's city on arrival. The browser still asks permission the first time.
  useEffect(() => {
    let live = true;
    const start = () => { if (live) value.locate(); };
    if (navigator.permissions?.query) {
      navigator.permissions.query({ name: "geolocation" })
        .then((status) => { if (status.state !== "denied") start(); })
        .catch(start);
    } else {
      start();
    }
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>;
}
