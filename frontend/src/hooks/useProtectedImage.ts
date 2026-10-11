import { useEffect, useState } from "react";

// Les images de profil/logo sont protégées par JWT : une balise <img> ne peut
// pas envoyer l'en-tête Authorization, on les récupère donc en Blob. Le cache
// (clé = ressource + version du fichier) évite de les retélécharger à chaque
// affichage ; une nouvelle version (nouveau fichier) change la clé.
const cache = new Map<string, string>();

export function useProtectedImage(
  key: string | null, version: number | null | undefined, fetcher: () => Promise<Blob>,
): string | null {
  const cacheKey = key && version ? `${key}:${version}` : null;
  const [url, setUrl] = useState<string | null>(cacheKey ? cache.get(cacheKey) ?? null : null);

  useEffect(() => {
    if (!cacheKey) { setUrl(null); return; }
    const hit = cache.get(cacheKey);
    if (hit) { setUrl(hit); return; }
    let cancelled = false;
    fetcher()
      .then((blob) => {
        const objectUrl = URL.createObjectURL(blob);
        cache.set(cacheKey, objectUrl);
        if (!cancelled) setUrl(objectUrl);
      })
      .catch(() => { if (!cancelled) setUrl(null); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey]);

  return url;
}
