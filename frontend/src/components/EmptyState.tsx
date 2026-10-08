import { FileQuestion, type LucideIcon } from "lucide-react";

/** État vide standardisé (aucun résultat, aucune écriture…) — remplace les
 * simples lignes de texte gris dispersées dans chaque page. */
export function EmptyState({
  icon: Icon = FileQuestion, title, hint,
}: { icon?: LucideIcon; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 px-5 py-12 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
        <Icon size={22} strokeWidth={1.75} />
      </span>
      <p className="mt-2 font-medium text-slate-600">{title}</p>
      {hint && <p className="text-sm text-slate-400">{hint}</p>}
    </div>
  );
}
