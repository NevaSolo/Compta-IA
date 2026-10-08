import { api } from "./api";
import type {
  AuditLogEntry, ModelVersion, Paginated, RetrainReport, Role, User,
} from "@/types";

export async function listUsers(): Promise<User[]> {
  const { data } = await api.get<User[]>("/auth/users");
  return data;
}

export async function createUser(payload: {
  email: string; password: string; full_name: string; role: Role;
  company_id?: number | null;
}): Promise<User> {
  const { data } = await api.post<User>("/auth/users", payload);
  return data;
}

export async function setUserActive(userId: number, isActive: boolean): Promise<User> {
  const { data } = await api.patch<User>(`/auth/users/${userId}/active`, { is_active: isActive });
  return data;
}

export async function getAuditLog(page = 1, size = 30): Promise<Paginated<AuditLogEntry>> {
  const { data } = await api.get("/audit", { params: { page, size } });
  return { items: data.items, total: data.total, page: data.page, size: data.size };
}

export async function listModelVersions(): Promise<ModelVersion[]> {
  const { data } = await api.get<ModelVersion[]>("/ml/versions");
  return data;
}

export async function retrainModel(): Promise<RetrainReport> {
  const { data } = await api.post<RetrainReport>("/ml/retrain");
  return data;
}
