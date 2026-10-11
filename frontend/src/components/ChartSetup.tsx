import { BookOpen } from "lucide-react";
import { ChartPicker } from "@/components/ChartPicker";
import { useAuth } from "@/context/AuthContext";

/** Écran bloquant : tant que l'entreprise n'a pas de plan comptable, aucune
 * facture ne peut être importée ni traitée. Seul l'administrateur de
 * l'entreprise peut choisir ; les autres utilisateurs sont informés. */
export function ChartSetup() {
  const { user } = useAuth();
  const canChoose = user?.role === "ENTREPRISE_ADMIN" || user?.role === "ADMIN";

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div className="card p-5 text-center">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-brand-100 text-brand-700">
          <BookOpen size={24} />
        </span>
        <h1 className="mt-3 text-xl font-bold text-slate-900">Choisissez votre plan comptable</h1>
        <p className="mt-1 text-sm text-slate-500">
          {canChoose
            ? "C'est la première étape : les écritures seront générées avec les comptes du plan choisi."
            : "Votre administrateur doit d'abord choisir le plan comptable de l'entreprise. Vous pourrez ensuite importer vos factures."}
        </p>
      </div>
      {canChoose && <ChartPicker />}
    </div>
  );
}
