import { useEffect, useRef, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, LogOut } from "lucide-react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** « success » : action positive (valider) ; « danger » : action destructive ; « info » : neutre (se déconnecter). */
  tone?: "success" | "danger" | "info";
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const TONES = {
  success: { icon: CheckCircle2, badge: "bg-emerald-100 text-emerald-700", button: "btn-success" },
  info: { icon: LogOut, badge: "bg-slate-100 text-slate-600", button: "btn-primary" },
  danger: { icon: AlertTriangle, badge: "bg-red-100 text-red-700", button: "btn bg-red-600 text-white hover:bg-red-700" },
};

/** Fenêtre de confirmation (remplace window.confirm) : sur téléphone elle
 * s'ancre en bas de l'écran, à portée de pouce ; Échap ou un toucher en
 * dehors annule, et le focus démarre sur « Annuler » pour éviter une
 * validation accidentelle à la touche Entrée. */
export function ConfirmDialog({
  open, title, children, confirmLabel = "Confirmer", cancelLabel = "Annuler",
  tone = "success", loading = false, onConfirm, onCancel,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !loading) onCancel(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, loading, onCancel]);

  if (!open) return null;
  const { icon: Icon, badge, button } = TONES[tone];

  return (
    <div
      className="fixed inset-0 z-[60] flex items-end justify-center bg-slate-900/50 p-4 animate-fade-in sm:items-center"
      onClick={() => { if (!loading) onCancel(); }}
    >
      <div
        role="dialog" aria-modal="true" aria-labelledby="confirm-title"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl rounded-2xl bg-white px-6 pt-7 shadow-xl animate-slide-up sm:px-8"
        // Espace sous les boutons + zone sûre des téléphones (barre de geste) : additionnés, jamais écrasés
        style={{ paddingBottom: "calc(2.5rem + env(safe-area-inset-bottom))" }}
      >
        <div className="flex items-start gap-3">
          <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${badge}`}>
            <Icon size={20} />
          </span>
          <div className="min-w-0">
            <h2 id="confirm-title" className="text-lg font-semibold text-slate-900">{title}</h2>
            <div className="mt-1.5 text-base text-slate-600">{children}</div>
          </div>
        </div>
        <div className="mt-7 grid grid-cols-2 gap-3 sm:flex sm:justify-end">
          <button ref={cancelRef} type="button" className="btn-secondary" disabled={loading} onClick={onCancel}>
            {cancelLabel}
          </button>
          <button type="button" className={button} disabled={loading} onClick={onConfirm}>
            {loading ? "En cours…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
