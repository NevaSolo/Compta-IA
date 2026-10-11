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

export async function uploadCompanyLogo(companyId: number, file: Blob): Promise<Company> {
  const form = new FormData();
  form.append("file", file, "logo.png");
  const { data } = await api.put<Company>(`/companies/${companyId}/logo`, form);
  return data;
}

export async function deleteCompanyLogo(companyId: number): Promise<Company> {
  const { data } = await api.delete<Company>(`/companies/${companyId}/logo`);
  return data;
}

export async function renameCompany(companyId: number, name: string): Promise<Company> {
  const { data } = await api.patch<Company>(`/companies/${companyId}/branding`, { name });
  return data;
}

export async function fetchCompanyLogoBlob(companyId: number): Promise<Blob> {
  const { data } = await api.get(`/companies/${companyId}/logo`, { responseType: "blob" });
  return data;
}

import type { ExchangeRate } from "@/types";

export const CURRENCIES = ["MGA", "EUR", "USD", "GBP", "CHF"] as const;

export async function setBaseCurrency(companyId: number, baseCurrency: string): Promise<Company> {
  const { data } = await api.patch<Company>(`/companies/${companyId}/currency`, { base_currency: baseCurrency });
  return data;
}

export async function listRates(companyId: number): Promise<ExchangeRate[]> {
  const { data } = await api.get<ExchangeRate[]>(`/companies/${companyId}/rates`);
  return data;
}

export async function saveRate(
  companyId: number, payload: { currency: string; rate: string; effective_date: string },
): Promise<ExchangeRate> {
  const { data } = await api.post<ExchangeRate>(`/companies/${companyId}/rates`, payload);
  return data;
}

export async function deleteRate(companyId: number, rateId: number): Promise<void> {
  await api.delete(`/companies/${companyId}/rates/${rateId}`);
}
