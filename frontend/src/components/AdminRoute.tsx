import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

/** Garde de route réservée aux rôles ADMIN et ENTREPRISE_ADMIN — un
 * COMPTABLE authentifié qui tente d'accéder à /admin est redirigé plutôt
 * que de voir une 403 brute. La portée exacte (toutes entreprises vs la
 * sienne) est ensuite tranchée dans AdminPage selon le rôle précis. */
export function AdminRoute() {
  const { user } = useAuth();
  if (user?.role !== "ADMIN" && user?.role !== "ENTREPRISE_ADMIN") {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
