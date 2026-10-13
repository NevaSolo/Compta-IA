import { api } from "./api";
import type {
  DashboardStats, ExtractedEntity, Invoice, JournalEntry, OcrResult, Paginated,
} from "@/types";

export async function uploadInvoice(file: File): Promise<Invoice> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<Invoice>("/invoices", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export interface InvoiceFilters {
  q?: string;
  date_from?: string;
  date_to?: string;
  min_amount?: string;
  max_amount?: string;
}

export async function listInvoices(
  status?: string, page = 1, size = 20, filters: InvoiceFilters = {}
): Promise<Paginated<Invoice>> {
  // Les filtres vides sont retirés : l'API les traite comme absents, mais une
  // chaîne vide en paramètre de date serait rejetée (422).
  const active = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
  const { data } = await api.get<Paginated<Invoice>>("/invoices", {
    params: { status, page, size, ...active },
  });
  return data;
}

export async function getInvoice(id: number): Promise<Invoice> {
  const { data } = await api.get<Invoice>(`/invoices/${id}`);
  return data;
}

// Le fichier source est protégé par JWT : impossible de le mettre en `src`
// d'une balise <img>/<iframe> (le navigateur n'y ajoute pas l'en-tête
// Authorization). On le récupère donc en Blob via axios, puis on construit
// une URL objet locale — voir useInvoiceFileUrl().
export async function getInvoiceFileBlob(id: number): Promise<Blob> {
  const { data } = await api.get(`/invoices/${id}/file`, { responseType: "blob" });
  return data;
}

export async function getOcrResult(id: number): Promise<OcrResult> {
  const { data } = await api.get<OcrResult>(`/invoices/${id}/ocr`);
  return data;
}

export async function getEntities(id: number): Promise<ExtractedEntity[]> {
  const { data } = await api.get<ExtractedEntity[]>(`/invoices/${id}/entities`);
  return data;
}

export async function reprocessInvoice(id: number): Promise<void> {
  await api.post(`/invoices/${id}/reprocess`);
}

export async function rejectInvoice(id: number, reason: string): Promise<Invoice> {
  const { data } = await api.post<Invoice>(`/invoices/${id}/reject`, { reason });
  return data;
}

export async function getEntriesOfInvoice(id: number): Promise<JournalEntry[]> {
  const { data } = await api.get<JournalEntry[]>(`/entries/by-invoice/${id}`);
  return data;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const { data } = await api.get<DashboardStats>("/dashboard");
  return data;
}

export async function setInvoiceRate(id: number, rate: string, saveForCompany: boolean): Promise<Invoice> {
  const { data } = await api.put<Invoice>(`/invoices/${id}/exchange-rate`, {
    rate, save_for_company: saveForCompany,
  });
  return data;
}

/** Supprime une facture NON validée (fichier, traitement et écritures proposées). */
export async function deleteInvoice(id: number): Promise<void> {
  await api.delete(`/invoices/${id}`);
}
