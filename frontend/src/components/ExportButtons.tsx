import { useState } from "react";
import { FileSpreadsheet, FileText, type LucideIcon } from "lucide-react";
import { downloadEntriesExport, type ExportFormat } from "@/services/entries";
import { apiErrorMessage } from "@/services/api";
import { useToast } from "@/context/ToastContext";

const OPTIONS: { format: ExportFormat; label: string; icon: LucideIcon }[] = [
  { format: "excel", label: "Excel", icon: FileSpreadsheet },
  { format: "csv", label: "CSV", icon: FileText },
  { format: "pdf", label: "PDF", icon: FileText },
];

/** Boutons d'export du journal des écritures validées, dans les trois
 * formats attendus par le cahier des charges (Excel, CSV, PDF). */
export function ExportButtons() {
  const [pending, setPending] = useState<ExportFormat | null>(null);
  const { notify } = useToast();

  async function handleExport(format: ExportFormat) {
    setPending(format);
    try {
      await downloadEntriesExport(format);
    } catch (err) {
      notify("error", apiErrorMessage(err));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="grid grid-cols-3 gap-2 sm:flex">
      {OPTIONS.map(({ format, label, icon: Icon }) => (
        <button
          key={format}
          onClick={() => handleExport(format)}
          disabled={pending !== null}
          className="btn-secondary"
        >
          <Icon size={15} />
          {pending === format ? "Export…" : label}
        </button>
      ))}
    </div>
  );
}
