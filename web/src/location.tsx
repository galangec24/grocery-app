import { createContext, ReactNode, useContext, useMemo, useState } from "react";
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
            setError("Location is turned off. Type your city instead; everything still works.");
          },
          { timeout: 12000 },
        );
      },
      chooseCity: (name) => resolve({ city: name }),
      clear: () => { setCity(null); setError(null); },
    };
  }, [city, busy, error]);

  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>;
}
