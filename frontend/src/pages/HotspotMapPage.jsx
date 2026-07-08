import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import MPHeader from "../components/MPHeader";
import FilterBar from "../components/FilterBar";
import MapView from "../components/MapView";
import HotspotSidebar from "../components/HotspotSidebar";
import { getHotspots } from "../lib/api";

const EMPTY_FILTERS = { category: "", constituency: "", from: "", to: "" };

export default function HotspotMapPage() {
  const { t } = useTranslation();
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [hotspots, setHotspots] = useState([]);
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");

    getHotspots(filters)
      .then((data) => {
        if (cancelled) return;
        setHotspots(data.features);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [filters]);

  return (
    <div className="flex h-screen flex-col bg-surface">
      <MPHeader />
      <FilterBar filters={filters} onChange={setFilters} />

      <div className="relative flex-1">
        {status === "loading" && (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-muted">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t("map.loading")}
          </div>
        )}

        {status === "error" && (
          <div className="flex h-full items-center justify-center text-sm text-red-700">
            {t("map.error")}
          </div>
        )}

        {status === "ready" && hotspots.length === 0 && (
          <div className="flex h-full items-center justify-center text-sm text-muted">
            {t("map.filter_empty")}
          </div>
        )}

        {status === "ready" && hotspots.length > 0 && (
          <MapView
            hotspots={hotspots}
            selectedId={selected?.properties.id}
            onSelectHotspot={setSelected}
          />
        )}

        <HotspotSidebar hotspot={selected} onClose={() => setSelected(null)} />
      </div>
    </div>
  );
}
