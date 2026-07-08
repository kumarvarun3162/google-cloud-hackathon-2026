import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useLocation } from "react-router-dom";
import { Loader2, AlertCircle } from "lucide-react";
import { useAuth } from "../lib/auth.jsx";

export default function LoginPage() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    setStatus("submitting");
    setError(null);
    try {
      await login(email, password);
      navigate(location.state?.from?.pathname ?? "/map", { replace: true });
    } catch {
      setError(t("auth.error"));
      setStatus("idle");
    }
  }

  const inputClasses =
    "w-full rounded-xl border border-primary/15 bg-white px-4 py-3 text-base text-ink placeholder:text-muted/70 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink px-5">
      <div className="w-full max-w-sm rounded-2xl bg-white p-7 shadow-xl">
        <span className="font-display text-lg font-semibold text-primary">
          {t("app.name")}
        </span>
        <h1 className="mt-3 font-display text-xl font-semibold text-ink">
          {t("auth.title")}
        </h1>
        <p className="mt-1 text-sm text-muted">{t("auth.subtitle")}</p>

        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <div>
            <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-ink">
              {t("auth.email_label")}
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClasses}
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-ink">
              {t("auth.password_label")}
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClasses}
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={status === "submitting"}
            className="flex items-center justify-center gap-2 rounded-xl bg-primary px-6 py-3 text-base font-semibold text-white shadow-sm transition-colors hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-70"
          >
            {status === "submitting" && <Loader2 className="h-4 w-4 animate-spin" />}
            {status === "submitting" ? t("auth.signing_in") : t("auth.sign_in")}
          </button>
        </form>

        <p className="mt-5 text-center text-xs text-muted">{t("auth.demo_hint")}</p>
      </div>
    </div>
  );
}
