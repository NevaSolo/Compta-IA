// Types miroirs des schémas Pydantic du backend (app/presentation/schemas.py).
// Toute évolution d'un schéma côté API doit se répercuter ici.

import type { Accent, ThemeMode } from "@/theme";

export type Role = "ADMIN" | "ENTREPRISE_ADMIN" | "COMPTABLE";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  company_id: number | null;
  company_name?: string | null;
  is_active?: boolean;
  theme?: ThemeMode;
  accent?: Accent;
  avatar_version?: number | null;
  company_logo_version?: number | null;
}

export interface Company {
  id: number;
  name: string;
  nif: string | null;
  stat: string | null;
  address: string | null;
  is_active: boolean;
  logo_version?: number | null;
}

export interface AuditLogEntry {
  id: number;
  user_id: number | null;
  user_name: string | null;
  action: string;
  entity_type: string;
  entity_id: number;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  created_at: string;
}

export interface ModelVersion {
  name: string;
  version: string;
  algorithm: string;
  accuracy: number | null;
  f1_score: number | null;
  training_samples: number;
  is_active: boolean;
  trained_at: string;
}

export interface RetrainCandidate {
  algorithm: string;
  version: string;
  accuracy: number;
  f1_score: number;
}

export interface RetrainReport {
  status: "SKIPPED" | "PROMOTED" | "TRAINED_NOT_PROMOTED";
  reason?: string;
  version?: string;
  algorithm?: string;
  accuracy?: number;
  f1_score?: number;
  previous_f1?: number;
  training_samples?: number;
  candidates?: RetrainCandidate[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export type InvoiceStatus =
  | "UPLOADED" | "PREPROCESSING" | "OCR_DONE" | "ANALYZED"
  | "ENTRIES_PROPOSED" | "VALIDATED" | "REJECTED" | "ERROR";

export type PipelineStep =
  | "PREPROCESSING" | "OCR" | "LANGUAGE_DETECTION" | "ENTITY_EXTRACTION"
  | "COHERENCE_CHECK" | "CLASSIFICATION" | "RULE_ENGINE"
  | "CONFIDENCE_SCORING" | "DONE";

export type DocumentType = "FACTURE" | "AVOIR";

export interface Invoice {
  id: number;
  company_id: number | null;
  company_name?: string | null;
  original_filename: string;
  status: InvoiceStatus;
  current_step: PipelineStep | null;
  document_type: DocumentType;
  supplier_id: number | null;
  supplier_name: string | null;
  language: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  total_ht: string | null;
  total_vat: string | null;
  total_ttc: string | null;
  currency: string;
  arithmetic_ok: boolean | null;
  error_message: string | null;
  duplicate_of?: number | null;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface ExtractedEntity {
  entity_type: string;
  raw_value: string;
  normalized_value: string | null;
  confidence: number;
  method: "REGEX" | "NER";
  source_block: { bbox: number[][]; text: string } | null;
}

export interface OcrBlockOut {
  text: string;
  bbox: number[][];
  confidence: number;
}

export interface OcrResult {
  engine: string;
  raw_text: string;
  mean_confidence: number;
  duration_ms: number;
  blocks: OcrBlockOut[];
}

export type EntryStatus = "PROPOSED" | "CORRECTED" | "VALIDATED";

export interface EntryLine {
  id: number | null;
  account_code: string;
  label: string;
  debit: string;
  credit: string;
  account_confidence: number | null;
  suggested_by_ml: boolean;
}

export interface JournalEntry {
  id: number;
  invoice_id: number;
  entry_date: string;
  label: string;
  status: EntryStatus;
  confidence_score: number | null;
  rule_code: string | null;
  validated_at: string | null;
  total_debit: string;
  total_credit: string;
  lines: EntryLine[];
}

export interface Account {
  code: string;
  label: string;
  account_class: number;
  normal_balance: "DEBIT" | "CREDIT";
}

export interface MonthlyVolumePoint {
  month: string; // "YYYY-MM"
  invoice_count: number;
  total_ttc: number;
}

export interface DashboardStats {
  total_invoices: number;
  pending_review: number;
  validated: number;
  errors: number;
  validated_without_correction_rate: number | null;
  average_confidence: number | null;
  invoices_by_status: Record<string, number>;
  operations_by_type: Record<string, number>;
  monthly_volume: MonthlyVolumePoint[];
  recent_invoices: Invoice[];
}
