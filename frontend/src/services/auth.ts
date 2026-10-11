import { api } from "./api";
import type { TokenResponse, User } from "@/types";

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/auth/login", { email, password });
  return data;
}

export async function fetchMe(): Promise<User> {
  const { data } = await api.get<User>("/auth/me");
  return data;
}

import type { Accent, ThemeMode } from "@/theme";

export interface ProfileUpdate {
  full_name?: string;
  theme?: ThemeMode;
  accent?: Accent;
}

export async function updateProfile(payload: ProfileUpdate): Promise<User> {
  const { data } = await api.patch<User>("/auth/me/profile", payload);
  return data;
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await api.post("/auth/me/password", { current_password: currentPassword, new_password: newPassword });
}

export async function uploadAvatar(file: Blob): Promise<User> {
  const form = new FormData();
  form.append("file", file, "avatar.png");
  const { data } = await api.put<User>("/auth/me/avatar", form);
  return data;
}

export async function deleteAvatar(): Promise<User> {
  const { data } = await api.delete<User>("/auth/me/avatar");
  return data;
}

export async function fetchAvatarBlob(): Promise<Blob> {
  const { data } = await api.get("/auth/me/avatar", { responseType: "blob" });
  return data;
}
