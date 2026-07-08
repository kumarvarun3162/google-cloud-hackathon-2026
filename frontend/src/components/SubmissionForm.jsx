import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Mic, Type, Camera, Upload, Loader2, AlertCircle } from "lucide-react";
import constituencies from "../mocks/constituencies.json";
import { submitReport } from "../lib/api";

const SUBMISSION_TYPES = [
  { id: "text", icon: Type, labelKey: "submit.type_text" },
  { id: "voice", icon: Mic, labelKey: "submit.type_voice" },
  { id: "photo", icon: Camera, labelKey: "submit.type_photo" },
];

// Language the citizen is submitting IN — independent of the app's own
// UI language (see LanguageSwitcher.jsx). More languages can be appended
// here without touching any other file.
const REPORT_LANGUAGES = [
  { code: "hi", label: "हिंदी (Hindi)" },
  { code: "en", label: "English" },
  { code: "pa", label: "ਪੰਜਾਬੀ (Punjabi)" },
  { code: "te", label: "తెలుగు (Telugu)" },
];

const initialState = {
  name: "",
  constituency: "",
  type: "text",
  language: "hi",
  text: "",
  caption: "",
};

export default function SubmissionForm({ onSuccess }) {
  const { t } = useTranslation();
  const [fields, setFields] = useState(initialState);
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | submitting | error
  const [errors, setErrors] = useState({});

  function updateField(key, value) {
    setFields((prev) => ({ ...prev, [key]: value }));
  }

  function selectType(type) {
    setFields((prev) => ({ ...prev, type }));
    setFile(null);
    setErrors({});
  }

  function validate() {
    const nextErrors = {};
    if (!fields.constituency) nextErrors.constituency = t("submit.error_constituency");
    if (fields.type === "text" && !fields.text.trim()) {
      nextErrors.text = t("submit.error_text");
    }
    if ((fields.type === "voice" || fields.type === "photo") && !file) {
      nextErrors.file = t("submit.error_file");
    }
    return nextErrors;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const validationErrors = validate();
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;

    setStatus("submitting");
    try {
      const formData = new FormData();
      formData.append("name", fields.name);
      formData.append("constituency", fields.constituency);
      formData.append("type", fields.type);
      formData.append("language", fields.language);
      if (fields.type === "text") {
        formData.append("text", fields.text);
      } else {
        formData.append("file", file);
        if (fields.type === "photo") formData.append("caption", fields.caption);
      }

      const result = await submitReport(formData);
      onSuccess(result.ticket);
    } catch {
      setStatus("error");
      setErrors({ generic: t("submit.error_generic") });
      return;
    }
    setStatus("idle");
  }

  const inputClasses =
    "w-full rounded-xl border border-primary/15 bg-white px-4 py-3 text-base text-ink placeholder:text-muted/70 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";
  const labelClasses = "mb-1.5 block text-sm font-medium text-ink";
  const errorClasses = "mt-1 text-sm text-red-600";

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-6">
      {/* Name (optional) */}
      <div>
        <label htmlFor="name" className={labelClasses}>
          {t("submit.name_label")}
        </label>
        <input
          id="name"
          type="text"
          value={fields.name}
          onChange={(e) => updateField("name", e.target.value)}
          placeholder={t("submit.name_placeholder")}
          className={inputClasses}
        />
        <p className="mt-1 text-xs text-muted">{t("submit.name_hint")}</p>
      </div>

      {/* Constituency */}
      <div>
        <label htmlFor="constituency" className={labelClasses}>
          {t("submit.constituency_label")}
        </label>
        <select
          id="constituency"
          value={fields.constituency}
          onChange={(e) => updateField("constituency", e.target.value)}
          className={inputClasses}
        >
          <option value="">{t("submit.constituency_placeholder")}</option>
          {constituencies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        {errors.constituency && <p className={errorClasses}>{errors.constituency}</p>}
      </div>

      {/* Submission type — segmented control */}
      <div>
        <span className={labelClasses}>{t("submit.type_label")}</span>
        <div className="grid grid-cols-3 gap-2">
          {SUBMISSION_TYPES.map(({ id, icon: Icon, labelKey }) => {
            const active = fields.type === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => selectType(id)}
                aria-pressed={active}
                className={`flex flex-col items-center gap-1.5 rounded-xl border px-3 py-3 text-sm font-medium transition-colors ${
                  active
                    ? "border-primary bg-primary-light text-primary"
                    : "border-primary/15 bg-white text-muted hover:border-primary/40"
                }`}
              >
                <Icon className="h-5 w-5" strokeWidth={1.75} />
                {t(labelKey)}
              </button>
            );
          })}
        </div>
      </div>

      {/* Report language */}
      <div>
        <label htmlFor="language" className={labelClasses}>
          {t("submit.language_label")}
        </label>
        <select
          id="language"
          value={fields.language}
          onChange={(e) => updateField("language", e.target.value)}
          className={inputClasses}
        >
          {REPORT_LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
      </div>

      {/* Conditional content by type */}
      {fields.type === "text" && (
        <div>
          <label htmlFor="text" className={labelClasses}>
            {t("submit.text_label")}
          </label>
          <textarea
            id="text"
            rows={5}
            value={fields.text}
            onChange={(e) => updateField("text", e.target.value)}
            placeholder={t("submit.text_placeholder")}
            className={inputClasses}
          />
          {errors.text && <p className={errorClasses}>{errors.text}</p>}
        </div>
      )}

      {fields.type === "voice" && (
        <FileField
          label={t("submit.voice_label")}
          hint={t("submit.voice_hint")}
          accept="audio/*"
          file={file}
          onFile={setFile}
          error={errors.file}
          chooseLabel={t("submit.file_choose")}
          noneLabel={t("submit.file_none")}
        />
      )}

      {fields.type === "photo" && (
        <>
          <FileField
            label={t("submit.photo_label")}
            hint={t("submit.photo_hint")}
            accept="image/*"
            file={file}
            onFile={setFile}
            error={errors.file}
            chooseLabel={t("submit.file_choose")}
            noneLabel={t("submit.file_none")}
          />
          <input
            type="text"
            value={fields.caption}
            onChange={(e) => updateField("caption", e.target.value)}
            placeholder={t("submit.photo_caption_placeholder")}
            className={inputClasses}
          />
        </>
      )}

      {errors.generic && (
        <div className="flex items-center gap-2 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {errors.generic}
        </div>
      )}

      <button
        type="submit"
        disabled={status === "submitting"}
        className="flex items-center justify-center gap-2 rounded-xl bg-accent px-6 py-3.5 text-base font-semibold text-white shadow-sm transition-colors hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-70"
      >
        {status === "submitting" && <Loader2 className="h-4 w-4 animate-spin" />}
        {status === "submitting" ? t("submit.submitting") : t("submit.submit_button")}
      </button>
    </form>
  );
}

function FileField({ label, hint, accept, file, onFile, error, chooseLabel, noneLabel }) {
  return (
    <div>
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-dashed border-primary/30 bg-white px-4 py-4 text-sm text-muted hover:border-primary/50">
        <Upload className="h-5 w-5 shrink-0 text-primary" strokeWidth={1.75} />
        <span className="flex-1 truncate">{file ? file.name : noneLabel}</span>
        <span className="shrink-0 rounded-lg bg-primary-light px-3 py-1.5 text-xs font-semibold text-primary">
          {chooseLabel}
        </span>
        <input
          type="file"
          accept={accept}
          className="sr-only"
          onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        />
      </label>
      <p className="mt-1 text-xs text-muted">{hint}</p>
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
    </div>
  );
}
