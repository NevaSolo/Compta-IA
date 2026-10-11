import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
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
import { ExchangeRateBox } from "@/components/ExchangeRateBox";
import { useAuth } from "@/context/AuthContext";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";
import { apiErrorMessage } from "@/services/api";
import { useInvoiceFileUrl } from "@/hooks/useInvoiceFileUrl";
import { useToast } from "@/context/ToastContext";
import { formatMoney } from "@/utils/format";
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
  const { user } = useAuth();
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
  const foreignCurrency = user !== null && user.company_id !== null
    && invoice.currency !== (user.company_currency ?? "MGA");

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
        <div className="grid grid-cols-2 gap-2 sm:flex">
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

      {invoice.duplicate_of && (
        <p className="rounded-md bg-orange-50 px-4 py-3 text-sm text-orange-800">
          Doublon possible : une facture plus ancienne a le même montant TTC et le même
          n° ou le même fournisseur à la même date.{" "}
          <Link to={`/factures/${invoice.duplicate_of}`} className="font-medium underline">
            Voir la facture n° {invoice.duplicate_of}
          </Link>
        </p>
      )}

      {foreignCurrency && (
        <ExchangeRateBox invoice={invoice} baseCurrency={user.company_currency ?? "MGA"} />
      )}

      {invoice.status === "ERROR" && !(foreignCurrency && !invoice.exchange_rate) && (
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
        {/* Visualisation de la facture source (après les données sur mobile) */}
        <div className="card order-2 p-4 lg:order-1">
          <h2 className="mb-3 font-semibold text-slate-800">Facture source</h2>
          {sourceFile.isLoading && <p className="text-sm text-slate-400">Chargement du fichier…</p>}
          {sourceFile.isError && <p className="text-sm text-red-600">Impossible de charger le fichier source.</p>}
          {sourceFile.url && (
            invoice.original_filename.toLowerCase().endsWith(".pdf") ? (
              <>
                <iframe src={sourceFile.url} className="h-[60vh] w-full rounded-md lg:h-[600px]" title="Facture PDF" />
                <a href={sourceFile.url} target="_blank" rel="noreferrer"
                   className="btn-secondary mt-3 w-full lg:hidden">Ouvrir le PDF en plein écran</a>
              </>
            ) : (
              <img src={sourceFile.url} alt="Facture" className="max-h-[600px] w-full rounded-md object-contain" />
            )
          )}
        </div>

        {/* Données extraites + OCR */}
        <div className="order-1 space-y-4 lg:order-2">
          <div className="card p-4">
            <h2 className="mb-3 font-semibold text-slate-800">Données extraites</h2>
            <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-2 text-sm">
              <dt className="text-slate-500">Fournisseur</dt>
              <dd className="break-words text-right font-medium sm:text-left">{invoice.supplier_name ?? "—"}</dd>
              <dt className="text-slate-500">N° facture</dt>
              <dd className="font-medium">{invoice.invoice_number ?? "—"}</dd>
              <dt className="text-slate-500">Date</dt>
              <dd className="font-medium">{invoice.invoice_date ?? "—"}</dd>
              <dt className="text-slate-500">Total HT</dt>
              <dd className="font-medium">{formatMoney(invoice.total_ht)}</dd>
              <dt className="text-slate-500">TVA</dt>
              <dd className="font-medium">{formatMoney(invoice.total_vat)}</dd>
              <dt className="text-slate-500">Total TTC</dt>
              <dd className="font-medium">{formatMoney(invoice.total_ttc)} {invoice.currency}</dd>
              <dt className="text-slate-500">Langue détectée</dt>
              <dd className="font-medium">{invoice.language ?? "—"}</dd>
            </dl>

            <PaymentInfo
              entities={entitiesQuery.data ?? []} totalTtc={invoice.total_ttc} currency={invoice.currency}
            />

            {entitiesQuery.data && entitiesQuery.data.length > 0 && (
              <details className="mt-3 text-sm">
                <summary className="cursor-pointer text-brand-700">
                  Détail des entités extraites ({entitiesQuery.data.length})
                </summary>
                <div className="overflow-x-auto"><table className="mt-2 w-full text-xs">
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
                </table></div>
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
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="font-semibold text-slate-800">
          Écriture proposée — {entry.label} ({entry.entry_date})
        </h2>
        <div className="flex items-center gap-2">
          <StatusBadge status={entry.status} />
          <ConfidenceBadge score={entry.confidence_score} />
        </div>
      </div>

      <ul className="space-y-3 md:hidden">
        {lines.map((line, i) => (
          <li key={line.id ?? i} className="space-y-2 rounded-lg border border-slate-200 p-3">
            {readOnly ? (
              <>
                <p className="font-mono text-sm text-slate-700">{line.account_code}</p>
                <p className="text-sm text-slate-600">{line.label}</p>
                <div className="flex justify-between text-sm tabular-nums">
                  <span>Débit : {formatMoney(line.debit)}</span><span>Crédit : {formatMoney(line.credit)}</span>
                </div>
              </>
            ) : (
              <>
                <select
                  value={line.account_code} aria-label="Compte"
                  onChange={(e) => updateLine(i, "account_code", e.target.value)}
                  className="input"
                >
                  {!accounts.some((a) => a.code === line.account_code) && (
                    <option value={line.account_code}>{line.account_code}</option>
                  )}
                  {accounts.map((a) => <option key={a.code} value={a.code}>{a.code} — {a.label}</option>)}
                </select>
                <input
                  value={line.label} aria-label="Libellé"
                  onChange={(e) => updateLine(i, "label", e.target.value)} className="input"
                />
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-xs text-slate-500">Débit
                    <input value={line.debit} inputMode="decimal"
                           onChange={(e) => updateLine(i, "debit", e.target.value)}
                           className="input mt-1 text-right" />
                  </label>
                  <label className="text-xs text-slate-500">Crédit
                    <input value={line.credit} inputMode="decimal"
                           onChange={(e) => updateLine(i, "credit", e.target.value)}
                           className="input mt-1 text-right" />
                  </label>
                </div>
              </>
            )}
          </li>
        ))}
        <li className="flex justify-between px-1 text-sm font-semibold tabular-nums">
          <span>Total</span>
          <span className={isBalanced ? "" : "text-red-600"}>
            {formatMoney(totalDebit)} / {formatMoney(totalCredit)}
          </span>
        </li>
      </ul>

      <div className="hidden overflow-x-auto md:block">
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
                {readOnly ? formatMoney(line.debit) : (
                  <input
                    value={line.debit} onChange={(e) => updateLine(i, "debit", e.target.value)}
                    className="w-28 rounded-md border border-slate-300 px-2 py-1 text-right text-sm"
                  />
                )}
              </td>
              <td className="py-1.5 text-right">
                {readOnly ? formatMoney(line.credit) : (
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
              {formatMoney(totalDebit)}
            </td>
            <td className={`pt-2 text-right ${isBalanced ? "" : "text-red-600"}`}>
              {formatMoney(totalCredit)}
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
        <div className="mt-4 grid gap-2 sm:flex sm:flex-wrap sm:justify-end">
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

const INFO_LABELS: Record<string, string> = {
  DEPOSIT_PAID: "Acompte déjà versé",
  NET_TO_PAY: "Net à payer",
  EARLY_PAYMENT_DISCOUNT: "Escompte possible",
};

/** Montants portés à titre d'information (jamais dans l'écriture) : l'acompte
 * a déjà été comptabilisé à son versement, le net à payer n'est qu'un solde. */
function PaymentInfo({
  entities, totalTtc, currency,
}: { entities: { entity_type: string; normalized_value: string | null; raw_value: string }[];
     totalTtc: string | null; currency: string }) {
  const value = (type: string) => entities.find((e) => e.entity_type === type)?.normalized_value ?? null;
  const rows = Object.keys(INFO_LABELS)
    .map((type) => ({ type, amount: value(type) }))
    .filter((r) => r.amount !== null);
  if (rows.length === 0) return null;

  const deposit = value("DEPOSIT_PAID");
  const net = value("NET_TO_PAY");
  const ttc = totalTtc !== null ? Number(totalTtc) : NaN;
  const checkable = net !== null && !Number.isNaN(ttc);
  const expected = ttc - (deposit !== null ? Number(deposit) : 0);
  const coherent = checkable && Math.abs(expected - Number(net)) < 0.02;

  return (
    <div className="mt-3 rounded-md bg-slate-50 p-3 text-sm">
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">
        Informations de paiement (hors écriture)
      </p>
      <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1">
        {rows.map((r) => (
          <div key={r.type} className="contents">
            <dt className="text-slate-500">{INFO_LABELS[r.type]}</dt>
            <dd className="text-right font-medium tabular-nums sm:text-left">{formatMoney(r.amount)} {currency}</dd>
          </div>
        ))}
      </dl>
      {checkable && (
        <p className={`mt-2 text-xs ${coherent ? "text-emerald-700" : "text-amber-700"}`}>
          {coherent
            ? "Cohérent : TTC − acompte = net à payer."
            : `Écart : TTC − acompte = ${formatMoney(expected)}, mais le net à payer lu est ${formatMoney(net)}. À vérifier.`}
        </p>
      )}
    </div>
  );
}
