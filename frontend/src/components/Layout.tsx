import { Link, NavLink, Outlet } from "react-router-dom";
import {
  FileText, History, LayoutDashboard, LogOut, Settings, UploadCloud, Wallet, type LucideIcon,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { Avatar, CompanyBrand } from "@/components/Avatar";
import { ChartSetup } from "@/components/ChartSetup";

interface NavItem { to: string; label: string; short: string; icon: LucideIcon }

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Tableau de bord", short: "Accueil", icon: LayoutDashboard },
  { to: "/upload", label: "Importer", short: "Importer", icon: UploadCloud },
  { to: "/historique", label: "Historique", short: "Factures", icon: History },
  { to: "/ecritures", label: "Écritures", short: "Écritures", icon: FileText },
];

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return `rounded-md px-3 py-2 text-sm font-medium transition-colors ${
    isActive ? "bg-brand-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"
  }`;
}

function tabClass({ isActive }: { isActive: boolean }): string {
  return `flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition-colors active:bg-slate-100 ${
    isActive ? "text-brand-700" : "text-slate-500"
  }`;
}

export function Layout() {
  const { user, logout } = useAuth();
  // Une entreprise sans plan comptable ne peut rien traiter : écran de choix à la place des pages.
  const needsChart = user?.company_id != null && user.company_chart_id == null;
  const navItems: NavItem[] = (user?.role === "ADMIN" || user?.role === "ENTREPRISE_ADMIN")
    ? [...NAV_ITEMS, { to: "/admin", label: "Administration", short: "Admin", icon: Settings }]
    : NAV_ITEMS;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="safe-top sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-2.5 md:py-3">
          <div className="flex min-w-0 items-center gap-3 md:gap-6">
            <Link to="/" tabIndex={needsChart ? -1 : undefined} aria-disabled={needsChart}
                  className={`flex shrink-0 items-center gap-2 text-lg font-bold text-brand-700 ${needsChart ? "pointer-events-none" : ""}`}>
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
                <Wallet size={18} />
              </span>
              <span className="hidden min-[360px]:inline">Compta-IA</span>
            </Link>
            <CompanyBrand compact />
            <nav className="hidden gap-1 md:flex">
              {navItems.map((item) => needsChart ? (
                <span key={item.to} aria-disabled="true" title="Choisissez d'abord votre plan comptable"
                      className="cursor-not-allowed rounded-md px-3 py-2 text-sm font-medium text-slate-400 opacity-60">
                  {item.label}
                </span>
              ) : (
                <NavLink key={item.to} to={item.to} end={item.to === "/"} className={navLinkClass}>
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>

          <div className="hidden items-center gap-3 text-sm md:flex">
            <Link to="/profil" title="Mon profil" tabIndex={needsChart ? -1 : undefined} aria-disabled={needsChart}
                  className={`flex items-center gap-2 rounded-md p-1 hover:bg-slate-100 ${needsChart ? "pointer-events-none opacity-60" : ""}`}>
              <Avatar user={user} size="sm" />
              <span className="text-slate-600">
                {user?.full_name} <span className="text-slate-400">· {user?.role}</span>
              </span>
            </Link>
            <button onClick={logout} className="btn-secondary">
              <LogOut size={15} /> Déconnexion
            </button>
          </div>

          {/* Mobile : avatar + déconnexion ; la navigation est dans la barre du bas. */}
          <div className="flex items-center gap-2 md:hidden">
            <Link to="/profil" aria-label="Mon profil" tabIndex={needsChart ? -1 : undefined} aria-disabled={needsChart}
                  className={`rounded-full ${needsChart ? "pointer-events-none opacity-60" : ""}`}>
              <Avatar user={user} />
            </Link>
            <button
              onClick={logout} aria-label="Déconnexion"
              className="flex h-11 w-11 items-center justify-center rounded-full text-slate-500 active:bg-slate-100"
            >
              <LogOut size={20} />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-4 pb-24 animate-fade-in md:py-6 md:pb-6">
        {needsChart ? <ChartSetup /> : <Outlet />}
      </main>

      <nav
        aria-label="Navigation principale"
        className="safe-bottom fixed inset-x-0 bottom-0 z-40 flex border-t border-slate-200 bg-white/95 backdrop-blur md:hidden"
      >
        {navItems.map(({ to, short, icon: Icon }) => needsChart ? (
          <span key={to} aria-disabled="true"
                className="flex min-h-[56px] flex-1 cursor-not-allowed flex-col items-center justify-center gap-0.5 text-[11px] font-medium text-slate-400 opacity-50">
            <Icon size={22} strokeWidth={1.75} />
            {short}
          </span>
        ) : (
          <NavLink key={to} to={to} end={to === "/"} className={tabClass}>
            <Icon size={22} strokeWidth={1.75} />
            {short}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
