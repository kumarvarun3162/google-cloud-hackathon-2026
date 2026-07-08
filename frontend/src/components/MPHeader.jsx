import { useTranslation } from "react-i18next";
import { NavLink, useNavigate } from "react-router-dom";
import { Map, ListOrdered, LogOut } from "lucide-react";
import LanguageSwitcher from "./LanguageSwitcher";
import { useAuth } from "../lib/auth.jsx";

export default function MPHeader() {
  const { t } = useTranslation();
  const { logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  const linkClasses = ({ isActive }) =>
    `flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      isActive ? "bg-white/15 text-white" : "text-white/70 hover:text-white"
    }`;

  return (
    <header className="flex items-center justify-between bg-ink px-4 py-3 sm:px-6">
      <div className="flex items-center gap-6">
        <span className="font-display text-base font-semibold text-white">
          {t("app.name")}
        </span>
        <nav className="hidden items-center gap-1 sm:flex">
          <NavLink to="/map" className={linkClasses}>
            <Map className="h-4 w-4" strokeWidth={1.75} />
            {t("nav.map")}
          </NavLink>
          <NavLink to="/priorities" className={linkClasses}>
            <ListOrdered className="h-4 w-4" strokeWidth={1.75} />
            {t("nav.priorities")}
          </NavLink>
        </nav>
      </div>

      <div className="flex items-center gap-3">
        <LanguageSwitcher />
        <button
          type="button"
          onClick={handleLogout}
          className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-white/70 hover:text-white"
        >
          <LogOut className="h-4 w-4" strokeWidth={1.75} />
          <span className="hidden sm:inline">{t("nav.logout")}</span>
        </button>
      </div>
    </header>
  );
}
