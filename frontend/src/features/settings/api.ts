import { request } from "../../shared/api/client";
import type { OzonProbeResponse } from "./types";
import type { ShopId } from "../../shared/types/common";

export function probeShop(shopId: ShopId): Promise<OzonProbeResponse> {
  return request<OzonProbeResponse>(`/api/ozon/probe/${shopId}`, { method: "POST" });
}
