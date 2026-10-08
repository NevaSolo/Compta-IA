// Seuils validés en Phase 6 : >=0.80 vert, 0.50-0.80 orange, <0.50 rouge.
export function ConfidenceBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) {
    return <span className="text-xs text-slate-400">—</span>;
  }
  const pct = Math.round(score * 100);
  const style =
    score >= 0.8 ? "bg-emerald-100 text-emerald-800"
    : score >= 0.5 ? "bg-amber-100 text-amber-800"
    : "bg-red-100 text-red-700";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${style}`}>
      {pct}%
    </span>
  );
}
