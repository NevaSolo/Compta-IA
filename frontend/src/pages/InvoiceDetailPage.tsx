import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getEntities, getEntriesOfInvoice, getInvoice, getOcrResult,
  rejectInvoice, reprocessInvoice,
} from "@/services/invoices";
import { correctEntry, validateEntry, type LineCorrection } from "@/services/entries";
import { listAccounts } from "@/services/accounts";
import { FileSearch } from "lucide-react";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";
import { apiErrorMessage } from "@/services/api";
import { useInvoiceFileUrl } from "@/hooks/useInvoiceFileUrl";
import { useToast } from "@/context/ToastContext";
import { usePipelineProgress } from "@/context/PipelineProgressContext";
import type { EntryLine, JournalEntry } from "@/types";

const PIPELINE_RUNNING_STATUSES = new Set([
  "UPLOADED", "PREPROCESSING", "OCR_DONE", "ANALYZED",
]);

export function InvoiceDetailPage() {
  const { id } = useParams();
  const invoiceId = Number(id);
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const { track } = usePipelineProgress();
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);

  const invoiceQuery = useQuery({
    queryKey: ["invoice", invoiceId],
    queryFn: () => getInvoice(invoiceId),
    refetchInterval: (query) =>
      query.state.data && PIPELINE_RUNNING_STATUSES.has(query.state.data.status) ? 2000 : false,
  });

  // Si la page est ouverte (ou rechargée) pendant qu'un pipeline tourne déjà
  // (upload lancé depuis un autre onglet, retour sur la page…), on rattache
  // le widget de progression bas-droite plutôt que de le limiter au seul cas
  // "upload depuis cette session".
  useEffect(() => {
    if (invoiceQuery.data && PIPELINE_RUNNING_STATUSES.has(invoiceQuery.data.status)) {
      track(invoiceId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invoiceId, invoiceQuery.data?.status]);

  const isPipelineDone = invoiceQuery.data
    ? !PIPELINE_RUNNING_STATUSES.has(invoiceQuery.data.status)
    : false;

  const ocrQuery = useQuery({
    queryKey: ["ocr", invoiceId], queryFn: () => getOcrResult(invoiceId),
    enabled: isPipelineDone, retry: false,
  });
  const entitiesQuery = useQuery({
    queryKey: ["entities", invoiceId], queryFn: () => getEntities(invoiceId),
    enabled: isPipelineDone, retry: false,
  });
  const entriesQuery = useQuery({
    queryKey: ["entries", invoiceId], queryFn: () => getEntriesOfInvoice(invoiceId),
    enabled: isPipelineDone, retry: false,
  });
  const accountsQuery = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const sourceFile = useInvoiceFileUrl(invoiceId);

  const rejectMutation = useMutation({
    mutationFn: (reason: string) => rejectInvoice(invoiceId, reason),
    onSuccess: () => {
      notify("success", "Facture rejetée.");
      setShowReject(false);
      queryClient.invalidateQueries({ queryKey: ["invoice", invoiceId] });
    },
    onError: (err) => notify("error", apiErrorMessage(err)),
  });
  const reprocessMutation = useMutation({
    mutationFn: () => reprocessInvoice(invoiceId),
    onSuccess: () => {
      notify("success", "Pipeline relancé.");
      track(invoiceId);
      queryClient.invalidateQueries({ queryKey: ["invoice", invoiceId] });
    },
    onError: (err) => notify("error", apiErrorMessage(err)),
  });

  if (invoiceQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-7 w-64" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Skeleton className="h-96 w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      </div>
    );
  }
  if (invoiceQuery.isError || !invoiceQuery.data) {
    return <div className="card"><EmptyState icon={FileSearch} title="Facture introuvable" /></div>;
  }
  const invoice = invoiceQuery.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 break-all">{invoice.original_filename}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <StatusBadge status={invoice.status} />
            {invoice.document_type === "AVOIR" && (
              <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800">
                Facture d'avoir — écriture inversée
              </span>
            )}
            {invoice.arithmetic_ok === false && (
              <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-700">
                Incohérence HT + TVA ≠ TTC — à vérifier
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => reprocessMutation.mutate()}
            disabled={reprocessMutation.isPending || PIPELINE_RUNNING_STATUSES.has(invoice.status)}
            className="btn-secondary"
          >Relancer le pipeline</button>
          <button
            onClick={() => setShowReject((v) => !v)}
            className="btn-danger"
          >Rejeter</button>
        </div>
      </div>

      {showReject && (
        <div className="flex flex-col gap-2 rounded-md border border-red-200 bg-red-50 p-3 sm:flex-row">
          <input
            value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Motif du rejet…"
            className="input flex-1"
          />
          <button
            onClick={() => rejectMutation.mutate(rejectReason)}
            disabled={rejectReason.length < 3 || rejectMutation.isPending}
            className="btn bg-red-600 text-white hover:bg-red-700"
          >Confirmer</button>
        </div>
      )}

      {invoice.status === "ERROR" && (
        <p className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
          {invoice.error_message ?? "Le traitement a échoué."}
        </p>
      )}
      {PIPELINE_RUNNING_STATUSES.has(invoice.status) && (
        <p className="rounded-md bg-blue-50 px-4 py-3 text-sm text-blue-700">
          Pipeline IA en cours ({invoice.status})… actualisation automatique.
        </p>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Visualisation de la facture source */}
        <div className="card p-4">
          <h2 className="mb-3 font-semibold text-slate-800">Facture source</h2>
          {sourceFile.isLoading && <p className="text-sm text-slate-400">Chargement du fichier…</p>}
          {sourceFile.isError && <p className="text-sm text-red-600">Impossible de charger le fichier source.</p>}
          {sourceFile.url && (
            invoice.original_filename.toLowerCase().endsWith(".pdf") ? (
              <iframe src={sourceFile.url} className="h-[600px] w-full rounded-md" title="Facture PDF" />
            ) : (
              <img src={sourceFile.url} alt="Facture" className="max-h-[600px] w-full rounded-md object-contain" />
            )
          )}
        </div>

        {/* Données extraites + OCR */}
        <div className="space-y-4">
          <div className="card p-4">
            <h2 className="mb-3 font-semibold text-slate-800">Données extraites</h2>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-slate-500">Fournisseur</dt>
              <dd className="font-medium">{invoice.supplier_name ?? "—"}</dd>
              <dt className="text-slate-500">N° facture</dt>
              <dd className="font-medium">{invoice.invoice_number ?? "—"}</dd>
              <dt className="text-slate-500">Date</dt>
              <dd className="font-medium">{invoice.invoice_date ?? "—"}</dd>
              <dt className="text-slate-500">Total HT</dt>
              <dd className="font-medium">{invoice.total_ht ?? "—"}</dd>
              <dt className="text-slate-500">TVA</dt>
              <dd className="font-medium">{invoice.total_vat ?? "—"}</dd>
              <dt className="text-slate-500">Total TTC</dt>
              <dd className="font-medium">{invoice.total_ttc ?? "—"} {invoice.currency}</dd>
              <dt className="text-slate-500">Langue détectée</dt>
              <dd className="font-medium">{invoice.language ?? "—"}</dd>
            </dl>

            {entitiesQuery.data && entitiesQuery.data.length > 0 && (
              <details className="mt-3 text-sm">
                <summary className="cursor-pointer text-brand-700">
                  Détail des entités extraites ({entitiesQuery.data.length})
                </summary>
                <table className="mt-2 w-full text-xs">
                  <thead className="text-left text-slate-400">
                    <tr><th>Type</th><th>Valeur</th><th>Méthode</th><th>Confiance</th></tr>
                  </thead>
                  <tbody>
                    {entitiesQuery.data.map((entity, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        <td className="py-1">{entity.entity_type}</td>
                        <td className="py-1">{entity.normalized_value ?? entity.raw_value}</td>
                        <td className="py-1">{entity.method}</td>
                        <td className="py-1"><ConfidenceBadge score={entity.confidence} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
          </div>

          {ocrQuery.data && (
            <div className="card p-4">
              <h2 className="mb-2 font-semibold text-slate-800">
                Résultat OCR ({ocrQuery.data.engine}, confiance {Math.round(ocrQuery.data.mean_confidence * 100)}%)
              </h2>
              <details className="text-xs">
                <summary className="cursor-pointer text-brand-700">Voir le texte brut</summary>
                <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-slate-50 p-3 text-slate-600">
                  {ocrQuery.data.raw_text}
                </pre>
              </details>
            </div>
          )}
        </div>
      </div>

      {entriesQuery.data?.map((entry) => (
        <EntryPanel key={entry.id} entry={entry} accounts={accountsQuery.data ?? []} />
      ))}
    </div>
  );
}

function EntryPanel({
  entry, accounts,
}: {
  entry: JournalEntry;
  accounts: { code: string; label: string }[];
}) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [lines, setLines] = useState<EntryLine[]>(entry.lines);
  const dirty = useMemo(
    () => JSON.stringify(lines) !== JSON.stringify(entry.lines), [lines, entry.lines]
  );

  const totalDebit = lines.reduce((sum, l) => sum + Number(l.debit || 0), 0);
  const totalCredit = lines.reduce((sum, l) => sum + Number(l.credit || 0), 0);
  const isBalanced = Math.abs(totalDebit - totalCredit) < 0.005;

  const correctMutation = useMutation({
    mutationFn: (corrections: LineCorrection[]) => correctEntry(entry.id, corrections),
    onSuccess: () => {
      notify("success", "Corrections enregistrées.");
      queryClient.invalidateQueries({ queryKey: ["entries", entry.invoice_id] });
    },
    onError: (err) => notify("error", apiErrorMessage(err)),
  });
  const validateMutation = useMutation({
    mutationFn: () => validateEntry(entry.id),
    onSuccess: () => {
      notify("success", "Écriture validée définitivement.");
      queryClient.invalidateQueries({ queryKey: ["entries", entry.invoice_id] });
      queryClient.invalidateQueries({ queryKey: ["invoice", entry.invoice_id] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err) => notify("error", apiErrorMessage(err)),
  });

  function updateLine(index: number, field: keyof EntryLine, value: string) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)));
  }

  function saveCorrections() {
    const corrections: LineCorrection[] = [];
    lines.forEach((line, i) => {
      const original = entry.lines[i];
      if (!line.id) return;
      if (line.account_code !== original.account_code) {
        corrections.push({ line_id: line.id, field: "account_code", new_value: line.account_code });
      }
      if (line.debit !== original.debit) {
        corrections.push({ line_id: line.id, field: "debit", new_value: line.debit });
      }
      if (line.credit !== original.credit) {
        corrections.push({ line_id: line.id, field: "credit", new_value: line.credit });
      }
      if (line.label !== original.label) {
        corrections.push({ line_id: line.id, field: "label", new_value: line.label });
      }
    });
    if (corrections.length > 0) correctMutation.mutate(corrections);
  }

  const readOnly = entry.status === "VALIDATED";

  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold text-slate-800">
          Écriture proposée — {entry.label} ({entry.entry_date})
        </h2>
        <div className="flex items-center gap-2">
          <StatusBadge status={entry.status} />
          <ConfidenceBadge score={entry.confidence_score} />
        </div>
      </div>

      <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-slate-500">
          <tr>
            <th className="pb-2 font-medium">Compte</th>
            <th className="pb-2 font-medium">Libellé</th>
            <th className="pb-2 font-medium text-right">Débit</th>
            <th className="pb-2 font-medium text-right">Crédit</th>
            <th className="pb-2 font-medium">Confiance ML</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line, i) => (
            <tr key={line.id ?? i} className="border-t border-slate-100">
              <td className="py-1.5 pr-2">
                {readOnly ? (
                  <span>{line.account_code}</span>
                ) : (
                  <select
                    value={line.account_code}
                    onChange={(e) => updateLine(i, "account_code", e.target.value)}
                    className="w-28 rounded-md border border-slate-300 px-2 py-1 text-sm"
                  >
                    {(() => {
                      const current = accounts.find((a) => a.code === line.account_code);
                      return (
                        <option value={line.account_code}>
                          {current ? `${current.code} — ${current.label}` : line.account_code}
                        </option>
                      );
                    })()}
                    {accounts.filter((a) => a.code !== line.account_code).map((a) => (
                      <option key={a.code} value={a.code}>{a.code} — {a.label}</option>
                    ))}
                  </select>
                )}
              </td>
              <td className="py-1.5 pr-2">
                {readOnly ? line.label : (
                  <input
                    value={line.label} onChange={(e) => updateLine(i, "label", e.target.value)}
                    className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
                  />
                )}
              </td>
              <td className="py-1.5 pr-2 text-right">
                {readOnly ? line.debit : (
                  <input
                    value={line.debit} onChange={(e) => updateLine(i, "debit", e.target.value)}
                    className="w-28 rounded-md border border-slate-300 px-2 py-1 text-right text-sm"
                  />
                )}
              </td>
              <td className="py-1.5 text-right">
                {readOnly ? line.credit : (
                  <input
                    value={line.credit} onChange={(e) => updateLine(i, "credit", e.target.value)}
                    className="w-28 rounded-md border border-slate-300 px-2 py-1 text-right text-sm"
                  />
                )}
              </td>
              <td className="py-1.5 pl-2"><ConfidenceBadge score={line.account_confidence} /></td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-slate-200 font-semibold">
            <td colSpan={2} className="pt-2">Total</td>
            <td className={`pt-2 text-right ${isBalanced ? "" : "text-red-600"}`}>
              {totalDebit.toFixed(2)}
            </td>
            <td className={`pt-2 text-right ${isBalanced ? "" : "text-red-600"}`}>
              {totalCredit.toFixed(2)}
            </td>
            <td />
          </tr>
        </tfoot>
      </table>
      </div>

      {!isBalanced && (
        <p className="mt-2 text-xs text-red-600">
          Écriture déséquilibrée — corrigez les montants avant de valider.
        </p>
      )}

      {!readOnly && (
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button
            onClick={saveCorrections} disabled={!dirty || correctMutation.isPending}
            className="btn-secondary"
          >Enregistrer les corrections</button>
          <button
            onClick={() => validateMutation.mutate()}
            disabled={!isBalanced || dirty || validateMutation.isPending}
            className="btn-success"
          >Valider définitivement</button>
        </div>
      )}
    </div>
  );
}
