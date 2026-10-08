import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, ClipboardList, ShieldCheck, UserPlus, Users } from "lucide-react";
import {
  createUser, getAuditLog, listModelVersions, listUsers, retrainModel, setUserActive,
} from "@/services/admin";
import { createCompany, listCompanies, setCompanyActive } from "@/services/companies";
import { apiErrorMessage } from "@/services/api";
import { useToast } from "@/context/ToastContext";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { TableSkeleton } from "@/components/Skeleton";
import type { Role } from "@/types";

const ALL_TABS = [
  { key: "companies", label: "Entreprises", icon: Building2, adminOnly: true },
  { key: "users", label: "Utilisateurs", icon: Users, adminOnly: false },
  { key: "audit", label: "Journal d'audit", icon: ClipboardList, adminOnly: true },
  { key: "models", label: "Modèles ML", icon: ShieldCheck, adminOnly: true },
] as const;
type TabKey = (typeof ALL_TABS)[number]["key"];

export function AdminPage() {
  const { user } = useAuth();
  const isGlobalAdmin = user?.role === "ADMIN";
  const tabs = ALL_TABS.filter((t) => !t.adminOnly || isGlobalAdmin);
  const [tab, setTab] = useState<TabKey>(isGlobalAdmin ? "companies" : "users");

  return (
    <div className="space-y-4">
      <PageHeader
        title="Administration"
        subtitle={isGlobalAdmin
          ? "Entreprises, utilisateurs, traçabilité et pilotage du modèle ML"
          : "Gestion des comptables de votre entreprise"}
      />

      <div className="flex flex-wrap gap-2">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm transition-colors ${
              tab === key
                ? "bg-brand-600 text-white shadow-sm"
                : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-50"
            }`}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {tab === "companies" && isGlobalAdmin && <CompaniesTab />}
      {tab === "users" && <UsersTab />}
      {tab === "audit" && isGlobalAdmin && <AuditTab />}
      {tab === "models" && isGlobalAdmin && <ModelsTab />}
    </div>
  );
}

function CompaniesTab() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", nif: "", stat: "", address: "" });

  const companiesQuery = useQuery({ queryKey: ["admin", "companies"], queryFn: listCompanies });

  const createMutation = useMutation({
    mutationFn: () => createCompany(form),
    onSuccess: () => {
      notify("success", "Entreprise créée. Crée maintenant son compte administrateur depuis l'onglet Utilisateurs.");
      setForm({ name: "", nif: "", stat: "", address: "" });
      setShowForm(false);
      queryClient.invalidateQueries({ queryKey: ["admin", "companies"] });
    },
    onError: (err) => notify("error", apiErrorMessage(err)),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) =>
      setCompanyActive(id, isActive),
    onSuccess: (_, { isActive }) => {
      notify("success", isActive ? "Entreprise réactivée." : "Entreprise désactivée.");
      queryClient.invalidateQueries({ queryKey: ["admin", "companies"] });
    },
    onError: (err) => notify("error", apiErrorMessage(err)),
  });

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button onClick={() => setShowForm((v) => !v)} className="btn-primary">
          <Building2 size={15} /> Nouvelle entreprise
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => { e.preventDefault(); createMutation.mutate(); }}
          className="card grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 animate-fade-in"
        >
          <input required placeholder="Raison sociale" className="input sm:col-span-2"
                value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="NIF (optionnel)" className="input"
                value={form.nif} onChange={(e) => setForm({ ...form, nif: e.target.value })} />
          <input placeholder="STAT (optionnel)" className="input"
                value={form.stat} onChange={(e) => setForm({ ...form, stat: e.target.value })} />
          <input placeholder="Adresse (optionnel)" className="input sm:col-span-2"
                value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          <div className="sm:col-span-2 flex justify-end gap-2">
            <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">Annuler</button>
            <button type="submit" disabled={createMutation.isPending} className="btn-primary">Créer</button>
          </div>
        </form>
      )}

      <div className="card overflow-hidden">
        {companiesQuery.isLoading ? (
          <TableSkeleton rows={4} cols={4} />
        ) : companiesQuery.data && companiesQuery.data.length === 0 ? (
          <EmptyState icon={Building2} title="Aucune entreprise créée" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-500">
                <tr>
                  <th className="px-5 py-2 font-medium">Raison sociale</th>
                  <th className="px-5 py-2 font-medium">NIF</th>
                  <th className="px-5 py-2 font-medium">STAT</th>
                  <th className="px-5 py-2 font-medium">Statut</th>
                  <th className="px-5 py-2 font-medium text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {companiesQuery.data?.map((c) => (
                  <tr key={c.id} className="border-t border-slate-100">
                    <td className="px-5 py-2.5 font-medium">{c.name}</td>
                    <td className="px-5 py-2.5 text-slate-500">{c.nif ?? "—"}</td>
                    <td className="px-5 py-2.5 text-slate-500">{c.stat ?? "—"}</td>
                    <td className="px-5 py-2.5">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        c.is_active ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-600"
                      }`}>
                        {c.is_active ? "Active" : "Désactivée"}
                      </span>
                    </td>
                    <td className="px-5 py-2.5 text-right">
                      <button
                        disabled={toggleMutation.isPending}
                        onClick={() => toggleMutation.mutate({ id: c.id, isActive: !c.is_active })}
                        className="text-xs font-medium text-brand-700 hover:underline"
                      >
                        {c.is_active ? "Désactiver" : "Réactiver"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

const ROLE_LABELS: Record<Role, string> = {
  ADMIN: "Administrateur plateforme",
  ENTREPRISE_ADMIN: "Admin d'entreprise",
  COMPTABLE: "Comptable",
};

function UsersTab() {
  const { user: currentUser } = useAuth();
  const isGlobalAdmin = currentUser?.role === "ADMIN";
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    email: "", password: "", full_name: "",
    role: (isGlobalAdmin ? "COMPTABLE" : "COMPTABLE") as Role,
    company_id: "" as string | number,
  });

  const usersQuery = useQuery({ queryKey: ["admin", "users"], queryFn: listUsers });
  const companiesQuery = useQuery({
    queryKey: ["admin", "companies"], queryFn: listCompanies, enabled: isGlobalAdmin,
  });

  const createMutation = useMutation({
    mutationFn: () => createUser({
      ...form,
      company_id: isGlobalAdmin
        ? (form.role === "ADMIN" ? null : Number(form.company_id) || null)
        : undefined, // l'API force le rôle et l'entreprise de l'appelant
    }),
    onSuccess: () => {
      notify("success", "Utilisateur créé.");
      setForm({ email: "", password: "", full_name: "", role: "COMPTABLE", company_id: "" });
      setShowForm(false);
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (err) => notify("error", apiErrorMessage(err)),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) => setUserActive(id, isActive),
    onSuccess: (_, { isActive }) => {
      notify("success", isActive ? "Compte réactivé." : "Compte désactivé.");
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (err) => notify("error", apiErrorMessage(err)),
  });

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button onClick={() => setShowForm((v) => !v)} className="btn-primary">
          <UserPlus size={15} /> Nouvel utilisateur
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => { e.preventDefault(); createMutation.mutate(); }}
          className="card grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 animate-fade-in"
        >
          <input required placeholder="Nom complet" className="input"
                value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          <input required type="email" placeholder="Email" className="input"
                value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input required type="password" placeholder="Mot de passe (min. 8 caractères)" className="input"
                minLength={8}
                value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          {isGlobalAdmin ? (
            <select className="input" value={form.role}
                   onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              <option value="COMPTABLE">Comptable</option>
              <option value="ENTREPRISE_ADMIN">Admin d'entreprise</option>
              <option value="ADMIN">Administrateur plateforme</option>
            </select>
          ) : (
            <input disabled className="input bg-slate-50 text-slate-400" value="Comptable" />
          )}
          {isGlobalAdmin && form.role !== "ADMIN" && (
            <select required className="input" value={form.company_id}
                   onChange={(e) => setForm({ ...form, company_id: e.target.value })}>
              <option value="" disabled>Choisir une entreprise…</option>
              {companiesQuery.data?.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          )}
          <div className="sm:col-span-2 flex justify-end gap-2">
            <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">Annuler</button>
            <button type="submit" disabled={createMutation.isPending} className="btn-primary">Créer</button>
          </div>
        </form>
      )}

      <div className="card overflow-hidden">
        {usersQuery.isLoading ? (
          <TableSkeleton rows={4} cols={4} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-500">
                <tr>
                  <th className="px-5 py-2 font-medium">Nom</th>
                  <th className="px-5 py-2 font-medium">Email</th>
                  <th className="px-5 py-2 font-medium">Rôle</th>
                  {isGlobalAdmin && <th className="px-5 py-2 font-medium">Entreprise</th>}
                  <th className="px-5 py-2 font-medium">Statut</th>
                  <th className="px-5 py-2 font-medium text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {usersQuery.data?.map((u) => (
                  <tr key={u.id} className="border-t border-slate-100">
                    <td className="px-5 py-2.5">{u.full_name}</td>
                    <td className="px-5 py-2.5 text-slate-500">{u.email}</td>
                    <td className="px-5 py-2.5">
                      <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">
                        {ROLE_LABELS[u.role]}
                      </span>
                    </td>
                    {isGlobalAdmin && (
                      <td className="px-5 py-2.5 text-slate-500">{u.company_name ?? "—"}</td>
                    )}
                    <td className="px-5 py-2.5">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        u.is_active ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-600"
                      }`}>
                        {u.is_active ? "Actif" : "Désactivé"}
                      </span>
                    </td>
                    <td className="px-5 py-2.5 text-right">
                      <button
                        disabled={u.id === currentUser?.id || toggleMutation.isPending}
                        onClick={() => toggleMutation.mutate({ id: u.id, isActive: !u.is_active })}
                        className="text-xs font-medium text-brand-700 hover:underline disabled:cursor-not-allowed disabled:text-slate-300 disabled:no-underline"
                        title={u.id === currentUser?.id ? "Vous ne pouvez pas modifier votre propre compte" : undefined}
                      >
                        {u.is_active ? "Désactiver" : "Réactiver"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

const ACTION_LABELS: Record<string, string> = {
  INVOICE_UPLOADED: "Facture importée",
  INVOICE_REJECTED: "Facture rejetée",
  ENTRY_CORRECTED: "Écriture corrigée",
  ENTRY_VALIDATED: "Écriture validée",
  USER_CREATED: "Utilisateur créé",
  USER_ACTIVATED: "Utilisateur réactivé",
  USER_DEACTIVATED: "Utilisateur désactivé",
  MODEL_RETRAINED: "Modèle réentraîné",
  COMPANY_CREATED: "Entreprise créée",
  COMPANY_ACTIVATED: "Entreprise réactivée",
  COMPANY_DEACTIVATED: "Entreprise désactivée",
};

function AuditTab() {
  const [page, setPage] = useState(1);
  const size = 30;
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "audit", page], queryFn: () => getAuditLog(page, size),
  });
  const totalPages = data ? Math.max(1, Math.ceil(data.total / size)) : 1;

  return (
    <div className="space-y-3">
      <div className="card overflow-hidden">
        {isLoading ? (
          <TableSkeleton rows={8} cols={4} />
        ) : data && data.items.length === 0 ? (
          <EmptyState icon={ClipboardList} title="Aucune action enregistrée" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-500">
                <tr>
                  <th className="px-5 py-2 font-medium">Date</th>
                  <th className="px-5 py-2 font-medium">Auteur</th>
                  <th className="px-5 py-2 font-medium">Action</th>
                  <th className="px-5 py-2 font-medium">Cible</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((entry) => (
                  <tr key={entry.id} className="border-t border-slate-100">
                    <td className="px-5 py-2.5 whitespace-nowrap text-slate-500">
                      {new Date(entry.created_at).toLocaleString("fr-FR")}
                    </td>
                    <td className="px-5 py-2.5">{entry.user_name ?? "Système (pipeline IA)"}</td>
                    <td className="px-5 py-2.5">
                      <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-medium text-brand-700">
                        {ACTION_LABELS[entry.action] ?? entry.action}
                      </span>
                    </td>
                    <td className="px-5 py-2.5 text-slate-500">{entry.entity_type} #{entry.entity_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {data && data.total > size && (
        <div className="flex items-center justify-between text-sm text-slate-600">
          <span>Page {page} / {totalPages} — {data.total} action(s)</span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="btn-secondary">Précédent</button>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="btn-secondary">Suivant</button>
          </div>
        </div>
      )}
    </div>
  );
}

function ModelsTab() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const versionsQuery = useQuery({ queryKey: ["admin", "models"], queryFn: listModelVersions });

  const retrainMutation = useMutation({
    mutationFn: retrainModel,
    onSuccess: (report) => {
      const compared = report.candidates
        ?.map((c) => `${c.algorithm.replace("tfidf+", "").replace("-calibrated", "")} F1=${Math.round(c.f1_score * 100)}%`)
        .join(" · ");
      if (report.status === "SKIPPED") {
        notify("info", report.reason ?? "Réentraînement ignoré : données insuffisantes.");
      } else if (report.status === "PROMOTED") {
        notify("success", `${report.algorithm?.includes("xgboost") ? "XGBoost" : "Régression logistique"} promu (${compared}).`);
      } else {
        notify("info", `Aucun candidat promu — ${compared} ≤ version active (F1=${Math.round((report.previous_f1 ?? 0) * 100)}%).`);
      }
      queryClient.invalidateQueries({ queryKey: ["admin", "models"] });
    },
    onError: (err) => notify("error", apiErrorMessage(err)),
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">
          Réentraîne le classifieur d'opérations à partir des factures validées et de leurs
          corrections. La nouvelle version n'est activée que si elle égale ou dépasse le F1
          macro de la version active (protection anti-régression).
        </p>
        <button onClick={() => retrainMutation.mutate()} disabled={retrainMutation.isPending} className="btn-primary shrink-0">
          {retrainMutation.isPending ? "Entraînement…" : "Réentraîner"}
        </button>
      </div>

      <div className="card overflow-hidden">
        {versionsQuery.isLoading ? (
          <TableSkeleton rows={3} cols={5} />
        ) : versionsQuery.data && versionsQuery.data.length === 0 ? (
          <EmptyState icon={ShieldCheck} title="Aucune version entraînée"
                     hint="Le classifieur à mots-clés (cold start) est utilisé par défaut." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-500">
                <tr>
                  <th className="px-5 py-2 font-medium">Version</th>
                  <th className="px-5 py-2 font-medium">Algorithme</th>
                  <th className="px-5 py-2 font-medium">Accuracy</th>
                  <th className="px-5 py-2 font-medium">F1 macro</th>
                  <th className="px-5 py-2 font-medium">Exemples</th>
                  <th className="px-5 py-2 font-medium">Statut</th>
                </tr>
              </thead>
              <tbody>
                {versionsQuery.data?.map((v) => (
                  <tr key={`${v.name}-${v.version}`} className="border-t border-slate-100">
                    <td className="px-5 py-2.5 font-mono">{v.version}</td>
                    <td className="px-5 py-2.5 text-slate-600">{v.algorithm}</td>
                    <td className="px-5 py-2.5">{v.accuracy !== null ? `${Math.round(v.accuracy * 100)}%` : "—"}</td>
                    <td className="px-5 py-2.5">{v.f1_score !== null ? `${Math.round(v.f1_score * 100)}%` : "—"}</td>
                    <td className="px-5 py-2.5">{v.training_samples}</td>
                    <td className="px-5 py-2.5">
                      {v.is_active ? (
                        <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800">Active</span>
                      ) : (
                        <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-500">Archivée</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
