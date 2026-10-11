import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { applyTheme, loadStoredTheme, watchSystemTheme } from "@/theme";
import type { User } from "@/types";
import { fetchMe, login as loginRequest } from "@/services/auth";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  /** Remplace le profil courant (après une modification du profil ou de l'entreprise). */
  setUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setIsLoading(false);
      return;
    }
    fetchMe()
      .then(setUser)
      .catch(() => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("user");
      })
      .finally(() => setIsLoading(false));
  }, []);

  // Thème et couleur d'accent : ceux du profil une fois connecté, sinon ceux
  // mémorisés sur cet appareil (page de connexion).
  useEffect(() => {
    const stored = loadStoredTheme();
    const mode = user?.theme ?? stored.mode;
    const accent = user?.accent ?? stored.accent;
    applyTheme(mode, accent);
    return watchSystemTheme(mode, accent);
  }, [user?.theme, user?.accent]);

  async function login(email: string, password: string) {
    const response = await loginRequest(email, password);
    localStorage.setItem("access_token", response.access_token);
    // La réponse de connexion ne contient ni l'entreprise ni la personnalisation :
    // on charge le profil complet.
    setUser(await fetchMe());
  }

  function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth doit être utilisé dans un AuthProvider");
  return context;
}
