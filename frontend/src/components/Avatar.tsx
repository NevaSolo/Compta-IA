import { useAuth } from "@/context/AuthContext";
import { fetchAvatarBlob } from "@/services/auth";
import { fetchCompanyLogoBlob } from "@/services/companies";
import { useProtectedImage } from "@/hooks/useProtectedImage";
import type { User } from "@/types";

export function initials(name: string | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return (parts[0]?.[0] ?? "").concat(parts[1]?.[0] ?? "").toUpperCase() || "?";
}

const SIZES = { sm: "h-8 w-8 text-xs", md: "h-9 w-9 text-xs", xl: "h-24 w-24 text-2xl" };

/** Photo de profil, ou initiales tant qu'il n'y en a pas. */
export function Avatar({ user, size = "md" }: { user: User | null; size?: keyof typeof SIZES }) {
  const url = useProtectedImage(user ? `avatar-${user.id}` : null, user?.avatar_version, fetchAvatarBlob);
  const box = `flex shrink-0 items-center justify-center overflow-hidden rounded-full ${SIZES[size]}`;
  return url
    ? <img src={url} alt="" className={`${box} object-cover`} />
    : <span className={`${box} bg-brand-100 font-bold text-brand-700`}>{initials(user?.full_name)}</span>;
}

/** Logo et nom de l'entreprise, visibles par tous ses membres. */
export function CompanyBrand({ compact = false }: { compact?: boolean }) {
  const { user } = useAuth();
  const companyId = user?.company_id ?? null;
  const logo = useProtectedImage(
    companyId ? `logo-${companyId}` : null, user?.company_logo_version,
    () => fetchCompanyLogoBlob(companyId!));
  if (!companyId || (!logo && !user?.company_name)) return null;
  return (
    <span className="flex min-w-0 items-center gap-2 border-l border-slate-200 pl-3">
      {logo && <img src={logo} alt="" className="h-8 max-w-[7rem] object-contain" />}
      {user?.company_name && (
        <span className={`truncate text-sm font-semibold text-slate-700 ${compact ? "hidden min-[420px]:inline max-w-[8rem]" : "max-w-[14rem]"}`}>
          {user.company_name}
        </span>
      )}
    </span>
  );
}
