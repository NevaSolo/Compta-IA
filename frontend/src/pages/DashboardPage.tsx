import { useQuery } from "@tanstack/react-query";
import {
  Bar, CartesianGrid, Cell, ComposedChart, Legend, Line, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  AlertTriangle, CheckCircle2, FileText, Hourglass, Inbox, PieChart as PieChartIcon,
  TrendingUp, type LucideIcon,
} from "lucide-react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { getDashboardStats } from "@/services/invoices";
import { InvoiceList } from "@/components/InvoiceList";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { CardSkeleton, TableSkeleton } from "@/components/Skeleton";

const OPERATION_LABELS: Record<string, string> = {
  ACHAT_MARCHANDISES: "Marchandises",
  ACHAT_SERVICES: "Services",
  ACHAT_IMMOBILISATION: "Immobilisations",
  AUTRE: "Autre",
};
const OPERATION_COLORS: Record<string, string> = {
  ACHAT_MARCHANDISES: "#2563eb",
  ACHAT_SERVICES: "#10b981",
  ACHAT_IMMOBILISATION: "#f59e0b",
  AUTRE: "#94a3b8",
};

function StatCard({
  icon: Icon, label, value, accent, iconClass,
}: { icon: LucideIcon; label: string; value: string | number; accent?: string; iconClass?: string }) {
  return (
    <div className="card flex flex-col gap-2 p-4 sm:flex-row sm:items-start sm:gap-3 sm:p-5">
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 ${iconClass ?? "text-slate-500"}`}>
        <Icon size={20} strokeWidth={1.75} />
      </span>
      <div>
        <p className="text-sm text-slate-500">{label}</p>
        <p className={`mt-0.5 text-2xl font-bold tabular-nums ${accent ?? "text-slate-900"}`}>{value}</p>
      </div>
    </div>
  );
}

function formatMonth(month: string): string {
  const [year, m] = month.split("-");
  const date = new Date(Number(year), Number(m) - 1, 1);
  return date.toLocaleDateString("fr-FR", { month: "short", year: "2-digit" });
}

export function DashboardPage() {
  const isPhone = useMediaQuery("(max-width: 639px)");
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard"], queryFn: getDashboardStats,
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Tableau de bord" />
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
        <div className="card"><TableSkeleton rows={4} /></div>
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="card p-8">
        <EmptyState icon={AlertTriangle} title="Impossible de charger les statistiques"
                   hint="Vérifiez votre connexion et réessayez." />
      </div>
    );
  }

  const operationData = Object.entries(data.operations_by_type)
    .filter(([, count]) => count > 0)
    .map(([type, count]) => ({
      name: OPERATION_LABELS[type] ?? type, value: count, color: OPERATION_COLORS[type] ?? "#94a3b8",
    }));

  const monthlyData = data.monthly_volume.map((point) => ({
    ...point, label: formatMonth(point.month),
  }));

  return (
    <div className="space-y-6">
      <PageHeader title="Tableau de bord" subtitle="Vue d'ensemble du pipeline OCR → NLP → IA" />

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard icon={FileText} label="Factures totales" value={data.total_invoices} />
        <StatCard icon={Hourglass} label="À vérifier" value={data.pending_review}
                 accent="text-amber-600" iconClass="bg-amber-50 text-amber-600" />
        <StatCard icon={CheckCircle2} label="Validées" value={data.validated}
                 accent="text-emerald-600" iconClass="bg-emerald-50 text-emerald-600" />
        <StatCard icon={AlertTriangle} label="En erreur" value={data.errors}
                 accent="text-red-600" iconClass="bg-red-50 text-red-600" />
      </div>

      <div className="grid grid-cols-2 gap-3 sm:gap-4">
        <div className="card min-w-0 p-4 sm:p-5">
          <p className="text-sm text-slate-500">Taux de validation sans correction</p>
          <p className="mt-1 text-2xl font-bold text-brand-700">
            {data.validated_without_correction_rate !== null
              ? `${Math.round(data.validated_without_correction_rate * 100)} %`
              : "—"}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            Indicateur central du mémoire : progression au fil des validations.
          </p>
        </div>
        <div className="card min-w-0 p-4 sm:p-5">
          <p className="text-sm text-slate-500">Score de confiance moyen</p>
          <p className="mt-1 text-2xl font-bold text-brand-700">
            {data.average_confidence !== null
              ? `${Math.round(data.average_confidence * 100)} %`
              : "—"}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card min-w-0 p-4 sm:p-5">
          <h2 className="mb-3 font-semibold text-slate-800">Répartition par type d'opération</h2>
          {operationData.length === 0 ? (
            <EmptyState icon={PieChartIcon} title="Pas encore de facture classifiée" />
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={operationData} dataKey="value" nameKey="name" cx="50%" cy="50%"
                     innerRadius={isPhone ? 45 : 55} outerRadius={isPhone ? 70 : 85} isAnimationActive={false} paddingAngle={2}>
                  {operationData.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card min-w-0 p-4 sm:p-5">
          <h2 className="mb-3 font-semibold text-slate-800">Volume mensuel (6 derniers mois)</h2>
          {monthlyData.length === 0 ? (
            <EmptyState icon={TrendingUp} title="Pas encore de données mensuelles" />
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={monthlyData} margin={isPhone ? { left: -16, right: 0 } : undefined}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <YAxis yAxisId="left" tick={{ fontSize: 12 }} stroke="#94a3b8"
                       allowDecimals={false}
                       label={isPhone ? undefined : { value: "Factures", angle: -90, position: "insideLeft", fontSize: 11, fill: "#94a3b8" }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} stroke="#94a3b8"
                       hide={isPhone} tickFormatter={(v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(0)} M` : String(v))}
                       label={isPhone ? undefined : { value: "Total TTC", angle: 90, position: "insideRight", fontSize: 11, fill: "#94a3b8" }} />
                <Tooltip />
                <Legend />
                <Bar yAxisId="left" dataKey="invoice_count" name="Factures" fill="#2563eb" radius={[4, 4, 0, 0]} />
                <Line yAxisId="right" dataKey="total_ttc" name="Total TTC" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3 }} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="border-b border-slate-100 px-5 py-3">
          <h2 className="font-semibold text-slate-800">Factures récentes</h2>
        </div>
        {data.recent_invoices.length === 0 ? (
          <EmptyState icon={Inbox} title="Aucune facture importée pour le moment"
                     hint="Commencez par importer une facture depuis l'onglet Importer." />
        ) : (
          <InvoiceList invoices={data.recent_invoices} />
        )}
      </div>
    </div>
  );
}
