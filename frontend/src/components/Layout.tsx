import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { LogOut, Menu, Wallet, X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const NAV_ITEMS = [
  { to: "/", label: "Tableau de bord" },
  { to: "/upload", label: "Importer" },
  { to: "/historique", label: "Historique" },
  { to: "/ecritures", label: "Écritures" },
];

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return `rounded-md px-3 py-2 text-sm font-medium transition-colors ${
    isActive ? "bg-brand-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"
  }`;
}

function mobileNavLinkClass({ isActive }: { isActive: boolean }): string {
  return `block rounded-md px-3 py-2 text-sm font-medium ${
    isActive ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"
  }`;
}

function initials(name: string | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return (parts[0]?.[0] ?? "").concat(parts[1]?.[0] ?? "").toUpperCase() || "?";
}

export function Layout() {
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const navItems = (user?.role === "ADMIN" || user?.role === "ENTREPRISE_ADMIN")
    ? [...NAV_ITEMS, { to: "/admin", label: "Administration" }]
    : NAV_ITEMS;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-6">
            <span className="flex items-center gap-2 text-lg font-bold text-brand-700">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
                <Wallet size={18} />
              </span>
              Compta-IA
            </span>
            <nav className="hidden gap-1 md:flex">
              {navItems.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.to === "/"} className={navLinkClass}>
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>

          <div className="hidden items-center gap-3 text-sm md:flex">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700">
                {initials(user?.full_name)}
              </span>
              <span className="text-slate-600">
                {user?.full_name} <span className="text-slate-400">· {user?.role}</span>
              </span>
            </div>
            <button onClick={logout} className="btn-secondary">
              <LogOut size={15} /> Déconnexion
            </button>
          </div>

          <button
            onClick={() => setMobileOpen((v) => !v)}
            className="flex h-9 w-9 items-center justify-center rounded-md border border-slate-300 text-slate-600 md:hidden"
            aria-label="Ouvrir le menu"
          >
            {mobileOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>

        {mobileOpen && (
          <nav className="border-t border-slate-100 px-4 py-3 md:hidden animate-fade-in">
            <div className="mb-3 flex items-center gap-2 text-sm text-slate-600">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700">
                {initials(user?.full_name)}
              </span>
              {user?.full_name} <span className="text-slate-400">· {user?.role}</span>
            </div>
            <div className="flex flex-col gap-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.to} to={item.to} end={item.to === "/"}
                  className={mobileNavLinkClass} onClick={() => setMobileOpen(false)}
                >
                  {item.label}
                </NavLink>
              ))}
              <button onClick={logout} className="btn-secondary mt-2 justify-start">
                <LogOut size={15} /> Déconnexion
              </button>
            </div>
          </nav>
        )}
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 animate-fade-in">
        <Outlet />
      </main>
    </div>
  );
}
