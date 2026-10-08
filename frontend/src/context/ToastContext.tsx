import {
  createContext, useCallback, useContext, useRef, useState, type ReactNode,
} from "react";
import { CheckCircle2, Info, XCircle, type LucideIcon } from "lucide-react";

export type ToastType = "success" | "error" | "info";

interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

interface ToastState {
  notify: (type: ToastType, message: string) => void;
}

const ToastContext = createContext<ToastState | null>(null);

const ICON: Record<ToastType, LucideIcon> = { success: CheckCircle2, error: XCircle, info: Info };
const STYLE: Record<ToastType, string> = {
  success: "bg-emerald-600 text-white",
  error: "bg-red-600 text-white",
  info: "bg-slate-800 text-white",
};

/** Système de notifications centralisé — retours d'action (validation,
 * correction, export, rejet…) sans polluer chaque page de son propre état
 * d'erreur/succès. Empilable, auto-disparition après 4s. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);

  const notify = useCallback((type: ToastType, message: string) => {
    const id = ++counter.current;
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  function dismiss(id: number) {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((toast) => {
          const Icon = ICON[toast.type];
          return (
            <div
              key={toast.id}
              onClick={() => dismiss(toast.id)}
              className={`flex max-w-sm cursor-pointer items-start gap-2 rounded-lg px-4 py-3 text-sm shadow-card animate-slide-up ${STYLE[toast.type]}`}
            >
              <Icon size={18} className="mt-0.5 shrink-0" />
              <span>{toast.message}</span>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastState {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast doit être utilisé sous ToastProvider");
  return ctx;
}
