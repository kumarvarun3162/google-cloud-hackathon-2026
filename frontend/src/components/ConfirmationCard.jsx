import { CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";

export default function ConfirmationCard({ ticket, onReset }) {
  const { t } = useTranslation();

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-6 py-10 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-success/10">
        <CheckCircle2 className="h-9 w-9 text-success" strokeWidth={1.75} />
      </div>

      <div>
        <h2 className="font-display text-2xl font-semibold text-ink">
          {t("submit.success_title")}
        </h2>
        <p className="mt-2 text-sm text-muted">{t("submit.success_body")}</p>
      </div>

      {/* Ticket stub: perforated edge on both sides via the .ticket-stub /
          .ticket-perforation classes defined in index.css */}
      <div className="ticket-stub flex w-full overflow-hidden rounded-2xl bg-white shadow-md ring-1 ring-primary/10">
        <div className="flex flex-1 flex-col items-start gap-1 p-6">
          <span className="text-xs font-medium uppercase tracking-wide text-muted">
            {t("submit.ticket_label")}
          </span>
          <span className="font-mono text-2xl font-semibold tracking-wider text-primary">
            {ticket}
          </span>
        </div>
        <div className="ticket-perforation flex w-20 items-center justify-center bg-primary-light text-primary">
          <CheckCircle2 className="h-6 w-6" strokeWidth={1.75} />
        </div>
      </div>

      <button
        type="button"
        onClick={onReset}
        className="text-sm font-medium text-primary underline decoration-primary/30 underline-offset-4 hover:decoration-primary"
      >
        {t("submit.success_new")}
      </button>
    </div>
  );
}
