import { useTranslation } from "react-i18next";
import { X, GitCompareArrows } from "lucide-react";

export default function CompareBar({ selectedIds, onClear, onCompare }) {
  const { t } = useTranslation();

  if (selectedIds.length === 0) return null;

  const message =
    selectedIds.length === 1 ? t("compare.bar_selected_one") : t("compare.bar_selected_two");

  return (
    <div className="fixed inset-x-0 bottom-0 z-20 flex justify-center px-4 pb-4 print:hidden">
      <div className="flex w-full max-w-md items-center gap-3 rounded-2xl bg-ink px-4 py-3 text-white shadow-xl">
        <p className="flex-1 text-sm">{message}</p>
        <button
          type="button"
          onClick={onClear}
          aria-label={t("compare.bar_clear")}
          className="rounded-full p-1.5 text-white/70 hover:bg-white/10 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onCompare}
          disabled={selectedIds.length < 2}
          className="flex items-center gap-1.5 rounded-xl bg-accent px-3.5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-white/15 disabled:text-white/50"
        >
          <GitCompareArrows className="h-4 w-4" strokeWidth={1.75} />
          {t("compare.bar_action")}
        </button>
      </div>
    </div>
  );
}
