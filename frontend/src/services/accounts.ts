import { api } from "./api";
import type { Account } from "@/types";

/** Comptes du plan comptable de l'entreprise (celle de l'utilisateur, ou celle
 * de la facture consultée par un administrateur plateforme). */
export async function listAccounts(companyId?: number | null): Promise<Account[]> {
  const { data } = await api.get<Account[]>("/accounts", {
    params: companyId ? { company_id: companyId } : undefined,
  });
  return data;
}
