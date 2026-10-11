/** Nombre à la française : espaces pour les milliers, virgule décimale, sans
 * décimales inutiles (4950 → « 4 950 », 4950.5 → « 4 950,5 »). */
export function formatNumber(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 6 }).format(number);
}
