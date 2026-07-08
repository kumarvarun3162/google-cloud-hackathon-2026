import { useTranslation } from "react-i18next";

const APP_LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "हिंदी" },
];

export default function LanguageSwitcher() {
  const { i18n, t } = useTranslation();

  return (
    <div
      className="flex items-center gap-1 rounded-full bg-white/70 p-1 shadow-sm ring-1 ring-primary/10"
      role="group"
      aria-label={t("language_switcher.label")}
    >
      {APP_LANGUAGES.map(({ code, label }) => {
        const active = i18n.resolvedLanguage === code;
        return (
          <button
            key={code}
            type="button"
            onClick={() => i18n.changeLanguage(code)}
            aria-pressed={active}
            className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
              active
                ? "bg-primary text-white"
                : "text-ink/70 hover:bg-primary-light"
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
