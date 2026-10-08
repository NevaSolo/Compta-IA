import type { InvoiceStatus, EntryStatus } from "@/types";

const STYLES: Record<string, string> = {
  UPLOADED: "bg-slate-100 text-slate-700",
  PREPROCESSING: "bg-slate-100 text-slate-700",
  OCR_DONE: "bg-blue-100 text-blue-700",
  ANALYZED: "bg-blue-100 text-blue-700",
  ENTRIES_PROPOSED: "bg-amber-100 text-amber-800",
  PROPOSED: "bg-amber-100 text-amber-800",
  CORRECTED: "bg-orange-100 text-orange-800",
  VALIDATED: "bg-emerald-100 text-emerald-800",
  REJECTED: "bg-slate-200 text-slate-600",
  ERROR: "bg-red-100 text-red-700",
};

const LABELS: Record<string, string> = {
  UPLOADED: "Importée", PREPROCESSING: "Prétraitement", OCR_DONE: "OCR terminé",
  ANALYZED: "Analysée", ENTRIES_PROPOSED: "À vérifier", PROPOSED: "Proposée",
  CORRECTED: "Corrigée", VALIDATED: "Validée", REJECTED: "Rejetée", ERROR: "Erreur",
};

export function StatusBadge({ status }: { status: InvoiceStatus | EntryStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STYLES[status] ?? "bg-slate-100 text-slate-700"}`}>
      {LABELS[status] ?? status}
    </span>
  );
}
