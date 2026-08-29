import { request, requestJson } from "../../shared/api/client";
import type { LoginResponse, SessionResponse } from "./types";
import type { OkResponse } from "../../shared/types/common";

export function getSession(): Promise<SessionResponse> {
  return request<SessionResponse>("/api/session");
}

export function login(password: string): Promise<LoginResponse> {
  return requestJson<LoginResponse>("/api/login", "POST", { password });
}

export function logout(): Promise<OkResponse> {
  return request<OkResponse>("/api/logout", { method: "POST" });
}
