import { apiClient } from "./client";

export type UserResponse = {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  created_at: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserResponse;
};

export const authApi = {
  register: (payload: { email: string; display_name: string; password: string }) =>
    apiClient.request<UserResponse>("/api/v1/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  login: (payload: { email: string; password: string }) =>
    apiClient.request<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  me: (accessToken: string) =>
    apiClient.get<UserResponse>("/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${accessToken}` },
    }),
};