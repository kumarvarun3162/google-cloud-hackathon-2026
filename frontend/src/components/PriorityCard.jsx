import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, MapPin, Users, Construction, Navigation, Sparkles, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { getCategory } from "../lib/categories";
import ScoreRing from "./ScoreRing";

const GAP_KEY = {
  severe: "priorities.gap_severe",
  moderate: "priorities.gap_moderate",
  minor: "priorities.gap_minor",
};

const TREND_KEY = {
  up: "priorities.trend_up",
  steady: "priorities.trend_steady",
  down: "priorities.trend_down",
};

const TREND_ICON = {
  up: TrendingUp,
  steady: Minus,
  down: TrendingDown,
};

export default function PriorityCard({
  item,
  highlighted,
  cardRef,
  selected = false,
  selectionDisabled = false,
  onToggleSelect,
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const category = getCategory(item.category);

  function handleKeyDown(event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setExpanded((v) => !v);
    }
  }

  return (
    <div
      ref={cardRef}
      className={`rounded-2xl bg-white shadow-sm ring-1 transition-shadow ${
        highlighted ? "ring-2 ring-accent" : selected ? "ring-2 ring-primary" : "ring-primary/10"
      }`}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={handleKeyDown}
        aria-expanded={expanded}
        className="flex w-full cursor-pointer items-start gap-4 p-5 text-left"
      >
        <label
          onClick={(e) => e.stopPropagation()}
          className={`mt-1 flex shrink-0 items-center ${
            selectionDisabled ? "cursor-not-allowed opacity-40" : "cursor-pointer"
          }`}
          title={selectionDisabled ? t("priorities.select_limit") : t("priorities.select_label")}
        >
          <input
            type="checkbox"
            checked={selected}
            disabled={selectionDisabled}
            onChange={() => onToggleSelect?.(item.id)}
            className="h-4 w-4 rounded border-primary/30 text-primary focus:ring-2 focus:ring-primary/30"
          />
          <span className="sr-only">{t("priorities.select_label")}</span>
        </label>

        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink font-display text-sm font-semibold text-white">
          {item.rank}
        </span>

        <ScoreRing score={item.priority_score} />

        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span
              className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold text-white"
              style={{ backgroundColor: category.color }}
            >
              {t(category.labelKey)}
            </span>
            <span className="flex items-center gap-1 text-xs text-muted">
              <MapPin className="h-3.5 w-3.5" />
              {item.location}
            </span>
          </div>
          <p className="font-display text-base font-semibold leading-snug text-ink">
            {item.title}
          </p>
          <p className="mt-1 text-sm text-muted">
            {item.report_count} {t("map.sidebar_reports")}
          </p>
        </div>

        <ChevronDown
          className={`mt-1 h-5 w-5 shrink-0 text-muted transition-transform ${
            expanded ? "rotate-180" : ""
          }`}
        />
      </div>

      {/* AI explanation is always visible — it's the whole point of the card */}
      <div className="flex gap-2 border-t border-primary/10 px-5 py-3">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary/60" strokeWidth={1.75} />
        <p className="text-sm italic text-ink/80">{item.ai_explanation}</p>
      </div>

      {expanded && (
        <div className="grid grid-cols-1 gap-4 border-t border-primary/10 p-5 sm:grid-cols-2 lg:grid-cols-4">
          <Stat
            icon={TREND_ICON[item.detail.trend]}
            label={t("priorities.detail_trend")}
            value={t(TREND_KEY[item.detail.trend])}
          />
          <Stat
            icon={Users}
            label={t("priorities.detail_population")}
            value={item.detail.affected_population.toLocaleString()}
          />
          <Stat
            icon={Construction}
            label={t("priorities.detail_infra_gap")}
            value={t(GAP_KEY[item.detail.infrastructure_gap])}
          />
          <Stat
            icon={Navigation}
            label={t("priorities.detail_distance")}
            value={`${item.detail.distance_to_facility_km} km`}
          />
          <div className="sm:col-span-2 lg:col-span-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">
              {t("priorities.detail_recommended")}
            </p>
            <p className="mt-1 text-sm text-ink">{item.detail.recommended_action}</p>
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full border-t border-primary/10 py-2 text-xs font-medium text-primary hover:bg-primary-light"
      >
        {expanded ? t("priorities.expand_less") : t("priorities.expand_more")}
      </button>
    </div>
  );
}

function Stat({ icon: Icon, label, value }) {
  return (
    <div className="flex items-start gap-2">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary/60" strokeWidth={1.75} />
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
        <p className="text-sm font-medium text-ink">{value}</p>
      </div>
    </div>
  );
}
