import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Wallet } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { apiErrorMessage } from "@/services/api";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 via-slate-50 to-slate-100 px-4">
      <div className="w-full max-w-sm animate-slide-up card p-8">
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 text-white shadow-sm">
            <Wallet size={24} />
          </span>
          <h1 className="text-xl font-bold text-slate-900">Compta-IA</h1>
          <p className="mt-1 text-sm text-slate-500">
            Génération automatique des écritures comptables
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
            <input
              type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input"
              placeholder="comptable@compta-ia.mg"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Mot de passe</label>
            <input
              type="password" required value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
            />
          </div>
          {error && (
            <p className="animate-fade-in rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
          )}
          <button
            type="submit" disabled={isSubmitting}
            className="btn-primary w-full py-2"
          >
            {isSubmitting ? "Connexion…" : "Se connecter"}
          </button>
        </form>
      </div>
    </div>
  );
}
