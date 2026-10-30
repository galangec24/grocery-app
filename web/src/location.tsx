import { Geolocation } from "@capacitor/geolocation";
import { Preferences } from "@capacitor/preferences";
import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { isNative } from "./api";

export interface Place {
  label: string;
  latitude: number;
  longitude: number;
  source: "device" | "manual";
}

export const AREAS: Place[] = [
  { label: "Cebu City", latitude: 10.3157, longitude: 123.8854, source: "manual" },
  { label: "Mandaue City", latitude: 10.3236, longitude: 123.9223, source: "manual" },
  { label: "Lapu-Lapu City", latitude: 10.3103, longitude: 123.9494, source: "manual" },
  { label: "Talisay City", latitude: 10.2447, longitude: 123.8494, source: "manual" },
];

const KEY = "manual_area";

interface LocationState {
  place: Place | null;
  locating: boolean;
  error: string | null;
  useDevice: () => Promise<void>;
  chooseArea: (label: string) => void;
}

const LocationContext = createContext<LocationState>(null!);
export const useLocation = () => useContext(LocationContext);

export function LocationProvider({ children }: { children: ReactNode }) {
  const [place, setPlace] = useState<Place | null>(null);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Preferences.get({ key: KEY }).then(({ value }) => {
      setPlace(AREAS.find((a) => a.label === value) ?? null);
    });
  }, []);

  const value = useMemo<LocationState>(() => ({
    place,
    locating,
    error,
    // Asked only when the shopper taps it. Device coordinates stay in memory and are never saved.
    async useDevice() {
      setLocating(true);
      setError(null);
      try {
        if (isNative) {
          const status = await Geolocation.requestPermissions({ permissions: ["location"] });
          if (status.location === "denied") throw new Error("denied");
        }
        const { coords } = await Geolocation.getCurrentPosition({ timeout: 10000 });
        setPlace({ label: "Current location", latitude: coords.latitude, longitude: coords.longitude, source: "device" });
      } catch {
        setError("Location isn't available. Choose your area below; search still works without it.");
      } finally {
        setLocating(false);
      }
    },
    chooseArea(label) {
      setError(null);
      const area = AREAS.find((a) => a.label === label) ?? null;
      setPlace(area);
      if (area) Preferences.set({ key: KEY, value: label });
      else Preferences.remove({ key: KEY });
    },
  }), [place, locating, error]);

  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>;
}
