import { useEffect, useState } from "react";

/** Suit une media query CSS (ex. "(max-width: 767px)") — utile pour les
 * composants non stylables en CSS pur, comme les graphiques Recharts. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}
