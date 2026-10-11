import { api } from "./api";
import type { JournalEntry, Paginated } from "@/types";

export interface LineCorrection {
  line_id: number;
  field: "account_code" | "debit" | "credit" | "label";
  new_value: string;
}

export async function listEntries(
  status?: string, page = 1, size = 20
): Promise<Paginated<JournalEntry>> {
  const { data } = await api.get<Paginated<JournalEntry>>("/entries", {
    params: { status, page, size },
  });
  return data;
}

export async function getEntry(id: number): Promise<JournalEntry> {
  const { data } = await api.get<JournalEntry>(`/entries/${id}`);
  return data;
}

export async function correctEntry(
  id: number, corrections: LineCorrection[]
): Promise<JournalEntry> {
  const { data } = await api.put<JournalEntry>(`/entries/${id}`, { corrections });
  return data;
}

export async function validateEntry(id: number): Promise<JournalEntry> {
  const { data } = await api.post<JournalEntry>(`/entries/${id}/validate`);
  return data;
}

export interface BatchValidateResult {
  validated: number;
  failed: number;
  results: { id: number; ok: boolean; error: string | null }[];
}

export async function validateEntriesBatch(ids: number[]): Promise<BatchValidateResult> {
  const { data } = await api.post<BatchValidateResult>("/entries/validate-batch", { entry_ids: ids });
  return data;
}

export type ExportFormat = "excel" | "csv" | "pdf";

const EXPORT_FILENAMES: Record<ExportFormat, string> = {
  excel: "journal_achats.xlsx",
  csv: "journal_achats.csv",
  pdf: "journal_achats.pdf",
};

// L'export est protégé par JWT : un <a href> classique ne porte pas l'en-tête
// Authorization (le navigateur navigue directement, hors d'axios), ce qui
// produisait un 401 au lieu du fichier. On récupère donc le fichier en Blob
// via axios, puis on déclenche le téléchargement programmatiquement.
export async function downloadEntriesExport(format: ExportFormat): Promise<void> {
  const { data } = await api.get(`/entries/export/${format}`, { responseType: "blob" });
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = EXPORT_FILENAMES[format];
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
