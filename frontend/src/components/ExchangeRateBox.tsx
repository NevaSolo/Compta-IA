import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Coins } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { usePipelineProgress } from "@/context/PipelineProgressContext";
import { useToast } from "@/context/ToastContext";
import { apiErrorMessage } from "@/services/api";
import { reprocessInvoice, setInvoiceRate } from "@/services/invoices";
import { formatMoney, formatNumber } from "@/utils/format";
import type { Invoice } from "@/types";

/** Taux de change d'une facture en devise étrangère : celui qui a servi à
 * convertir l'écriture, ou le champ à remplir quand il manque (le traitement
 * s'arrête alors avec une erreur explicite). Appliquer un taux relance le
 * traitement pour régénérer l'écriture dans la devise de l'entreprise. */
export function ExchangeRateBox({ invoice, baseCurrency }: { invoice: Invoice; baseCurrency: string }) {
  const { user } = useAuth();
  const { notify } = useToast();
  const { track } = usePipelineProgress();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [rate, setRate] = useState(invoice.exchange_rate ?? "");
  const [remember, setRemember] = useState(false);

  const canRemember = user?.role === "ADMIN" || user?.role === "ENTREPRISE_ADMIN";
  const locked = invoice.status === "VALIDATED";
  const missing = !invoice.exchange_rate;
  const needsRate = missing && invoice.status === "ERROR";

  const apply = useMutation({
    mutationFn: async () => {
      await setInvoiceRate(invoice.id, rate, remember && canRemember);
      await reprocessInvoice(invoice.id);
    },
    onSuccess: () => {
      notify("success", "Taux appliqué, écriture en cours de régénération.");
      setEditing(false);
      track(invoice.id);
      queryClient.invalidateQueries({ queryKey: ["invoice", invoice.id] });
      queryClient.invalidateQueries({ queryKey: ["entries", invoice.id] });
      queryClient.invalidateQueries({ queryKey: ["rates"] });
    },
    onError: (err) => notify("error", apiErrorMessage(err)),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    apply.mutate();
  }

  const converted = invoice.total_ttc && invoice.exchange_rate
    ? Number(invoice.total_ttc) * Number(invoice.exchange_rate) : null;
  const showForm = !locked && (editing || missing);

  return (
    <section className={`rounded-lg border p-4 text-sm ${needsRate
      ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"}`}>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700">
          <Coins size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-slate-800">
            {needsRate ? "Taux de change requis" : `Facture en ${invoice.currency}`}
          </h2>
          <p className="mt-0.5 text-slate-600">
            {missing
              ? `Votre comptabilité est tenue en ${baseCurrency} : indiquez combien vaut 1 ${invoice.currency}
                 en ${baseCurrency} pour générer l'écriture.`
              : `1 ${invoice.currency} = ${formatNumber(invoice.exchange_rate)} ${baseCurrency}`
                + (converted !== null
                  ? ` · ${formatMoney(invoice.total_ttc)} ${invoice.currency} = ${formatMoney(converted)} ${baseCurrency}`
                  : "")}
          </p>

          {showForm ? (
            <form onSubmit={submit} className="mt-3 space-y-2">
              <div className="flex gap-2">
                <input className="input" type="number" inputMode="decimal" step="any" min="0" required
                       aria-label={`Taux : 1 ${invoice.currency} en ${baseCurrency}`}
                       placeholder="Taux, ex. 4950"
                       value={rate} onChange={(e) => setRate(e.target.value)} />
                <button type="submit" className="btn-primary shrink-0" disabled={apply.isPending || !rate}>
                  {apply.isPending ? "…" : "Appliquer et relancer"}
                </button>
              </div>
              {canRemember && (
                <label className="flex items-center gap-2 text-slate-600">
                  <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)}
                         className="h-4 w-4 rounded border-slate-300" />
                  Mémoriser ce taux pour l'entreprise (à la date de la facture)
                </label>
              )}
              {!missing && (
                <button type="button" className="text-slate-500 underline" onClick={() => setEditing(false)}>
                  Annuler
                </button>
              )}
            </form>
          ) : (
            !locked && (
              <button type="button" className="mt-2 text-brand-700 hover:underline" onClick={() => setEditing(true)}>
                Modifier le taux
              </button>
            )
          )}
        </div>
      </div>
    </section>
  );
}
