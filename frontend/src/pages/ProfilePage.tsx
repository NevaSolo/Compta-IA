import { useRef, useState, type FormEvent } from "react";
import { Building2, Camera, Check, Monitor, Moon, Sun, Trash2, type LucideIcon } from "lucide-react";
import { Avatar } from "@/components/Avatar";
import { ChartPicker } from "@/components/ChartPicker";
import { CurrencySettings } from "@/components/CurrencySettings";
import { PageHeader } from "@/components/PageHeader";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { useProtectedImage } from "@/hooks/useProtectedImage";
import { apiErrorMessage } from "@/services/api";
import {
  changePassword, deleteAvatar, updateProfile, uploadAvatar, type ProfileUpdate,
} from "@/services/auth";
import {
  deleteCompanyLogo, fetchCompanyLogoBlob, renameCompany, uploadCompanyLogo,
} from "@/services/companies";
import { ACCENTS, type ThemeMode } from "@/theme";
import { shrinkImage } from "@/utils/image";

const THEMES: { value: ThemeMode; label: string; icon: LucideIcon }[] = [
  { value: "auto", label: "Automatique", icon: Monitor },
  { value: "light", label: "Clair", icon: Sun },
  { value: "dark", label: "Sombre", icon: Moon },
];

const ROLE_LABELS = {
  ADMIN: "Administrateur plateforme",
  ENTREPRISE_ADMIN: "Admin d'entreprise",
  COMPTABLE: "Comptable",
} as const;

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="card p-4 sm:p-5">
      <h2 className="font-semibold text-slate-800">{title}</h2>
      {hint && <p className="mt-0.5 text-sm text-slate-500">{hint}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function ProfilePage() {
  const { user, setUser } = useAuth();
  const { notify } = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [companyName, setCompanyName] = useState(user?.company_name ?? "");
  const [passwords, setPasswords] = useState({ current: "", next: "", confirm: "" });
  const photoInput = useRef<HTMLInputElement>(null);
  const selfieInput = useRef<HTMLInputElement>(null);
  const logoInput = useRef<HTMLInputElement>(null);

  const companyId = user?.company_id ?? null;
  const canEditCompany = user?.role === "ENTREPRISE_ADMIN" && companyId !== null;
  const logo = useProtectedImage(
    companyId ? `logo-${companyId}` : null, user?.company_logo_version,
    () => fetchCompanyLogoBlob(companyId!));

  if (!user) return null;

  // Enchaîne « occupé → action → message » pour toutes les actions de la page.
  async function run(label: string, action: () => Promise<void>, success: string) {
    setBusy(label);
    try {
      await action();
      notify("success", success);
    } catch (err) {
      notify("error", apiErrorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function savePreference(update: ProfileUpdate) {
    // Appliqué tout de suite (retour visuel immédiat), puis enregistré.
    try {
      setUser(await updateProfile(update));
    } catch (err) {
      notify("error", apiErrorMessage(err));
    }
  }

  function pickAvatar(file: File | undefined) {
    if (!file) return;
    run("avatar", async () => setUser(await uploadAvatar(await shrinkImage(file, 1024, "image/jpeg"))),
      "Photo de profil mise à jour.");
  }
  function pickLogo(file: File | undefined) {
    if (!file || !companyId) return;
    run("logo", async () => {
      await uploadCompanyLogo(companyId, await shrinkImage(file, 1024, "image/png"));
      setUser({ ...user!, company_logo_version: Math.floor(Date.now() / 1000) });
    }, "Logo de l'entreprise mis à jour.");
  }

  function submitPassword(event: FormEvent) {
    event.preventDefault();
    if (passwords.next !== passwords.confirm) {
      notify("error", "La confirmation ne correspond pas au nouveau mot de passe.");
      return;
    }
    run("password", async () => {
      await changePassword(passwords.current, passwords.next);
      setPasswords({ current: "", next: "", confirm: "" });
    }, "Mot de passe modifié.");
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <PageHeader title="Mon profil" subtitle={`${user.email} · ${ROLE_LABELS[user.role]}`} />

      <Section title="Photo de profil">
        <div className="flex flex-col items-center gap-4 sm:flex-row">
          <Avatar user={user} size="xl" />
          <div className="grid w-full gap-2 sm:w-auto sm:grid-cols-2">
            <button type="button" className="btn-primary" disabled={busy !== null}
                    onClick={() => photoInput.current?.click()}>
              <Camera size={16} /> {user.avatar_version ? "Changer la photo" : "Ajouter une photo"}
            </button>
            <button type="button" className="btn-secondary md:hidden" disabled={busy !== null}
                    onClick={() => selfieInput.current?.click()}>
              <Camera size={16} /> Prendre un selfie
            </button>
            {user.avatar_version && (
              <button type="button" className="btn-danger" disabled={busy !== null}
                      onClick={() => run("avatar", async () => setUser(await deleteAvatar()), "Photo supprimée.")}>
                <Trash2 size={16} /> Supprimer
              </button>
            )}
          </div>
          <input ref={photoInput} type="file" accept="image/png,image/jpeg,image/webp" hidden
                 onChange={(e) => { pickAvatar(e.target.files?.[0]); e.target.value = ""; }} />
          <input ref={selfieInput} type="file" accept="image/*" capture="user" hidden
                 onChange={(e) => { pickAvatar(e.target.files?.[0]); e.target.value = ""; }} />
        </div>
      </Section>

      <Section title="Informations">
        <form className="space-y-3" onSubmit={(e) => {
          e.preventDefault();
          run("name", async () => setUser(await updateProfile({ full_name: fullName.trim() })),
            "Nom enregistré.");
        }}>
          <label className="block text-sm text-slate-500">Nom affiché
            <input className="input mt-1" value={fullName} minLength={2} maxLength={150} required
                   onChange={(e) => setFullName(e.target.value)} />
          </label>
          <button type="submit" className="btn-primary w-full sm:w-auto"
                  disabled={busy !== null || fullName.trim() === user.full_name || fullName.trim().length < 2}>
            Enregistrer
          </button>
        </form>
      </Section>

      <Section title="Apparence" hint="Enregistrée sur votre compte : elle vous suit d'un appareil à l'autre.">
        <p className="mb-2 text-sm text-slate-500">Thème</p>
        <div className="grid grid-cols-3 gap-2">
          {THEMES.map(({ value, label, icon: Icon }) => {
            const active = (user.theme ?? "auto") === value;
            return (
              <button key={value} type="button" aria-pressed={active}
                      onClick={() => savePreference({ theme: value })}
                      className={`flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-lg border text-sm transition-colors ${
                        active ? "border-brand-500 bg-brand-50 font-medium text-brand-700"
                               : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}>
                <Icon size={20} /> {label}
              </button>
            );
          })}
        </div>

        <p className="mb-2 mt-5 text-sm text-slate-500">Couleur d'accentuation</p>
        <div className="flex flex-wrap gap-3">
          {ACCENTS.map(({ value, label, swatch }) => {
            const active = (user.accent ?? "blue") === value;
            return (
              <button key={value} type="button" aria-label={label} aria-pressed={active} title={label}
                      onClick={() => savePreference({ accent: value })}
                      style={{ backgroundColor: swatch }}
                      className={`flex h-11 w-11 items-center justify-center rounded-full text-white shadow-sm ring-offset-2 transition ${
                        active ? "ring-2 ring-slate-400" : "hover:scale-105"}`}>
                {active && <Check size={18} />}
              </button>
            );
          })}
        </div>
      </Section>

      {canEditCompany && (
        <Section title="Mon entreprise"
                 hint="Le logo et le nom s'affichent dans l'en-tête, pour tous les utilisateurs de votre entreprise.">
          <div className="flex items-center gap-4">
            <span className="flex h-20 w-32 shrink-0 items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 p-2">
              {logo ? <img src={logo} alt="Logo" className="max-h-full max-w-full object-contain" />
                    : <Building2 size={28} className="text-slate-300" />}
            </span>
            <div className="grid w-full gap-2 sm:w-auto sm:grid-cols-2">
              <button type="button" className="btn-secondary" disabled={busy !== null}
                      onClick={() => logoInput.current?.click()}>
                {logo ? "Changer le logo" : "Ajouter un logo"}
              </button>
              {logo && (
                <button type="button" className="btn-danger" disabled={busy !== null}
                        onClick={() => run("logo", async () => {
                          await deleteCompanyLogo(companyId!);
                          setUser({ ...user, company_logo_version: null });
                        }, "Logo supprimé.")}>
                  <Trash2 size={16} /> Retirer
                </button>
              )}
            </div>
            <input ref={logoInput} type="file" accept="image/png,image/jpeg,image/webp" hidden
                   onChange={(e) => { pickLogo(e.target.files?.[0]); e.target.value = ""; }} />
          </div>

          <form className="mt-4 space-y-3" onSubmit={(e) => {
            e.preventDefault();
            run("company", async () => {
              const updated = await renameCompany(companyId!, companyName.trim());
              setUser({ ...user, company_name: updated.name });
            }, "Nom de l'entreprise enregistré.");
          }}>
            <label className="block text-sm text-slate-500">Nom de l'entreprise
              <input className="input mt-1" value={companyName} minLength={2} maxLength={255} required
                     onChange={(e) => setCompanyName(e.target.value)} />
            </label>
            <button type="submit" className="btn-primary w-full sm:w-auto"
                    disabled={busy !== null || companyName.trim() === (user.company_name ?? "")
                              || companyName.trim().length < 2}>
              Enregistrer le nom
            </button>
          </form>
        </Section>
      )}

      {canEditCompany && (
        <Section title="Plan comptable"
                 hint={user.company_chart_name ? `Plan actuel : ${user.company_chart_name}. Modifiable tant qu'aucune écriture n'existe.` : "Aucun plan choisi."}>
          <ChartPicker />
        </Section>
      )}

      {canEditCompany && (
        <Section title="Devise et taux de change"
                 hint="Votre comptabilité est tenue dans une seule devise ; les factures en devise étrangère y sont converties au taux que vous définissez.">
          <CurrencySettings companyId={companyId!} />
        </Section>
      )}

      <Section title="Mot de passe">
        <form className="space-y-3" onSubmit={submitPassword}>
          <input className="input" type="password" autoComplete="current-password" required
                 placeholder="Mot de passe actuel" value={passwords.current}
                 onChange={(e) => setPasswords({ ...passwords, current: e.target.value })} />
          <input className="input" type="password" autoComplete="new-password" required minLength={8}
                 placeholder="Nouveau mot de passe (8 caractères minimum)" value={passwords.next}
                 onChange={(e) => setPasswords({ ...passwords, next: e.target.value })} />
          <input className="input" type="password" autoComplete="new-password" required minLength={8}
                 placeholder="Confirmer le nouveau mot de passe" value={passwords.confirm}
                 onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })} />
          <button type="submit" className="btn-primary w-full sm:w-auto" disabled={busy !== null}>
            Changer le mot de passe
          </button>
        </form>
      </Section>
    </div>
  );
}
