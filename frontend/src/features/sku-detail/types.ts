import type { AdsSummary, AdsTrendPoint } from "../advertising/types";
import type { AnalyticsProductQueryDetailResponse, AnalyticsTrafficRow } from "../analytics/types";
import type { Channel, ShopId } from "../../shared/types/common";

export interface SkuIdentity {
  shop_id: ShopId;
  shop_name: string;
  sku: string;
  offer_id: string;
  display_name: string;
  product_name_raw: string;
  group_id: number | null;
  primary_offer_id: string | null;
}

export interface SkuSalesSummary {
  orders: number;
  units: number;
  revenue: number | null;
  currency: string | null;
  revenue_complete: boolean;
  avg_units_per_day: number | null;
  sales_7: number;
  sales_15: number;
  sales_30: number;
  period_days: number;
}

export interface SkuSalesPoint {
  date: string;
  orders: number;
  units: number;
  revenue: number | null;
  currency: string | null;
  revenue_complete: boolean;
}

export interface SkuSalesChannel {
  channel: Channel;
  orders: number;
  units: number;
  revenue: number | null;
  currency: string | null;
  revenue_complete: boolean;
}

export interface SkuSales {
  status: "available" | "empty";
  summary: SkuSalesSummary;
  channels: SkuSalesChannel[];
  trend: SkuSalesPoint[];
  data_through: string | null;
}

export interface SkuInventoryChannel {
  channel: Channel;
  source: string | null;
  present: number | null;
  reserved: number | null;
  effective_stock: number | null;
  observed_at: string | null;
}

export type SkuInventoryRiskCode =
  | "out_of_stock"
  | "urgent_replenishment"
  | "replenish"
  | "sufficient"
  | "overstock"
  | "no_recent_sales";

export interface SkuInventory {
  status: "available" | "unavailable";
  channels: SkuInventoryChannel[];
  fbp_present: number | null;
  fbp_reserved: number | null;
  realfbs_present: number | null;
  realfbs_reserved: number | null;
  whd_present: number | null;
  whd_reserved: number | null;
  sales_7: number | null;
  sales_15: number | null;
  sales_30: number | null;
  daily_7: number | null;
  daily_15: number | null;
  daily_30: number | null;
  forecast_daily: number | null;
  trend: string | null;
  trend_7_vs_30: number | null;
  days_cover: number | null;
  expected_stockout_date: string | null;
  lead_time_days: number;
  target_cover_days: number;
  recommended_replenishment: number | null;
  risk_code: SkuInventoryRiskCode | null;
  risk_status: string | null;
  projected_stock_at_arrival?: number | null;
  inbound_included?: boolean;
  data_through: string | null;
}

export interface SkuAdvertisingSummary extends AdsSummary {
  campaign_count: number;
  currency: "RUB";
}

export interface SkuAdvertising {
  status: "available" | "empty";
  summary: SkuAdvertisingSummary;
  trend: AdsTrendPoint[];
  currency: "RUB";
  ad_order_share: number | null;
  data_through: string | null;
}

export interface CancelReasonCount {
  reason: string;
  count: number;
}

export interface SkuAfterSales {
  status: "available" | "empty";
  orders: number;
  cancelled_before_ship: number;
  cancel_rate: number | null;
  returns: number;
  return_orders: number;
  return_rate: number | null;
  complaints: number;
  complaint_orders: number;
  complaint_rate: number | null;
  cancel_reasons: CancelReasonCount[];
  completeness: Record<string, string>;
}

export interface SkuProfit {
  status: "complete" | "incomplete" | "unavailable";
  candidate_orders: number;
  attributed_orders: number;
  unattributed_multi_sku_orders: number;
  incomplete_orders: number;
  actual_profit_cny: string | null;
  avg_profit_per_unit_cny: string | null;
  units: number;
  currency: "CNY";
  incomplete_reasons: Record<string, number>;
}

export type SignalSeverity = "critical" | "warning" | "info" | "positive";

export interface BusinessSignal {
  code: string;
  severity: SignalSeverity;
  title: string;
  message: string;
  metrics: Record<string, number | string | null>;
}

export interface SkuFreshness {
  orders: string | null;
  inventory: string | null;
  advertising: string | null;
  finance: string | null;
  erp_cost: string | null;
}

export interface SkuDetailResponse {
  identity: SkuIdentity;
  period: { from: string; to: string };
  sales: SkuSales;
  inventory: SkuInventory;
  advertising: SkuAdvertising;
  after_sales: SkuAfterSales;
  profit: SkuProfit;
  signals: BusinessSignal[];
  freshness: SkuFreshness;
}

export type AnalyticsTraffic = AnalyticsTrafficRow;
export type AnalyticsQueries = AnalyticsProductQueryDetailResponse;
