import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import MPHeader from "../components/MPHeader";
import StatsRow from "../components/StatsRow";
import PriorityCard from "../components/PriorityCard";
import { StatsRowSkeleton, PriorityCardSkeleton } from "../components/PrioritySkeleton";
import CompareBar from "../components/CompareBar";
import ComparisonModal from "../components/ComparisonModal";
import { getPriorities } from "../lib/api";

export default function PrioritiesPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const highlightHotspotId = searchParams.get("highlight");

  const [data, setData] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const highlightedRef = useRef(null);

  const [selectedIds, setSelectedIds] = useState([]);
  const [comparing, setComparing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");

    getPriorities()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Once the (slow) data arrives, scroll the card that was opened from the
  // map's sidebar into view, so the "View in priority list" link actually
  // feels connected rather than dropping the MP at the top of a long list.
  useEffect(() => {
    if (status === "ready" && highlightedRef.current) {
      highlightedRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [status]);

  function toggleSelect(id) {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((existing) => existing !== id);
      if (prev.length >= 2) return prev; // guarded in the UI too via selectionDisabled
      return [...prev, id];
    });
  }

  return (
    <div className="flex h-screen flex-col bg-surface">
      <MPHeader />

      <div className="mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-4 pb-28 pt-6 sm:px-6">
        <div className="mb-6">
          <span className="text-xs font-semibold uppercase tracking-wide text-accent-dark">
            {t("priorities.eyebrow")}
          </span>
          <h1 className="mt-1 font-display text-2xl font-semibold text-ink">
            {t("priorities.title")}
          </h1>
        </div>

        {status === "loading" && (
          <div className="flex flex-col gap-6">
            <StatsRowSkeleton />
            <div className="flex flex-col gap-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <PriorityCardSkeleton key={i} />
              ))}
            </div>
          </div>
        )}

        {status === "error" && (
          <div className="rounded-2xl bg-white p-6 text-center text-sm text-red-700 shadow-sm">
            {t("priorities.error")}
          </div>
        )}

        {status === "ready" && data && (
          <div className="flex flex-col gap-6">
            <StatsRow stats={data.stats} />

            {highlightHotspotId && (
              <p className="rounded-xl bg-primary-light px-4 py-2.5 text-sm text-primary">
                {t("priorities.highlighted_banner")}
              </p>
            )}

            <div className="flex flex-col gap-3">
              {data.items.map((item) => {
                const isHighlighted = item.hotspot_id === highlightHotspotId;
                const isSelected = selectedIds.includes(item.id);
                return (
                  <PriorityCard
                    key={item.id}
                    item={item}
                    highlighted={isHighlighted}
                    cardRef={isHighlighted ? highlightedRef : undefined}
                    selected={isSelected}
                    selectionDisabled={!isSelected && selectedIds.length >= 2}
                    onToggleSelect={toggleSelect}
                  />
                );
              })}
            </div>
          </div>
        )}
      </div>

      <CompareBar
        selectedIds={selectedIds}
        onClear={() => setSelectedIds([])}
        onCompare={() => setComparing(true)}
      />

      {comparing && selectedIds.length === 2 && (
        <ComparisonModal
          idA={selectedIds[0]}
          idB={selectedIds[1]}
          onClose={() => setComparing(false)}
        />
      )}
    </div>
  );
}
