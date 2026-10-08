import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export function ProtectedRoute() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return <p className="flex min-h-screen items-center justify-center text-slate-500">Chargement…</p>;
  }
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}
