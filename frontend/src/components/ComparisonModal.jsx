import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { X, Printer, MapPin } from "lucide-react";
import { getCategory } from "../lib/categories";
import { compareProjects } from "../lib/api";

const GAP_KEY = {
  severe: "priorities.gap_severe",
  moderate: "priorities.gap_moderate",
  minor: "priorities.gap_minor",
};

export default function ComparisonModal({ idA, idB, onClose }) {
  const { t } = useTranslation();
  const [pair, setPair] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | ready | error

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");

    compareProjects(idA, idB)
      .then((result) => {
        if (cancelled) return;
        setPair(result);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [idA, idB]);

  // Escape to close, disabled while printing dialog itself is open (browser
  // handles that natively — this just covers the modal's own keyboard UX).
  useEffect(() => {
    function handleKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center bg-ink/40 p-0 print:static print:bg-white sm:items-center sm:p-4">
      <div className="print-target flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-t-2xl bg-white shadow-2xl print:max-h-none print:overflow-visible print:rounded-none print:shadow-none sm:rounded-2xl">
        <div className="flex items-center justify-between border-b border-primary/10 p-5 print:hidden">
          <h2 className="font-display text-lg font-semibold text-ink">{t("compare.title")}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("compare.close")}
            className="rounded-full p-1.5 text-muted hover:bg-primary-light hover:text-primary"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 print:overflow-visible">
          {status === "loading" && (
            <div className="flex h-40 items-center justify-center text-sm text-muted">
              {t("compare.loading")}
            </div>
          )}

          {status === "error" && (
            <div className="flex h-40 items-center justify-center text-sm text-red-700">
              {t("compare.error")}
            </div>
          )}

          {status === "ready" && pair && <ComparisonTable pair={pair} t={t} />}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-primary/10 p-5 print:hidden">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl px-4 py-2.5 text-sm font-medium text-muted hover:bg-primary-light hover:text-primary"
          >
            {t("compare.close")}
          </button>
          <button
            type="button"
            onClick={() => window.print()}
            disabled={status !== "ready"}
            className="flex items-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Printer className="h-4 w-4" strokeWidth={1.75} />
            {t("compare.download_pdf")}
          </button>
        </div>
      </div>
    </div>
  );
}

function ComparisonTable({ pair, t }) {
  const { a, b } = pair;
  const columns = [a, b];

  const rows = [
    { label: t("compare.row_score"), render: (item) => item.priority_score },
    { label: t("compare.row_reports"), render: (item) => item.report_count },
    {
      label: t("compare.row_population"),
      render: (item) => item.detail.affected_population.toLocaleString(),
    },
    {
      label: t("compare.row_infra_gap"),
      render: (item) => t(GAP_KEY[item.detail.infrastructure_gap]),
    },
    {
      label: t("compare.row_distance"),
      render: (item) => `${item.detail.distance_to_facility_km} km`,
    },
  ];

  return (
    <div>
      {/* Project headers */}
      <div className="grid grid-cols-2 gap-4">
        {columns.map((item) => {
          const category = getCategory(item.category);
          return (
            <div key={item.id}>
              <span
                className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold text-white"
                style={{ backgroundColor: category.color }}
              >
                {t(category.labelKey)}
              </span>
              <p className="mt-2 font-display text-base font-semibold leading-snug text-ink">
                {item.title}
              </p>
              <span className="mt-1 flex items-center gap-1 text-xs text-muted">
                <MapPin className="h-3.5 w-3.5" />
                {item.location}
              </span>
            </div>
          );
        })}
      </div>

      {/* Metric rows */}
      <div className="mt-5 divide-y divide-primary/10 rounded-xl border border-primary/10">
        {rows.map((row) => (
          <div key={row.label} className="grid grid-cols-2 gap-4 px-4 py-3">
            <div className="col-span-2 -mb-1 text-xs font-medium uppercase tracking-wide text-muted">
              {row.label}
            </div>
            {columns.map((item) => (
              <p key={item.id} className="text-sm font-semibold text-ink">
                {row.render(item)}
              </p>
            ))}
          </div>
        ))}
      </div>

      {/* AI justification */}
      <div className="mt-5 grid grid-cols-2 gap-4">
        {columns.map((item) => (
          <div key={item.id} className="rounded-xl bg-surface p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">
              {t("compare.row_justification")}
            </p>
            <p className="mt-1 text-sm italic text-ink/80">{item.ai_explanation}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
