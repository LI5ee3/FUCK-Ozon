import type { ShopId, ShopSelection } from "../../shared/types/common";

export interface AdsSummary {
  impressions: number;
  clicks: number;
  cart_adds: number;
  spend_rub: number;
  orders: number;
  revenue_rub: number;
  ctr: number | null;
  avg_cpc_rub: number | null;
  drr: number | null;
  roas: number | null;
}

export interface AdsTrendPoint extends AdsSummary {
  date: string;
}

export interface AdsShopSummary extends AdsSummary {
  shop_id: ShopId;
  shop_name: string;
}

export interface AdsOverviewResponse extends AdsSummary {
  shop_id: ShopSelection;
  date_from: string;
  date_to: string;
  summary: AdsSummary;
  trend: AdsTrendPoint[];
  shops: AdsShopSummary[];
  data_through: string | null;
}

export type AdCampaignState =
  | ""
  | "CAMPAIGN_STATE_RUNNING"
  | "CAMPAIGN_STATE_INACTIVE"
  | "CAMPAIGN_STATE_ARCHIVED"
  | "CAMPAIGN_STATE_STOPPED";

export type AdCampaignSort =
  | "spend_rub"
  | "revenue_rub"
  | "orders"
  | "drr"
  | "roas"
  | "impressions"
  | "clicks";

export interface AdCampaignItem extends AdsSummary {
  shop_id: ShopId;
  shop_name: string;
  campaign_id: string;
  name: string;
  state: string;
  payment_type: string | null;
  adv_object_type: string | null;
  placement: string | null;
  weekly_budget: number | null;
  data_through: string | null;
}

export interface AdCampaignStatsResponse {
  items: AdCampaignItem[];
  total: number;
  page: number;
  size: number;
  date_from: string;
  date_to: string;
  data_through: string | null;
}

export type AdSkuSort = "spend_rub" | "revenue_rub" | "drr" | "roas" | "orders" | "clicks";

export interface AdSkuItem extends AdsSummary {
  shop_id: ShopId;
  shop_name: string;
  sku: string;
  product_name: string | null;
  campaign_count: number;
  data_through: string | null;
}

export interface AdSkuStatsResponse {
  items: AdSkuItem[];
  total: number;
  page: number;
  size: number;
  date_from: string;
  date_to: string;
  data_through: string | null;
}
