import { request } from "./client";
import type { OzonProbeResponse, ShopId } from "../types/api";

export function probeShop(shopId: ShopId): Promise<OzonProbeResponse> {
  return request<OzonProbeResponse>(`/api/ozon/probe/${shopId}`, { method: "POST" });
}
