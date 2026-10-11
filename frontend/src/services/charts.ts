import { api } from "./api";
import type { Chart, Company } from "@/types";

export async function listCharts(): Promise<Chart[]> {
  const { data } = await api.get<Chart[]>("/charts");
  return data;
}

export async function chooseChart(companyId: number, chartId: number): Promise<Company> {
  const { data } = await api.put<Company>(`/companies/${companyId}/chart`, { chart_id: chartId });
  return data;
}
