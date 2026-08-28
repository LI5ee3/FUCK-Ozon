import { request } from "./client";
import type {
  AdCampaignSort,
  AdCampaignState,
  AdCampaignStatsResponse,
  AdsOverviewResponse,
  ShopSelection,
} from "../types/api";

export interface AdCampaignStatsQuery {
  shopId: ShopSelection;
  from: string;
  to: string;
  state: AdCampaignState;
  sort: AdCampaignSort;
  page: number;
  size: number;
}

export function getAdsOverview(shopId: ShopSelection, from: string, to: string): Promise<AdsOverviewResponse> {
  const query = new URLSearchParams({ shop_id: String(shopId), from, to });
  return request<AdsOverviewResponse>(`/api/performance/overview?${query}`);
}

export function getAdCampaignStats(values: AdCampaignStatsQuery): Promise<AdCampaignStatsResponse> {
  const query = new URLSearchParams({
    shop_id: String(values.shopId),
    from: values.from,
    to: values.to,
    state: values.state,
    sort: values.sort,
    order: "desc",
    page: String(values.page),
    size: String(values.size),
  });
  return request<AdCampaignStatsResponse>(`/api/performance/campaign-stats?${query}`);
}
