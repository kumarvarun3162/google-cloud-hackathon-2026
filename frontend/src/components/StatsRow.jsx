import { useTranslation } from "react-i18next";
import { TrendingUp, Tag, MapPin } from "lucide-react";
import { getCategory } from "../lib/categories";

export default function StatsRow({ stats }) {
  const { t } = useTranslation();
  const topCategory = getCategory(stats.top_category);

  const items = [
    {
      icon: TrendingUp,
      label: t("priorities.stats_total"),
      value: stats.total_submissions_week.toLocaleString(),
    },
    {
      icon: Tag,
      label: t("priorities.stats_top_category"),
      value: t(topCategory.labelKey),
    },
    {
      icon: MapPin,
      label: t("priorities.stats_top_location"),
      value: stats.top_location,
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {items.map(({ icon: Icon, label, value }) => (
        <div
          key={label}
          className="flex items-center gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-primary/10"
        >
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-light text-primary">
            <Icon className="h-5 w-5" strokeWidth={1.75} />
          </div>
          <div className="min-w-0">
            <p className="truncate text-xs font-medium uppercase tracking-wide text-muted">
              {label}
            </p>
            <p className="truncate font-display text-lg font-semibold text-ink">{value}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
