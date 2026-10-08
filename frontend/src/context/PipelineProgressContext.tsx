import {
  createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode,
} from "react";
import { CheckCircle2, CircleDashed, Loader2, X, XCircle } from "lucide-react";
import { getInvoice } from "@/services/invoices";
import type { Invoice, PipelineStep } from "@/types";

const STEPS: { key: PipelineStep; label: string }[] = [
  { key: "PREPROCESSING", label: "Prétraitement de l'image" },
  { key: "OCR", label: "Lecture OCR" },
  { key: "LANGUAGE_DETECTION", label: "Détection de la langue" },
  { key: "ENTITY_EXTRACTION", label: "Extraction des données" },
  { key: "COHERENCE_CHECK", label: "Contrôle de cohérence" },
  { key: "CLASSIFICATION", label: "Classification IA" },
  { key: "RULE_ENGINE", label: "Génération de l'écriture" },
  { key: "CONFIDENCE_SCORING", label: "Score de confiance" },
];

const POLL_MS = 2000;

interface TrackedEntry {
  invoice: Invoice | null;
  done: boolean; // succès (ENTRIES_PROPOSED) ou échec (ERROR) : polling arrêté
}

interface PipelineProgressState {
  /** Démarre (ou reprend) le suivi en temps réel d'une facture en cours de
   * traitement — appelé après un upload ou un "Relancer le pipeline". */
  track: (invoiceId: number) => void;
}

const AUTO_CLOSE_MS = 2500; // fermeture auto de la modale après un succès

const PipelineProgressContext = createContext<PipelineProgressState | null>(null);

function stepIndex(step: PipelineStep | null): number {
  if (!step || step === "DONE") return STEPS.length;
  return STEPS.findIndex((s) => s.key === step);
}

/** Modale de suivi pas-à-pas du pipeline IA — distincte des toasts ponctuels
 * (ToastContext) : ceci reflète un état vivant qui se met à jour en place au
 * fil du polling, pas un message éphémère. Se ferme seule en cas de succès,
 * reste ouverte (fermeture manuelle) en cas d'échec pour garder l'erreur
 * lisible. */
export function PipelineProgressProvider({ children }: { children: ReactNode }) {
  const [tracked, setTracked] = useState<Record<number, TrackedEntry>>({});
  const dismissTimers = useRef<Record<number, number>>({});

  const track = useCallback((invoiceId: number) => {
    setTracked((prev) => (prev[invoiceId] ? prev : { ...prev, [invoiceId]: { invoice: null, done: false } }));
  }, []);

  const activeIds = Object.entries(tracked)
    .filter(([, t]) => !t.done)
    .map(([id]) => Number(id));
  // Sérialisé pour ne redéclencher l'effet de polling que si l'ensemble
  // des factures suivies change réellement (pas à chaque nouveau contenu).
  const activeIdsKey = activeIds.join(",");

  useEffect(() => {
    if (activeIds.length === 0) return;
    let cancelled = false;

    const poll = async () => {
      await Promise.all(activeIds.map(async (id) => {
        try {
          const invoice = await getInvoice(id);
          if (cancelled) return;
          const finished = invoice.status === "ENTRIES_PROPOSED" || invoice.status === "ERROR";
          setTracked((prev) => (prev[id] ? { ...prev, [id]: { invoice, done: finished } } : prev));
        } catch {
          if (cancelled) return;
          setTracked((prev) => {
            const next = { ...prev };
            delete next[id];
            return next;
          });
        }
      }));
    };

    poll();
    const interval = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(interval); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIdsKey]);

  const dismiss = useCallback((id: number) => {
    setTracked((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    if (dismissTimers.current[id] !== undefined) {
      clearTimeout(dismissTimers.current[id]);
      delete dismissTimers.current[id];
    }
  }, []);

  useEffect(() => {
    Object.entries(tracked).forEach(([idStr, entry]) => {
      const id = Number(idStr);
      // Fermeture automatique uniquement en cas de succès — en cas
      // d'échec, on laisse la modale ouverte pour que le message d'erreur
      // reste lisible (fermeture manuelle requise).
      const shouldAutoClose = entry.done && entry.invoice?.status === "ENTRIES_PROPOSED";
      if (shouldAutoClose && dismissTimers.current[id] === undefined) {
        dismissTimers.current[id] = window.setTimeout(() => {
          dismiss(id);
        }, AUTO_CLOSE_MS);
      }
    });
  }, [tracked, dismiss]);

  const visible = Object.entries(tracked)
    .map(([id, entry]) => ({ id: Number(id), ...entry }))
    .filter((entry) => entry.invoice !== null) as { id: number; invoice: Invoice; done: boolean }[];

  return (
    <PipelineProgressContext.Provider value={{ track }}>
      {children}
      {visible.length > 0 && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 animate-fade-in">
          <div className="max-h-[85vh] w-full max-w-md space-y-4 overflow-y-auto">
            {visible.map(({ id, invoice }) => (
              <PipelineProgressCard key={id} invoice={invoice} onClose={() => dismiss(id)} />
            ))}
          </div>
        </div>
      )}
    </PipelineProgressContext.Provider>
  );
}

function PipelineProgressCard({ invoice, onClose }: { invoice: Invoice; onClose: () => void }) {
  const failed = invoice.status === "ERROR";
  const succeeded = invoice.status === "ENTRIES_PROPOSED";
  const currentIndex = stepIndex(invoice.current_step);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xl animate-slide-up">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-800">
            {succeeded ? "Traitement terminé" : failed ? "Traitement en erreur" : "Traitement IA en cours…"}
          </p>
          <p className="truncate text-xs text-slate-400" title={invoice.original_filename}>
            {invoice.original_filename}
          </p>
        </div>
        <button
          onClick={onClose}
          aria-label="Fermer"
          className="shrink-0 rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
        ><X size={16} /></button>
      </div>
      <ul className="space-y-2">
        {STEPS.map((step, index) => {
          const isFailedStep = failed && index === currentIndex;
          const isDone = index < currentIndex || (index === currentIndex && succeeded);
          const isCurrent = index === currentIndex && !failed && !succeeded;
          return (
            <li key={step.key} className="flex items-center gap-2.5 text-sm">
              {isFailedStep && <XCircle size={16} className="shrink-0 text-red-600" />}
              {!isFailedStep && isDone && <CheckCircle2 size={16} className="shrink-0 text-emerald-600" />}
              {!isFailedStep && isCurrent && <Loader2 size={16} className="shrink-0 animate-spin text-blue-600" />}
              {!isFailedStep && !isDone && !isCurrent && <CircleDashed size={16} className="shrink-0 text-slate-300" />}
              <span
                className={
                  isFailedStep ? "text-red-700"
                  : isDone ? "text-slate-500 line-through decoration-slate-300"
                  : isCurrent ? "font-medium text-slate-800"
                  : "text-slate-400"
                }
              >
                {step.label}
              </span>
            </li>
          );
        })}
      </ul>
      {failed && invoice.error_message && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{invoice.error_message}</p>
      )}
    </div>
  );
}

export function usePipelineProgress(): PipelineProgressState {
  const ctx = useContext(PipelineProgressContext);
  if (!ctx) throw new Error("usePipelineProgress doit être utilisé sous PipelineProgressProvider");
  return ctx;
}
