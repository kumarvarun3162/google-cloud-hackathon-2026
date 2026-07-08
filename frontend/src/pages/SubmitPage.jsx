import { useState } from "react";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "../components/LanguageSwitcher";
import SubmissionForm from "../components/SubmissionForm";
import ConfirmationCard from "../components/ConfirmationCard";

export default function SubmitPage() {
  const { t } = useTranslation();
  const [ticket, setTicket] = useState(null);

  return (
    <div className="min-h-screen bg-surface">
      <header className="mx-auto flex max-w-lg items-center justify-between px-5 pt-6">
        <span className="font-display text-lg font-semibold text-primary">
          {t("app.name")}
        </span>
        <LanguageSwitcher />
      </header>

      <main className="mx-auto max-w-lg px-5 pb-16 pt-8">
        {ticket ? (
          <ConfirmationCard ticket={ticket} onReset={() => setTicket(null)} />
        ) : (
          <>
            <div className="mb-6">
              <span className="text-xs font-semibold uppercase tracking-wide text-accent-dark">
                {t("submit.eyebrow")}
              </span>
              <h1 className="mt-1 font-display text-2xl font-semibold text-ink">
                {t("submit.title")}
              </h1>
              <p className="mt-2 text-sm text-muted">{t("submit.subtitle")}</p>
            </div>
            <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-primary/10 sm:p-6">
              <SubmissionForm onSuccess={setTicket} />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
