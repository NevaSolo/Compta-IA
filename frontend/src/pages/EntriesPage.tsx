import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listEntries } from "@/services/entries";
import { Receipt } from "lucide-react";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { ExportButtons } from "@/components/ExportButtons";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";
import type { EntryStatus } from "@/types";

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

  const { data, isLoading } = useQuery({
    queryKey: ["entries", status, page],
    queryFn: () => listEntries(status || undefined, page, size),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / size)) : 1;

  return (
    <div className="space-y-4">
      <PageHeader title="Écritures comptables" actions={<ExportButtons />} />

      <div className="flex flex-wrap gap-2">
        {STATUS_FILTERS.map((filter) => (
          <button
            key={filter.value}
            onClick={() => { setStatus(filter.value); setPage(1); }}
            className={`rounded-full px-3 py-1 text-sm transition-colors ${
              status === filter.value
                ? "bg-brand-600 text-white shadow-sm"
                : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-50"
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {isLoading && Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="card space-y-2 p-5">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-24 w-full" />
          </div>
        ))}

        {data?.items.map((entry) => (
          <div key={entry.id} className="card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-5 py-3">
              <div className="flex items-center gap-3">
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

            <div className="overflow-x-auto">
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

      {data && data.total > size && (
        <div className="flex items-center justify-between text-sm text-slate-600">
          <span>Page {page} / {totalPages} — {data.total} écriture(s)</span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
              className="btn-secondary"
            >Précédent</button>
            <button
              disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}
              className="btn-secondary"
            >Suivant</button>
          </div>
        </div>
      )}
    </div>
  );
}
