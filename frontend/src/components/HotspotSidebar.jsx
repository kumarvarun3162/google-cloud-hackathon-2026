import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { X, MessageSquareQuote } from "lucide-react";
import { getCategory } from "../lib/categories";

export default function HotspotSidebar({ hotspot, onClose }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  if (!hotspot) return null;
  const { properties } = hotspot;
  const category = getCategory(properties.category);

  return (
    <aside className="absolute inset-y-0 right-0 z-20 flex w-full max-w-sm flex-col bg-white shadow-2xl sm:inset-y-2 sm:right-2 sm:rounded-2xl">
      <div className="flex items-start justify-between border-b border-primary/10 p-5">
        <div>
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold text-white"
            style={{ backgroundColor: category.color }}
          >
            {t(category.labelKey)}
          </span>
          <p className="mt-2 text-2xl font-semibold text-ink">
            {properties.report_count}{" "}
            <span className="text-sm font-normal text-muted">
              {t("map.sidebar_reports")}
            </span>
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("map.sidebar_close")}
          className="rounded-full p-1.5 text-muted hover:bg-primary-light hover:text-primary"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">
          {t("map.sidebar_last_updated")}
        </p>
        <p className="mt-1 text-sm text-ink">{properties.last_report_date}</p>

        <p className="mt-5 text-xs font-medium uppercase tracking-wide text-muted">
          {t("map.sidebar_top_complaints")}
        </p>
        <ul className="mt-2 flex flex-col gap-3">
          {properties.top_complaints.map((excerpt, i) => (
            <li key={i} className="flex gap-2 rounded-xl bg-surface p-3 text-sm text-ink">
              <MessageSquareQuote
                className="mt-0.5 h-4 w-4 shrink-0 text-primary/60"
                strokeWidth={1.75}
              />
              {excerpt}
            </li>
          ))}
        </ul>
      </div>

      <div className="border-t border-primary/10 p-5">
        <button
          type="button"
          onClick={() => navigate(`/priorities?highlight=${properties.id}`)}
          className="w-full rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-primary-dark"
        >
          {t("map.sidebar_view_priority")}
        </button>
      </div>
    </aside>
  );
}
