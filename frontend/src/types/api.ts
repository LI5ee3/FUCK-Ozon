export type ShopId = 1 | 2;
export type ShopSelection = 0 | ShopId;
export type Granularity = "day" | "week" | "month";
export type Channel = "FBP" | "realFBS" | "WHD";
export type OrderStatusFilter = "" | "pending" | "shipping" | "delivered" | "cancelled";

export interface SessionResponse {
  authenticated: boolean;
  csrf_token: string;
}

export interface LoginResponse {
  ok: boolean;
}

export interface Shop {
  id: ShopId;
  name: string;
}

export interface OkResponse {
  ok: boolean;
}

export interface GmvSummary {
  amount: number;
  currency: string;
  missing_rate_orders: number;
}

export interface OverviewTotals {
  orders: number;
  pieces: number;
  cancelled_orders: number;
  cancelled_pieces: number;
  cancel_rate: number;
}

export interface OverviewChannel {
  channel: Channel;
  orders: number;
  pieces: number;
  cancelled_pieces: number;
}

export interface TimelinessOverview {
  channel: Channel;
  ship_samples: number;
  delivery_samples: number;
  p50_ship_hours: number | null;
  p50_delivery_hours: number | null;
  p90_delivery_hours: number | null;
  ship_sample_insufficient: boolean;
  delivery_sample_insufficient: boolean;
}

export interface TimelinessSummary {
  orders: number;
  shipped_orders: number;
  delivered_orders: number;
  ship_samples: number;
  delivery_samples: number;
  avg_ship_hours: number | null;
  p50_ship_hours: number | null;
  p90_ship_hours: number | null;
  avg_delivery_hours: number | null;
  p50_delivery_hours: number | null;
  p90_delivery_hours: number | null;
}

export interface TimelinessGroup {
  shop_id: ShopId;
  shop_name: string;
  channel: Channel;
  orders: number;
  created: number;
  shipped: number;
  delivered: number;
  ship_samples: number;
  delivery_samples: number;
  ship_sample_insufficient: boolean;
  delivery_sample_insufficient: boolean;
  avg_ship_hours: number | null;
  p50_ship_hours: number | null;
  p90_ship_hours: number | null;
  avg_delivery_hours: number | null;
  p50_delivery_hours: number | null;
  p90_delivery_hours: number | null;
  created_completeness: number;
  shipped_completeness: number;
  delivered_completeness: number;
}

export interface TimelinessItem {
  shop_id: ShopId;
  shop_name: string;
  posting_number: string;
  channel: Channel;
  created_at: string;
  shipped_at: string | null;
  delivered_at: string | null;
  ship_hours: number | null;
  delivery_hours: number | null;
  ship_anomaly: boolean;
  delivery_anomaly: boolean;
}

export interface TimelinessResponse {
  range: { from: string; to: string };
  summary: TimelinessSummary;
  items: TimelinessItem[];
  total: number;
  page: number;
  size: number;
  groups: TimelinessGroup[];
  data_through: string | null;
}

export interface TopProduct {
  name: string;
  pieces: number;
  orders: number;
  cancel_rate: number;
}

export interface TrendChannelValue {
  orders: number;
  gmv: GmvSummary;
}

export type TrendChannels = Record<Channel, TrendChannelValue>;

export interface TrendBucket {
  key: string;
  from: string;
  to: string;
  orders: number;
  gmv: GmvSummary;
  channels: TrendChannels;
}

export interface DashboardSummary {
  range: { from: string; to: string };
  granularity: Granularity;
  totals: OverviewTotals;
  channels: OverviewChannel[];
  buckets: TrendBucket[];
  gmv: GmvSummary;
  timeliness: TimelinessOverview[];
  top_products: TopProduct[];
  data_through: string | null;
}

export interface OrderTrend {
  granularity: Granularity;
  from: string;
  to: string;
  buckets: TrendBucket[];
}

export interface OrderItem {
  shop_id: ShopId;
  posting_number: string;
  sku: string | null;
  offer_id: string | null;
  product_name_raw: string | null;
  product_name_original: string | null;
  quantity: number;
  unit_price: number | null;
  price_currency: string | null;
}

export interface Order {
  shop_id: ShopId;
  shop_name: string;
  posting_number: string;
  channel: Channel;
  created_at: string;
  shipped_at: string | null;
  delivered_at: string | null;
  status_raw: string;
  cancel_reason_raw: string | null;
  shipped: number;
  data_anomaly: number;
  amount_original: number | null;
  amount_currency: string | null;
  items: OrderItem[];
  sku_types: number;
  pieces: number;
}

export interface OrderStatusCounts {
  all: number;
  pending: number;
  shipping: number;
  delivered: number;
  cancelled: number;
  cancelled_shipped: number;
  anomaly: number;
}

export interface OrderListResponse {
  items: Order[];
  total: number;
  page: number;
  size: number;
  status_counts: OrderStatusCounts;
}

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

export interface AnalyticsPagedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  data_through: string;
}

export interface AnalyticsTrafficShopSummary {
  shop_id: ShopId;
  shop_name: string;
  impressions: number;
  product_views: number;
  cart_adds: number;
  unique_visitors: number;
  ordered_units: number;
  revenue: number;
  currency: string;
}

export interface AnalyticsTrafficRow extends AnalyticsTrafficShopSummary {
  sku: string;
  name: string;
  view_rate: number | null;
  cart_rate: number | null;
  order_rate: number | null;
}

export interface AnalyticsDataResponse extends AnalyticsPagedResponse<AnalyticsTrafficRow> {
  shops: AnalyticsTrafficShopSummary[];
}

export interface AnalyticsProductQueryRow {
  shop_id: ShopId;
  shop_name: string;
  sku: string;
  name: string;
  offer_id: string;
  category: string;
  position: number | null;
  unique_search_users: number | null;
  unique_view_users: number | null;
  view_conversion: number | null;
  gmv: number | null;
  currency: string;
}

export type AnalyticsProductQueryResponse = AnalyticsPagedResponse<AnalyticsProductQueryRow>;

export interface AnalyticsProductQueryDetailRow {
  shop_id: ShopId;
  shop_name: string;
  sku: string;
  query: string;
  position: number | null;
  unique_search_users: number | null;
  unique_view_users: number | null;
  view_conversion: number | null;
  order_count: number | null;
  gmv: number | null;
  currency: string;
}

export type AnalyticsProductQueryDetailResponse = AnalyticsPagedResponse<AnalyticsProductQueryDetailRow>;
