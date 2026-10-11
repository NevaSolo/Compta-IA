export type ThemeMode = "auto" | "light" | "dark";
export type Accent = "blue" | "emerald" | "violet" | "rose" | "amber" | "slate";

export const ACCENTS: { value: Accent; label: string; swatch: string }[] = [
  { value: "blue", label: "Bleu", swatch: "#2563eb" },
  { value: "emerald", label: "Émeraude", swatch: "#059669" },
  { value: "violet", label: "Violet", swatch: "#7c3aed" },
  { value: "rose", label: "Rose", swatch: "#e11d48" },
  { value: "amber", label: "Ambre", swatch: "#d97706" },
  { value: "slate", label: "Ardoise", swatch: "#475569" },
];

const STORAGE_KEY = "ui_prefs";
const DARK_QUERY = "(prefers-color-scheme: dark)";

function isDark(mode: ThemeMode): boolean {
  return mode === "dark" || (mode === "auto" && window.matchMedia(DARK_QUERY).matches);
}

/** Applique thème + accent sur <html>. Mémorisé localement pour que la page
 * de connexion (avant tout appel API) et le premier affichage ne clignotent
 * pas ; la référence reste le profil enregistré côté serveur. */
export function applyTheme(mode: ThemeMode, accent: Accent): void {
  const root = document.documentElement;
  root.classList.toggle("dark", isDark(mode));
  root.dataset.accent = accent;
  const brand = getComputedStyle(root).getPropertyValue("--brand-600").trim().split(" ")
    .reduce((hex, v) => hex + Number(v).toString(16).padStart(2, "0"), "#");
  document.querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", isDark(mode) ? "#0b1220" : brand.length === 7 ? brand : "#2563eb");
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ mode, accent }));
  } catch { /* stockage indisponible : sans conséquence */ }
}

export function loadStoredTheme(): { mode: ThemeMode; accent: Accent } {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    if (raw && ["auto", "light", "dark"].includes(raw.mode) && ACCENTS.some((a) => a.value === raw.accent)) {
      return raw;
    }
  } catch { /* valeur corrompue : on retombe sur le défaut */ }
  return { mode: "auto", accent: "blue" };
}

/** En mode « auto », suit le réglage du système en direct. */
export function watchSystemTheme(mode: ThemeMode, accent: Accent): () => void {
  if (mode !== "auto") return () => undefined;
  const query = window.matchMedia(DARK_QUERY);
  const onChange = () => applyTheme("auto", accent);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
