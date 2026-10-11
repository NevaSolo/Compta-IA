import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FolderOpen } from "lucide-react";
import { listInvoices } from "@/services/invoices";
import { InvoiceList } from "@/components/InvoiceList";
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

      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] md:mx-0 md:flex-wrap md:px-0">
        {STATUS_FILTERS.map((filter) => (
          <button
            key={filter.value}
            onClick={() => { setStatus(filter.value); setPage(1); }}
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

      <div className="card overflow-hidden">
        {isLoading ? (
          <TableSkeleton rows={6} cols={6} />
        ) : data && data.items.length === 0 ? (
          <EmptyState icon={FolderOpen} title="Aucun résultat" hint="Essayez un autre filtre de statut." />
        ) : (
          <InvoiceList invoices={data?.items ?? []} detailed />
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
