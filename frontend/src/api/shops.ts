import { request, requestJson } from "./client";
import type { OkResponse, Shop } from "../types/api";

export function listShops(): Promise<Shop[]> {
  return request<Shop[]>("/api/shops");
}

export function updateShops(names: { 1: string; 2: string }): Promise<OkResponse> {
  return requestJson<OkResponse>("/api/shops", "PUT", names);
}
