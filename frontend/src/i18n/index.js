import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import en from "./locales/en.json";
import hi from "./locales/hi.json";

// UI chrome is translated for English + Hindi today. To add Punjabi or
// Telugu as an APP language later: drop in locales/pa.json + locales/te.json
// (copy en.json's keys), import them below, and add them to `resources`
// and to SUPPORTED_APP_LANGUAGES in LanguageSwitcher.jsx.
// Note: this is separate from the "language of report" field in the form,
// which already lists all four and doesn't need any code changes to grow.
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      hi: { translation: hi },
    },
    fallbackLng: "en",
    supportedLngs: ["en", "hi"],
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
    },
  });

export default i18n;
