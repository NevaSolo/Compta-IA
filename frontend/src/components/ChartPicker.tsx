import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpen, Check, Search } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { apiErrorMessage } from "@/services/api";
import { chooseChart, listCharts } from "@/services/charts";
import { Skeleton } from "@/components/Skeleton";
import type { Chart } from "@/types";

const COUNTRY_NAMES: Record<string, string> = { MG: "Madagascar", FR: "France" };

/** Sélecteur de plan comptable. Sert à la première configuration (choix
 * obligatoire) et au changement depuis « Mon profil » tant qu'aucune écriture
 * n'existe (le serveur refuse sinon). */
export function ChartPicker({ onChosen }: { onChosen?: () => void }) {
  const { user, setUser } = useAuth();
  const { notify } = useToast();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Chart | null>(null);
  const charts = useQuery({ queryKey: ["charts"], queryFn: listCharts });
  const current = user?.company_chart_id ?? null;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (charts.data ?? []).filter((c) =>
      !q || [c.name, c.code, c.country ? COUNTRY_NAMES[c.country] ?? c.country : ""]
        .some((text) => text.toLowerCase().includes(q)));
  }, [charts.data, query]);

  const choose = useMutation({
    mutationFn: (chart: Chart) => chooseChart(user!.company_id!, chart.id),
    onSuccess: (_, chart) => {
      setUser({ ...user!, company_chart_id: chart.id, company_chart_name: chart.name });
      setSelected(null);
      notify("success", `Plan comptable : ${chart.name}.`);
      onChosen?.();
    },
    onError: (err) => { setSelected(null); notify("error", apiErrorMessage(err)); },
  });

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input type="search" className="input pl-9" value={query} onChange={(e) => setQuery(e.target.value)}
               placeholder="Rechercher un pays ou un plan…" aria-label="Rechercher un plan comptable" />
      </div>

      {charts.isLoading && <Skeleton className="h-24 w-full" />}
      {filtered.map((chart) => {
        const active = chart.id === current;
        return (
          <button key={chart.id} type="button" onClick={() => !active && setSelected(chart)}
                  aria-pressed={active}
                  className={`flex w-full items-start gap-3 rounded-xl border p-4 text-left transition-colors ${
                    active ? "border-brand-500 bg-brand-50" : "border-slate-200 bg-white hover:border-brand-300"}`}>
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-sm font-bold text-brand-700">
              {chart.country ?? <BookOpen size={18} />}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-800">{chart.name}</span>
                {chart.version && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{chart.version}</span>}
                {active && <span className="inline-flex items-center gap-1 text-xs font-medium text-brand-700"><Check size={14} /> Plan actuel</span>}
              </span>
              <span className="mt-0.5 block text-sm text-slate-500">
                {chart.country ? COUNTRY_NAMES[chart.country] ?? chart.country : "International"} · {chart.accounts_count} comptes
              </span>
              {chart.description && <span className="mt-1 block text-xs text-slate-400">{chart.description}</span>}
            </span>
          </button>
        );
      })}
      {charts.data && filtered.length === 0 && (
        <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-500">
          Aucun plan ne correspond à « {query} ». Votre plan n'est pas dans la liste ? L'import d'un plan
          personnalisé sera bientôt disponible.
        </p>
      )}

      <ConfirmDialog
        open={selected !== null} tone="success" loading={choose.isPending}
        title={`Choisir « ${selected?.name} » ?`} confirmLabel="Choisir ce plan"
        onCancel={() => setSelected(null)} onConfirm={() => selected && choose.mutate(selected)}
      >
        Les écritures de votre entreprise seront générées avec les comptes de ce plan. Le plan ne pourra
        plus être changé dès qu'une écriture existe.
      </ConfirmDialog>
    </div>
  );
}
