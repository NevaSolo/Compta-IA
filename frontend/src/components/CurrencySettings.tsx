import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { apiErrorMessage } from "@/services/api";
import { CURRENCIES, deleteRate, listRates, saveRate, setBaseCurrency } from "@/services/companies";
import { formatNumber } from "@/utils/format";

/** Devise de tenue de comptabilité de l'entreprise + taux de change utilisés
 * pour convertir les factures en devise étrangère. Réservé à l'administrateur
 * de l'entreprise (le serveur contrôle aussi les droits). */
export function CurrencySettings({ companyId }: { companyId: number }) {
  const { user, setUser } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const base = user?.company_currency ?? "MGA";
  const [choice, setChoice] = useState(base);
  const [confirming, setConfirming] = useState(false);
  const foreign = CURRENCIES.filter((c) => c !== base);
  const [form, setForm] = useState({
    currency: foreign[0] as string, rate: "", date: new Date().toISOString().slice(0, 10),
  });

  const rates = useQuery({ queryKey: ["rates", companyId], queryFn: () => listRates(companyId) });

  const changeCurrency = useMutation({
    mutationFn: () => setBaseCurrency(companyId, choice),
    onSuccess: (company) => {
      setUser({ ...user!, company_currency: company.base_currency });
      setConfirming(false);
      setForm((f) => ({ ...f, currency: CURRENCIES.find((c) => c !== company.base_currency) as string }));
      notify("success", `Devise de l'entreprise : ${company.base_currency}.`);
    },
    onError: (err) => { setConfirming(false); setChoice(base); notify("error", apiErrorMessage(err)); },
  });

  const addRate = useMutation({
    mutationFn: () => saveRate(companyId, { currency: form.currency, rate: form.rate, effective_date: form.date }),
    onSuccess: () => {
      setForm((f) => ({ ...f, rate: "" }));
      queryClient.invalidateQueries({ queryKey: ["rates", companyId] });
      notify("success", "Taux enregistré.");
    },
    onError: (err) => notify("error", apiErrorMessage(err)),
  });

  const removeRate = useMutation({
    mutationFn: (id: number) => deleteRate(companyId, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rates", companyId] }),
    onError: (err) => notify("error", apiErrorMessage(err)),
  });

  function submitRate(event: FormEvent) {
    event.preventDefault();
    addRate.mutate();
  }

  return (
    <div className="space-y-5">
      <div>
        <label className="block text-sm text-slate-500" htmlFor="base-currency">
          Devise de l'entreprise
        </label>
        <div className="mt-1 flex gap-2">
          <select id="base-currency" className="input" value={choice} onChange={(e) => setChoice(e.target.value)}>
            {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button type="button" className="btn-primary shrink-0" disabled={choice === base || changeCurrency.isPending}
                  onClick={() => setConfirming(true)}>
            Appliquer
          </button>
        </div>
        <p className="mt-1 text-xs text-slate-400">
          Elle ne peut plus être changée une fois des écritures validées.
        </p>
      </div>

      <div>
        <p className="text-sm font-medium text-slate-700">Taux de change</p>
        <p className="text-xs text-slate-400">
          1 unité de la devise étrangère = le taux indiqué, en {base}. Le taux appliqué à une facture est
          le plus récent à sa date.
        </p>

        {rates.data && rates.data.length > 0 ? (
          <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
            {rates.data.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="font-medium tabular-nums">1 {r.currency} = {formatNumber(r.rate)} {base}</span>
                  <span className="ml-2 whitespace-nowrap text-xs text-slate-400">
                    depuis le {new Date(r.effective_date + "T00:00:00").toLocaleDateString("fr-FR")}
                  </span>
                </span>
                <button type="button" aria-label={`Supprimer le taux ${r.currency} du ${r.effective_date}`}
                        onClick={() => removeRate.mutate(r.id)}
                        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-red-50 hover:text-red-600">
                  <Trash2 size={16} />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-500">
            Aucun taux enregistré : une facture en devise étrangère attendra que vous saisissiez son taux.
          </p>
        )}

        <form onSubmit={submitRate} className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-[6rem,1fr,9rem,auto]">
          <select className="input" value={form.currency} aria-label="Devise"
                  onChange={(e) => setForm({ ...form, currency: e.target.value })}>
            {foreign.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <input className="input" type="number" inputMode="decimal" step="any" min="0" required
                 placeholder={`Taux en ${base}`} aria-label="Taux" value={form.rate}
                 onChange={(e) => setForm({ ...form, rate: e.target.value })} />
          <input className="input" type="date" required aria-label="Date d'effet" value={form.date}
                 onChange={(e) => setForm({ ...form, date: e.target.value })} />
          <button type="submit" className="btn-secondary col-span-2 sm:col-span-1"
                  disabled={addRate.isPending || !form.rate}>
            Ajouter
          </button>
        </form>
        {Number(form.rate) > 0 && Number(form.rate) < 0.01 && (
          <p className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Ce taux est très petit : saisissez-le avec ses 6 décimales (par exemple 0.000202 et non 0.0002),
            sinon chaque conversion perd en précision. Vous pouvez aussi garder comme devise de l'entreprise
            celle qui a la plus grande valeur unitaire.
          </p>
        )}
      </div>

      <ConfirmDialog
        open={confirming} tone="danger" loading={changeCurrency.isPending}
        title={`Passer la comptabilité en ${choice} ?`} confirmLabel="Changer la devise"
        onCancel={() => setConfirming(false)} onConfirm={() => changeCurrency.mutate()}
      >
        Les prochaines écritures seront générées en {choice}. Les écritures déjà proposées ne sont pas
        converties : relancez le traitement des factures concernées. Les taux enregistrés devront être
        adaptés à cette devise.
      </ConfirmDialog>
    </div>
  );
}
