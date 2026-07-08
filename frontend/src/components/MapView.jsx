import { useEffect, useRef, useState } from "react";
import { Loader } from "@googlemaps/js-api-loader";
import { useTranslation } from "react-i18next";
import { getCategory } from "../lib/categories";

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
// Google's public "DEMO_MAP_ID" works for local development without any
// Cloud Console setup. Swap in a real Map ID (Cloud Console > Map
// Management) before shipping, ideally with a styled theme to match brand.
const MAP_ID = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID || "DEMO_MAP_ID";

const CENTER = { lat: 29.55, lng: 76.85 }; // roughly centered on the constituencies in mock data
const DEFAULT_ZOOM = 9;

function markerScale(size, min, max) {
  if (max === min) return 28;
  const t = (size - min) / (max - min);
  return 18 + t * 30; // 18px–48px diameter
}

function buildPinElement(feature, min, max, isSelected) {
  const { category, cluster_size } = feature.properties;
  const meta = getCategory(category);
  const diameter = Math.round(markerScale(cluster_size, min, max));

  const el = document.createElement("div");
  el.style.width = `${diameter}px`;
  el.style.height = `${diameter}px`;
  el.style.borderRadius = "9999px";
  el.style.background = meta.color;
  el.style.border = isSelected ? "3px solid #E98A15" : "2px solid white";
  el.style.boxShadow = isSelected
    ? "0 0 0 3px rgba(233, 138, 21, 0.25), 0 1px 4px rgba(11, 32, 39, 0.35)"
    : "0 1px 4px rgba(11, 32, 39, 0.35)";
  el.style.cursor = "pointer";
  el.style.display = "flex";
  el.style.alignItems = "center";
  el.style.justifyContent = "center";
  el.style.color = "white";
  el.style.fontFamily = "var(--font-mono)";
  el.style.fontSize = diameter > 30 ? "11px" : "9px";
  el.style.fontWeight = "600";
  el.textContent = String(cluster_size);
  return el;
}

export default function MapView({ hotspots, onSelectHotspot, selectedId }) {
  const { t } = useTranslation();
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef([]);
  const [loadState, setLoadState] = useState(API_KEY ? "loading" : "no-key");

  // Initialize the map once.
  useEffect(() => {
    if (!API_KEY) return;
    let cancelled = false;

    const loader = new Loader({ apiKey: API_KEY, version: "weekly" });

    loader
      .importLibrary("maps")
      .then(({ Map }) => {
        if (cancelled || !containerRef.current) return;
        mapRef.current = new Map(containerRef.current, {
          center: CENTER,
          zoom: DEFAULT_ZOOM,
          mapId: MAP_ID,
          disableDefaultUI: false,
          streetViewControl: false,
          fullscreenControl: false,
        });
        setLoadState("ready");
      })
      .catch(() => setLoadState("error"));

    return () => {
      cancelled = true;
    };
  }, []);

  // Sync markers whenever the filtered hotspot list changes.
  useEffect(() => {
    if (loadState !== "ready") return;

    let cancelled = false;

    window.google.maps.importLibrary("marker").then(({ AdvancedMarkerElement }) => {
      if (cancelled) return;

      markersRef.current.forEach((m) => (m.map = null));
      markersRef.current = [];

      if (hotspots.length === 0) return;

      const sizes = hotspots.map((f) => f.properties.cluster_size);
      const min = Math.min(...sizes);
      const max = Math.max(...sizes);

      hotspots.forEach((feature) => {
        const [lng, lat] = feature.geometry.coordinates;
        const marker = new AdvancedMarkerElement({
          map: mapRef.current,
          position: { lat, lng },
          content: buildPinElement(feature, min, max, feature.properties.id === selectedId),
          title: `${feature.properties.category} (${feature.properties.cluster_size})`,
        });
        marker.addListener("click", () => onSelectHotspot(feature));
        markersRef.current.push(marker);
      });
    });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadState, hotspots, selectedId]);

  if (loadState === "no-key") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 bg-primary-light px-6 text-center">
        <p className="font-display text-lg font-semibold text-primary">
          {t("map.missing_key_title")}
        </p>
        <p className="max-w-sm text-sm text-muted">{t("map.missing_key_body")}</p>
      </div>
    );
  }

  if (loadState === "error") {
    return (
      <div className="flex h-full items-center justify-center bg-primary-light px-6 text-center text-sm text-red-700">
        {t("map.error")}
      </div>
    );
  }

  return <div ref={containerRef} className="h-full w-full" />;
}
