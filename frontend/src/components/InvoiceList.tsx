import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { StatusBadge } from "@/components/StatusBadge";
import { formatMoney } from "@/utils/format";

interface InvoiceRow {
  id: number;
  original_filename: string;
  supplier_name?: string | null;
  invoice_number?: string | null;
  invoice_date?: string | null;
  total_ttc?: string | null;
  currency: string;
  status: Parameters<typeof StatusBadge>[0]["status"];
  duplicate_of?: number | null;
}

function DuplicateBadge({ of }: { of?: number | null }) {
  if (!of) return null;
  return (
    <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-800"
          title={`Semble identique à la facture n° ${of}`}>
      Doublon ?
    </span>
  );
}

/** Liste de factures : cartes tactiles sur téléphone (tout est lisible sans
 * défilement horizontal), tableau classique dès l'écran tablette. */
export function InvoiceList({
  invoices, detailed = false,
}: { invoices: InvoiceRow[]; detailed?: boolean }) {
  const amount = (i: InvoiceRow) => (i.total_ttc ? `${formatMoney(i.total_ttc)} ${i.currency}` : "—");

  return (
    <>
      <ul className="divide-y divide-slate-100 md:hidden">
        {invoices.map((invoice) => (
          <li key={invoice.id}>
            <Link
              to={`/factures/${invoice.id}`}
              className="flex items-center gap-3 px-4 py-3 active:bg-slate-50"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="truncate text-sm font-medium text-brand-700">{invoice.original_filename}</p>
                  <StatusBadge status={invoice.status} />
                </div>
                {invoice.duplicate_of ? <div className="mt-1"><DuplicateBadge of={invoice.duplicate_of} /></div> : null}
                <p className="mt-0.5 truncate text-sm text-slate-600">{invoice.supplier_name ?? "—"}</p>
                <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
                  <span>
                    {detailed && invoice.invoice_number ? `${invoice.invoice_number} · ` : ""}
                    {detailed ? (invoice.invoice_date ?? "") : ""}
                  </span>
                  <span className="text-sm font-semibold tabular-nums text-slate-800">{amount(invoice)}</span>
                </div>
              </div>
              <ChevronRight size={18} className="shrink-0 text-slate-300" />
            </Link>
          </li>
        ))}
      </ul>

      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-5 py-2 font-medium">Fichier</th>
              <th className="px-5 py-2 font-medium">Fournisseur</th>
              {detailed && <th className="px-5 py-2 font-medium">N° facture</th>}
              {detailed && <th className="px-5 py-2 font-medium">Date</th>}
              <th className="px-5 py-2 font-medium">Total TTC</th>
              <th className="px-5 py-2 font-medium">Statut</th>
            </tr>
          </thead>
          <tbody>
            {invoices.map((invoice) => (
              <tr key={invoice.id} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="px-5 py-2.5">
                  <Link to={`/factures/${invoice.id}`} className="text-brand-700 hover:underline">
                    {invoice.original_filename}
                  </Link>
                </td>
                <td className="px-5 py-2.5">{invoice.supplier_name ?? "—"}</td>
                {detailed && <td className="px-5 py-2.5">{invoice.invoice_number ?? "—"}</td>}
                {detailed && <td className="px-5 py-2.5">{invoice.invoice_date ?? "—"}</td>}
                <td className="px-5 py-2.5">{amount(invoice)}</td>
                <td className="px-5 py-2.5">
                  <span className="inline-flex flex-wrap items-center gap-1.5">
                    <StatusBadge status={invoice.status} /><DuplicateBadge of={invoice.duplicate_of} />
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
