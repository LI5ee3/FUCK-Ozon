import { request } from "../../shared/api/client";
import type {
  AdCampaignSort,
  AdCampaignState,
  AdCampaignStatsResponse,
  AdSkuSort,
  AdSkuStatsResponse,
  AdsOverviewResponse,
} from "./types";
import type { ShopSelection } from "../../shared/types/common";

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

export interface AdSkuStatsQuery {
  shopId: ShopSelection;
  q: string;
  from: string;
  to: string;
  sort: AdSkuSort;
  page: number;
  size: number;
}

export function getAdSkuStats(values: AdSkuStatsQuery): Promise<AdSkuStatsResponse> {
  const query = new URLSearchParams({
    shop_id: String(values.shopId),
    from: values.from,
    to: values.to,
    q: values.q,
    sort: values.sort,
    order: "desc",
    page: String(values.page),
    size: String(values.size),
  });
  return request<AdSkuStatsResponse>(`/api/performance/sku-stats?${query}`);
}
