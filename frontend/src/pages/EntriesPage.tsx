import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listEntries, validateEntriesBatch } from "@/services/entries";
import { CheckCheck, Receipt } from "lucide-react";
import { apiErrorMessage } from "@/services/api";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useToast } from "@/context/ToastContext";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { ExportButtons } from "@/components/ExportButtons";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";
import type { EntryStatus, JournalEntry } from "@/types";

const RELIABLE_CONFIDENCE = 0.8; // seuil « vert » du badge de confiance

const isValidatable = (e: JournalEntry) => e.status !== "VALIDATED";
const isReliable = (e: JournalEntry) =>
  isValidatable(e) && (e.confidence_score ?? 0) >= RELIABLE_CONFIDENCE
  && Math.abs(Number(e.total_debit) - Number(e.total_credit)) < 0.005;

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "Tous les statuts" },
  { value: "PROPOSED", label: "Proposées" },
  { value: "CORRECTED", label: "Corrigées" },
  { value: "VALIDATED", label: "Validées" },
];

function EntryStatusBadge({ status }: { status: EntryStatus }) {
  const style: Record<EntryStatus, string> = {
    PROPOSED: "bg-amber-100 text-amber-800",
    CORRECTED: "bg-blue-100 text-blue-800",
    VALIDATED: "bg-emerald-100 text-emerald-800",
  };
  const label: Record<EntryStatus, string> = {
    PROPOSED: "Proposée", CORRECTED: "Corrigée", VALIDATED: "Validée",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${style[status]}`}>
      {label[status]}
    </span>
  );
}

export function EntriesPage() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const size = 20;
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirming, setConfirming] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["entries", status, page],
    queryFn: () => listEntries(status || undefined, page, size),
  });

  const batchMutation = useMutation({
    mutationFn: (ids: number[]) => validateEntriesBatch(ids),
    onSuccess: (result) => {
      if (result.failed === 0) {
        notify("success", `${result.validated} écriture(s) validée(s).`);
      } else {
        const first = result.results.find((r) => !r.ok);
        notify("error", `${result.validated} validée(s), ${result.failed} refusée(s) : ${first?.error ?? "erreur"}`);
      }
      setSelected(new Set());
      setConfirming(false);
      for (const key of ["entries", "invoices", "dashboard"]) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
    onError: (err) => { setConfirming(false); notify("error", apiErrorMessage(err)); },
  });

  const items = data?.items ?? [];
  const reliableIds = items.filter(isReliable).map((e) => e.id);
  const allReliableSelected = reliableIds.length > 0 && reliableIds.every((id) => selected.has(id));

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  function toggleReliable() {
    setSelected(allReliableSelected ? new Set() : new Set(reliableIds));
  }
  function changeFilter(value: string) {
    setStatus(value); setPage(1); setSelected(new Set());
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / size)) : 1;

  return (
    <div className="space-y-4">
      <PageHeader title="Écritures comptables" actions={<ExportButtons />} />

      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] md:mx-0 md:flex-wrap md:px-0">
        {STATUS_FILTERS.map((filter) => (
          <button
            key={filter.value}
            onClick={() => changeFilter(filter.value)}
            className={`chip ${
              status === filter.value
                ? "bg-brand-600 text-white shadow-sm"
                : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-50"
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {reliableIds.length > 0 && (
        <button type="button" onClick={toggleReliable} className="btn-secondary w-full sm:w-auto">
          <CheckCheck size={16} />
          {allReliableSelected
            ? "Désélectionner les écritures fiables"
            : `Sélectionner les ${reliableIds.length} écriture(s) fiable(s) (≥ 80 %, équilibrées)`}
        </button>
      )}

      <div className="space-y-3">
        {isLoading && Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="card space-y-2 p-5">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-24 w-full" />
          </div>
        ))}

        {data?.items.map((entry) => (
          <div key={entry.id} className="card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-4 py-3 md:px-5">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                {isValidatable(entry) && (
                  <input
                    type="checkbox" checked={selected.has(entry.id)} onChange={() => toggle(entry.id)}
                    aria-label={`Sélectionner l'écriture ${entry.label}`}
                    className="h-5 w-5 rounded border-slate-300 text-brand-600"
                  />
                )}
                <Link to={`/factures/${entry.invoice_id}`} className="font-medium text-brand-700 hover:underline">
                  {entry.label}
                </Link>
                <EntryStatusBadge status={entry.status} />
                {entry.rule_code && (
                  <span className="text-xs text-slate-400">{entry.rule_code}</span>
                )}
              </div>
              <div className="flex items-center gap-3 text-sm text-slate-500">
                <span>{entry.entry_date}</span>
                <ConfidenceBadge score={entry.confidence_score} />
              </div>
            </div>

            <ul className="divide-y divide-slate-100 md:hidden">
              {entry.lines.map((line) => {
                const isDebit = Number(line.debit) > 0;
                return (
                  <li key={line.id ?? `${entry.id}-${line.account_code}`} className="flex items-start gap-3 px-4 py-2.5">
                    <span className="mt-0.5 w-14 shrink-0 font-mono text-sm text-slate-700">{line.account_code}</span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-slate-600">{line.label}</p>
                      <p className="mt-0.5 text-xs text-slate-400">{isDebit ? "Débit" : "Crédit"}</p>
                    </div>
                    <span className="shrink-0 text-sm font-medium tabular-nums text-slate-800">
                      {isDebit ? line.debit : line.credit}
                    </span>
                  </li>
                );
              })}
              <li className="flex justify-between bg-slate-50 px-4 py-2.5 text-sm font-medium text-slate-700">
                <span>Total</span>
                <span className="tabular-nums">{entry.total_debit} / {entry.total_credit}</span>
              </li>
            </ul>

            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead className="text-left text-slate-400">
                  <tr>
                    <th className="px-5 py-2 font-medium">Compte</th>
                    <th className="px-5 py-2 font-medium">Libellé</th>
                    <th className="px-5 py-2 font-medium text-right">Débit</th>
                    <th className="px-5 py-2 font-medium text-right">Crédit</th>
                    <th className="px-5 py-2 font-medium">Compte suggéré par l'IA</th>
                  </tr>
                </thead>
                <tbody>
                  {entry.lines.map((line) => (
                    <tr key={line.id ?? `${entry.id}-${line.account_code}`} className="border-t border-slate-100">
                      <td className="px-5 py-2 font-mono text-slate-700">{line.account_code}</td>
                      <td className="px-5 py-2 text-slate-600">{line.label}</td>
                      <td className="px-5 py-2 text-right tabular-nums">
                        {Number(line.debit) > 0 ? line.debit : ""}
                      </td>
                      <td className="px-5 py-2 text-right tabular-nums">
                        {Number(line.credit) > 0 ? line.credit : ""}
                      </td>
                      <td className="px-5 py-2">
                        {line.suggested_by_ml ? <ConfidenceBadge score={line.account_confidence} /> : (
                          <span className="text-xs text-slate-400">règle</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-slate-200 font-medium text-slate-700">
                    <td className="px-5 py-2" colSpan={2}>Total</td>
                    <td className="px-5 py-2 text-right tabular-nums">{entry.total_debit}</td>
                    <td className="px-5 py-2 text-right tabular-nums">{entry.total_credit}</td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        ))}

        {data && data.items.length === 0 && (
          <div className="card"><EmptyState icon={Receipt} title="Aucune écriture" hint="Essayez un autre filtre de statut." /></div>
        )}
      </div>

      {selected.size > 0 && (
        <div className="fixed inset-x-4 bottom-20 z-40 flex items-center justify-between gap-3 rounded-xl bg-slate-900 px-4 py-3 text-white shadow-lg animate-slide-up md:inset-x-auto md:bottom-6 md:left-1/2 md:min-w-[24rem] md:-translate-x-1/2">
          <span className="text-sm">{selected.size} sélectionnée(s)</span>
          <div className="flex gap-2">
            <button type="button" onClick={() => setSelected(new Set())}
                    className="btn rounded-md px-3 text-slate-200 hover:bg-slate-800">Annuler</button>
            <button type="button" onClick={() => setConfirming(true)} disabled={batchMutation.isPending}
                    className="btn-success">
              {batchMutation.isPending ? "Validation…" : "Valider"}
            </button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirming} tone="success" loading={batchMutation.isPending}
        title={`Valider ${selected.size} écriture(s) ?`}
        confirmLabel="Valider définitivement"
        onCancel={() => setConfirming(false)}
        onConfirm={() => batchMutation.mutate([...selected])}
      >
        Une écriture validée ne peut plus être modifiée. Chaque écriture est contrôlée
        (équilibre débit = crédit) ; celles qui échouent restent à vérifier.
      </ConfirmDialog>

      {data && data.total > size && (
        <div className="flex items-center justify-between text-sm text-slate-600">
          <span>Page {page} / {totalPages} — {data.total} écriture(s)</span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1} onClick={() => { setPage((p) => p - 1); setSelected(new Set()); }}
              className="btn-secondary"
            >Précédent</button>
            <button
              disabled={page >= totalPages} onClick={() => { setPage((p) => p + 1); setSelected(new Set()); }}
              className="btn-secondary"
            >Suivant</button>
          </div>
        </div>
      )}
    </div>
  );
}
