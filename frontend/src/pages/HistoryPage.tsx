import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { FolderOpen } from "lucide-react";
import { listInvoices } from "@/services/invoices";
import { StatusBadge } from "@/components/StatusBadge";
import { ExportButtons } from "@/components/ExportButtons";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { TableSkeleton } from "@/components/Skeleton";

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "Tous les statuts" },
  { value: "ENTRIES_PROPOSED", label: "À vérifier" },
  { value: "VALIDATED", label: "Validées" },
  { value: "ERROR", label: "En erreur" },
  { value: "REJECTED", label: "Rejetées" },
];

export function HistoryPage() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const size = 15;

  const { data, isLoading } = useQuery({
    queryKey: ["invoices", status, page],
    queryFn: () => listInvoices(status || undefined, page, size),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / size)) : 1;

  return (
    <div className="space-y-4">
      <PageHeader title="Historique des factures" actions={<ExportButtons />} />

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

      <div className="card overflow-hidden">
        {isLoading ? (
          <TableSkeleton rows={6} cols={6} />
        ) : data && data.items.length === 0 ? (
          <EmptyState icon={FolderOpen} title="Aucun résultat" hint="Essayez un autre filtre de statut." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-500">
                <tr>
                  <th className="px-5 py-2 font-medium">Fichier</th>
                  <th className="px-5 py-2 font-medium">Fournisseur</th>
                  <th className="px-5 py-2 font-medium">N° facture</th>
                  <th className="px-5 py-2 font-medium">Date</th>
                  <th className="px-5 py-2 font-medium">Total TTC</th>
                  <th className="px-5 py-2 font-medium">Statut</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((invoice) => (
                  <tr key={invoice.id} className="border-t border-slate-100 hover:bg-slate-50">
                    <td className="px-5 py-2.5">
                      <Link to={`/factures/${invoice.id}`} className="text-brand-700 hover:underline">
                        {invoice.original_filename}
                      </Link>
                    </td>
                    <td className="px-5 py-2.5">{invoice.supplier_name ?? "—"}</td>
                    <td className="px-5 py-2.5">{invoice.invoice_number ?? "—"}</td>
                    <td className="px-5 py-2.5">{invoice.invoice_date ?? "—"}</td>
                    <td className="px-5 py-2.5">
                      {invoice.total_ttc ? `${invoice.total_ttc} ${invoice.currency}` : "—"}
                    </td>
                    <td className="px-5 py-2.5"><StatusBadge status={invoice.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {data && data.total > size && (
        <div className="flex items-center justify-between text-sm text-slate-600">
          <span>Page {page} / {totalPages} — {data.total} facture(s)</span>
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
