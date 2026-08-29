import type { Channel, ShopId } from "../../shared/types/common";

export type InventoryRiskCode =
  | "out_of_stock"
  | "urgent_replenishment"
  | "replenish"
  | "sufficient"
  | "overstock"
  | "no_recent_sales";
export type InventoryRiskFilter = "" | "attention" | InventoryRiskCode;
export type InventorySort = "" | "fbp" | "realfbs" | "whd" | "forecast" | "replenishment" | "days_cover" | "risk";
export type SortOrder = "asc" | "desc";

export interface InventoryChannelStock {
  channel: Channel;
  source: string;
  present: number;
  reserved: number;
  effective_stock: number;
  observed_at: string | null;
}

export interface InventoryRow {
  shop_id: ShopId;
  shop_name: string;
  sku: string;
  offer_id: string;
  product_id: string | number | null;
  product_name_raw: string;
  short_name: string;
  display_name: string;
  analysis_identity: string;
  group_id: number | null;
  primary_offer_id: string;
  offer_members: string[];
  channels: InventoryChannelStock[];
  present: number;
  reserved: number;
  sales_7: number;
  sales_15: number;
  sales_30: number;
  daily_7: number | null;
  daily_15: number | null;
  daily_30: number | null;
  forecast_daily: number;
  forecast_windows_used: number[];
  forecast_adjusted_for_stockout: boolean;
  confirmed_stockout_days_30: number;
  trend: string;
  trend_7_vs_30: number | null;
  current_stock: number;
  reserved_stock: number;
  effective_stock: number;
  days_cover: number | null;
  expected_stockout_date: string | null;
  lead_time_days: number;
  inbound_before_arrival: number;
  inbound_included: boolean;
  projected_stock_at_arrival: number | null;
  target_cover_days: number;
  target_stock_after_arrival: number;
  recommended_replenishment: number;
  stockout_before_arrival: boolean;
  shortage_days: number | null;
  risk_code: InventoryRiskCode;
  risk_status: string;
  ad_orders_30: number | null;
  ad_order_share: number | null;
  fbp_present: number;
  fbp_reserved: number;
  fbp_effective_stock: number;
  replenishment_stock_source: "FBP";
  observed_at: string | null;
}

export interface InventorySummary {
  active_skus: number;
  fbp_present: number;
  fbp_reserved: number;
  need_replenishment_skus: number;
  replenishment_skus: number;
  stockout_before_arrival_skus: number;
  shortage_skus: number;
  expected_stockout_skus: number;
  recommended_replenishment_total: number;
  effective_stock: number;
  reserved_stock: number;
  forecast_channel: "FBP";
  reference_channel: Channel;
  replenishment_stock_source: "FBP";
  inbound_included: false;
}

export interface InventoryResponse {
  summary: InventorySummary;
  items: InventoryRow[];
  total: number;
  page: number;
  size: number;
  data_through: string | null;
  sales_through: string | null;
  sales_window_end: string;
  inventory_business_date: string;
  formula: string;
}
