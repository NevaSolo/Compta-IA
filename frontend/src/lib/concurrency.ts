/** Exécute `worker` sur chaque élément de `items` avec au plus `limit`
 * exécutions simultanées. Utilisé pour l'import de plusieurs factures à la
 * fois : évite de saturer le navigateur (et le pipeline IA côté serveur)
 * en envoyant toutes les requêtes d'un coup, sans pour autant les envoyer
 * une par une. Ne rejette jamais globalement : chaque échec est capturé
 * par l'appelant via son propre worker (voir UploadPage). */
export async function runWithConcurrency<T>(
  items: T[], limit: number, worker: (item: T, index: number) => Promise<void>
): Promise<void> {
  let cursor = 0;
  async function runNext(): Promise<void> {
    const index = cursor++;
    if (index >= items.length) return;
    await worker(items[index], index);
    return runNext();
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, runNext));
}
