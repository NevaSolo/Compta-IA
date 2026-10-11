/** Nombre à la française : espaces pour les milliers, virgule décimale, sans
 * décimales inutiles (4950 → « 4 950 », 4950.5 → « 4 950,5 »). */
export function formatNumber(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 6 }).format(number);
}

/** Montant à la française, toujours 2 décimales : 2750000 → « 2 750 000,00 ».
 * Réservé à l'affichage : les champs de saisie et les exports gardent le nombre brut. */
export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  return new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(number);
}
