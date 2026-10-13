import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FolderOpen, Search, SlidersHorizontal, X } from "lucide-react";
import { listInvoices, type InvoiceFilters } from "@/services/invoices";
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
  // Le statut vit dans l'adresse (?status=VALIDATED) : les cartes du tableau de bord y renvoient
  // directement, et le filtre survit à un rechargement ou à un retour en arrière.
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("status") ?? "";
  const status = STATUS_FILTERS.some((f) => f.value === requested) ? requested : "";
  function setStatus(value: string) {
    setSearchParams(value ? { status: value } : {}, { replace: true });
  }
  const [page, setPage] = useState(1);
  const size = 15;
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [advanced, setAdvanced] = useState<Omit<InvoiceFilters, "q">>({});

  // Une requête par pause de frappe, pas une par lettre.
  useEffect(() => {
    const timer = setTimeout(() => { setDebouncedSearch(search); setPage(1); }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const filters: InvoiceFilters = { q: debouncedSearch, ...advanced };
  const activeCount = Object.values(advanced).filter(Boolean).length;
  const hasFilters = Boolean(debouncedSearch) || activeCount > 0 || status !== "";

  function setAdvancedField(field: keyof typeof advanced, value: string) {
    setAdvanced((prev) => ({ ...prev, [field]: value }));
    setPage(1);
  }
  function resetFilters() {
    setSearch(""); setDebouncedSearch(""); setAdvanced({}); setStatus(""); setPage(1);
  }

  const { data, isLoading } = useQuery({
    queryKey: ["invoices", status, page, filters],
    queryFn: () => listInvoices(status || undefined, page, size, filters),
    placeholderData: (previous) => previous,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / size)) : 1;

  return (
    <div className="space-y-4">
      <PageHeader title="Historique des factures" actions={<ExportButtons />} />

      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="search" value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Fournisseur, n° de facture, fichier…" aria-label="Rechercher une facture"
            className="input pl-9"
          />
        </div>
        <button
          type="button" onClick={() => setShowFilters((v) => !v)} aria-expanded={showFilters}
          className={`btn-secondary shrink-0 ${activeCount > 0 ? "border-brand-400 text-brand-700" : ""}`}
        >
          <SlidersHorizontal size={16} /> Filtres{activeCount > 0 ? ` (${activeCount})` : ""}
        </button>
      </div>

      {showFilters && (
        <div className="card grid grid-cols-2 gap-3 p-4 animate-fade-in sm:grid-cols-4">
          <label className="text-xs text-slate-500">Date à partir du
            <input type="date" className="input mt-1" value={advanced.date_from ?? ""}
                   onChange={(e) => setAdvancedField("date_from", e.target.value)} />
          </label>
          <label className="text-xs text-slate-500">Date jusqu'au
            <input type="date" className="input mt-1" value={advanced.date_to ?? ""}
                   onChange={(e) => setAdvancedField("date_to", e.target.value)} />
          </label>
          <label className="text-xs text-slate-500">TTC minimum
            <input type="number" inputMode="decimal" min="0" className="input mt-1" value={advanced.min_amount ?? ""}
                   onChange={(e) => setAdvancedField("min_amount", e.target.value)} />
          </label>
          <label className="text-xs text-slate-500">TTC maximum
            <input type="number" inputMode="decimal" min="0" className="input mt-1" value={advanced.max_amount ?? ""}
                   onChange={(e) => setAdvancedField("max_amount", e.target.value)} />
          </label>
        </div>
      )}

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
          <EmptyState icon={FolderOpen} title="Aucun résultat"
                      hint={hasFilters ? "Aucune facture ne correspond à ces critères." : "Importez une première facture."} />
        ) : (
          <InvoiceList invoices={data?.items ?? []} detailed />
        )}
      </div>

      {hasFilters && (
        <button type="button" onClick={resetFilters} className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline">
          <X size={14} /> Effacer la recherche et les filtres
        </button>
      )}

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
