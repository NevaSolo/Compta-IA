/** Bloc de chargement animé — remplace les "Chargement…" en texte brut par
 * un aperçu de la forme du contenu à venir (meilleure perception de vitesse). */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200 ${className}`} />;
}

export function CardSkeleton() {
  return (
    <div className="card space-y-3 p-5">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-7 w-16" />
    </div>
  );
}

export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-3 p-5">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-4 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}
