import { api } from "./api";
import type { Company } from "@/types";

export async function listCompanies(): Promise<Company[]> {
  const { data } = await api.get<Company[]>("/companies");
  return data;
}

export async function createCompany(payload: {
  name: string; nif?: string | null; stat?: string | null; address?: string | null;
}): Promise<Company> {
  const { data } = await api.post<Company>("/companies", payload);
  return data;
}

export async function setCompanyActive(companyId: number, isActive: boolean): Promise<Company> {
  const { data } = await api.patch<Company>(
    `/companies/${companyId}/active`, { is_active: isActive });
  return data;
}
