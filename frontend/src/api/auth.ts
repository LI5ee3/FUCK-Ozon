import { request, requestJson } from "./client";
import type { LoginResponse, OkResponse, SessionResponse } from "../types/api";

export function getSession(): Promise<SessionResponse> {
  return request<SessionResponse>("/api/session");
}

export function login(password: string): Promise<LoginResponse> {
  return requestJson<LoginResponse>("/api/login", "POST", { password });
}

export function logout(): Promise<OkResponse> {
  return request<OkResponse>("/api/logout", { method: "POST" });
}
