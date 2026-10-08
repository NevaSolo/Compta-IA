import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { uploadInvoice } from "@/services/invoices";
import { apiErrorMessage } from "@/services/api";
import { runWithConcurrency } from "@/lib/concurrency";
import { usePipelineProgress } from "@/context/PipelineProgressContext";

const ACCEPTED_TYPES = ["application/pdf", "image/jpeg", "image/png"];
const MAX_SIZE_MB = 15; // reflète app.core.config.Settings.max_upload_size_mb
const MAX_CONCURRENT_UPLOADS = 3; // envoie par lots pour ne pas saturer le pipeline IA

export type QueueStatus = "pending" | "uploading" | "queued" | "error";

export interface QueueItem {
  key: string;
  file: File;
  status: QueueStatus;
  invoiceId?: number;
  error?: string;
}

function validate(file: File): string | null {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return "Format non pris en charge (PDF, JPG ou PNG uniquement).";
  }
  if (file.size > MAX_SIZE_MB * 1024 * 1024) {
    return `Fichier trop volumineux (max ${MAX_SIZE_MB} Mo).`;
  }
  return null;
}

interface UploadQueueState {
  queue: QueueItem[];
  isProcessing: boolean;
  handleFiles: (files: FileList | File[]) => Promise<void>;
  clearFinished: () => void;
}

const UploadQueueContext = createContext<UploadQueueState | null>(null);

// Le provider vit au-dessus des <Routes> (voir App.tsx) : son état n'est
// donc PAS remonté à chaque navigation. Avant ce fix, la file d'upload
// était un useState local à UploadPage — quitter l'onglet Import démontait
// le composant, et bien que les requêtes réseau déjà parties continuaient
// réellement côté serveur, l'utilisateur revenait sur une file vide et
// croyait (à raison, du point de vue de l'UI) que tout avait été annulé.
export function UploadQueueProvider({ children }: { children: ReactNode }) {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const { track } = usePipelineProgress();

  const updateItem = useCallback((key: string, patch: Partial<QueueItem>) => {
    setQueue((prev) => prev.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  }, []);

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const incoming: QueueItem[] = Array.from(files).map((file) => ({
      key: `${file.name}-${file.size}-${file.lastModified}-${Math.random()}`,
      file, status: "pending" as QueueStatus,
    }));
    if (incoming.length === 0) return;
    setQueue((prev) => [...prev, ...incoming]);
    setIsProcessing(true);

    await runWithConcurrency(incoming, MAX_CONCURRENT_UPLOADS, async (item) => {
      const validationError = validate(item.file);
      if (validationError) {
        updateItem(item.key, { status: "error", error: validationError });
        return;
      }
      updateItem(item.key, { status: "uploading" });
      try {
        const invoice = await uploadInvoice(item.file);
        updateItem(item.key, { status: "queued", invoiceId: invoice.id });
        track(invoice.id);
      } catch (err) {
        updateItem(item.key, { status: "error", error: apiErrorMessage(err) });
      }
    });

    setIsProcessing(false);
  }, [updateItem, track]);

  const clearFinished = useCallback(() => {
    setQueue((prev) => prev.filter((item) => item.status === "pending" || item.status === "uploading"));
  }, []);

  return (
    <UploadQueueContext.Provider value={{ queue, isProcessing, handleFiles, clearFinished }}>
      {children}
    </UploadQueueContext.Provider>
  );
}

export function useUploadQueue(): UploadQueueState {
  const ctx = useContext(UploadQueueContext);
  if (!ctx) throw new Error("useUploadQueue doit être utilisé sous UploadQueueProvider");
  return ctx;
}
