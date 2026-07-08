import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import constituencies from "../mocks/constituencies.json";
import { CATEGORIES } from "../lib/categories";

export default function FilterBar({ filters, onChange }) {
  const { t } = useTranslation();

  const hasActiveFilters = Object.values(filters).some(Boolean);
  const selectClasses =
    "rounded-lg border border-primary/20 bg-white px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";

  function update(key, value) {
    onChange({ ...filters, [key]: value });
  }

  function clearAll() {
    onChange({ category: "", constituency: "", from: "", to: "" });
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-primary/10 bg-white px-4 py-3 sm:px-6">
      <select
        value={filters.category}
        onChange={(e) => update("category", e.target.value)}
        className={selectClasses}
        aria-label={t("map.filter_category")}
      >
        <option value="">{t("map.filter_category_all")}</option>
        {CATEGORIES.map((c) => (
          <option key={c.id} value={c.id}>
            {t(c.labelKey)}
          </option>
        ))}
      </select>

      <select
        value={filters.constituency}
        onChange={(e) => update("constituency", e.target.value)}
        className={selectClasses}
        aria-label={t("map.filter_constituency")}
      >
        <option value="">{t("map.filter_constituency_all")}</option>
        {constituencies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      <label className="flex items-center gap-1.5 text-sm text-muted">
        {t("map.filter_from")}
        <input
          type="date"
          value={filters.from}
          onChange={(e) => update("from", e.target.value)}
          className={selectClasses}
        />
      </label>

      <label className="flex items-center gap-1.5 text-sm text-muted">
        {t("map.filter_to")}
        <input
          type="date"
          value={filters.to}
          onChange={(e) => update("to", e.target.value)}
          className={selectClasses}
        />
      </label>

      {hasActiveFilters && (
        <button
          type="button"
          onClick={clearAll}
          className="flex items-center gap-1 rounded-lg px-2 py-2 text-sm font-medium text-primary hover:bg-primary-light"
        >
          <X className="h-3.5 w-3.5" />
          {t("map.filter_clear")}
        </button>
      )}
    </div>
  );
}
