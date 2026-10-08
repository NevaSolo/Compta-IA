import { api } from "./api";
import type { Account } from "@/types";

export async function listAccounts(): Promise<Account[]> {
  const { data } = await api.get<Account[]>("/accounts");
  return data;
}
