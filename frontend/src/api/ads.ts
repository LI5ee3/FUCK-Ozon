import { request } from "./client";
import type { AdsOverviewResponse, ShopSelection } from "../types/api";

export function getAdsOverview(shopId: ShopSelection, from: string, to: string): Promise<AdsOverviewResponse> {
  const query = new URLSearchParams({ shop_id: String(shopId), from, to });
  return request<AdsOverviewResponse>(`/api/performance/overview?${query}`);
}
