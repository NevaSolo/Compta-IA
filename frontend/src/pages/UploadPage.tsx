import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { UploadCloud } from "lucide-react";
import { useUploadQueue, type QueueStatus } from "@/context/UploadQueueContext";
import { PageHeader } from "@/components/PageHeader";

const ACCEPTED_TYPES = ["application/pdf", "image/jpeg", "image/png"];
const MAX_SIZE_MB = 15; // reflète app.core.config.Settings.max_upload_size_mb

const STATUS_LABEL: Record<QueueStatus, string> = {
  pending: "En attente", uploading: "Envoi…", queued: "Pipeline lancé", error: "Erreur",
};
const STATUS_STYLE: Record<QueueStatus, string> = {
  pending: "bg-slate-100 text-slate-600",
  uploading: "bg-blue-100 text-blue-700",
  queued: "bg-emerald-100 text-emerald-800",
  error: "bg-red-100 text-red-700",
};

export function UploadPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  // La file (queue) et son traitement vivent dans UploadQueueContext, monté
  // au-dessus des routes : quitter cet onglet puis y revenir ne perd donc
  // plus le suivi des imports en cours (le composant se remonte, mais pas
  // l'état ni les requêtes réseau qu'il contenait avant ce fix).
  const { queue, isProcessing, handleFiles, clearFinished } = useUploadQueue();

  const queuedCount = queue.filter((i) => i.status === "queued").length;
  const errorCount = queue.filter((i) => i.status === "error").length;
  const hasFinished = queue.some((i) => i.status === "queued" || i.status === "error");

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <PageHeader
        title="Importer des factures"
        subtitle="Déposez une ou plusieurs factures fournisseurs (PDF, JPG ou PNG). Le pipeline OCR + NLP + IA se lance automatiquement pour chacune, en parallèle — le suivi reste actif même si vous changez d'onglet."
      />

      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-14 text-center transition-colors ${
          isDragging ? "border-brand-500 bg-brand-50" : "border-slate-300 bg-white hover:border-brand-400"
        }`}
      >
        <UploadCloud size={30} className="mb-2 text-slate-400" strokeWidth={1.5} />
        <p className="font-medium text-slate-700">
          {isProcessing ? "Import en cours…" : "Cliquez ou glissez-déposez une ou plusieurs factures ici"}
        </p>
        <p className="mt-1 text-xs text-slate-400">PDF, JPG, PNG — {MAX_SIZE_MB} Mo maximum par fichier</p>
        <input
          ref={inputRef} type="file" accept={ACCEPTED_TYPES.join(",")} multiple hidden
          onChange={(e) => { if (e.target.files?.length) handleFiles(e.target.files); e.target.value = ""; }}
        />
      </div>

      {queue.length > 0 && (
        <div className="card overflow-hidden animate-fade-in">
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-4 py-2 text-sm text-slate-600">
            <span>{queue.length} fichier(s) — {queuedCount} lancé(s){errorCount > 0 && `, ${errorCount} en erreur`}</span>
            {hasFinished && (
              <button
                type="button"
                onClick={clearFinished}
                className="text-xs font-medium text-slate-500 hover:text-slate-700 hover:underline"
              >
                Effacer les terminés
              </button>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <tbody>
                {queue.map((item) => (
                  <tr key={item.key} className="border-t border-slate-100">
                    <td className="px-4 py-2 text-slate-700">{item.file.name}</td>
                    <td className="px-4 py-2 text-slate-400 whitespace-nowrap">
                      {(item.file.size / 1024 / 1024).toFixed(2)} Mo
                    </td>
                    <td className="px-4 py-2">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLE[item.status]}`}>
                        {STATUS_LABEL[item.status]}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      {item.status === "queued" && item.invoiceId && (
                        <Link to={`/factures/${item.invoiceId}`} className="text-brand-700 hover:underline">
                          Voir la facture
                        </Link>
                      )}
                      {item.status === "error" && (
                        <span className="text-xs text-red-600">{item.error}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
