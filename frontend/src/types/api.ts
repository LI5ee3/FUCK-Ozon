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

export type PushEventType = string;

export interface PushSubscription {
  id: number | string | null;
  url: string;
  enabled: boolean;
  types: PushEventType[];
  createdAt: string | null;
  updatedAt: string | null;
  error: string;
}

export type PushCheckStatus = "idle" | "loading" | "success" | "error";

export interface PushCheckState {
  status: PushCheckStatus;
  message: string;
}

export interface PushShopState {
  shopId: ShopId;
  loading: boolean;
  apiAvailable: boolean;
  listReady: boolean;
  types: PushEventType[];
  typesFresh: boolean;
  subscriptions: PushSubscription[];
  typeError: string;
  listError: string;
  selectedTypes: PushEventType[];
  urlDraft: string;
  setting: boolean;
  setError: string;
  enableBusyIds: string[];
  enableError: string;
  deletingIds: string[];
  deleteError: string;
  check: PushCheckState;
}

export type AlertStatus = "open" | "resolved" | "all";
export type AlertSeverity = "critical" | "high" | "warning";
export type AlertCategory = "advertising" | "inventory" | "sales";
export type AlertRuleKey =
  | "ad_spend_spike"
  | "ad_drr_high"
  | "ad_clicks_no_orders"
  | "ad_orders_drop"
  | "inventory_risk"
  | "sales_drop";
export type AlertMetricValue = string | number | boolean | null;
export type AlertMetrics = Record<string, AlertMetricValue>;
export type AlertRuleConfig = Record<string, number>;

export interface AlertSummary {
  active: number;
  critical: number;
  high: number;
  warning: number;
  advertising: number;
  inventory: number;
  sales: number;
}

export interface AlertEvent {
  id: number;
  shop_id: ShopId;
  rule_key: AlertRuleKey;
  entity_type: string;
  entity_id: string;
  severity: AlertSeverity;
  title: string;
  message: string;
  first_seen_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  acknowledged_at: string | null;
  last_notified_at: string | null;
  last_notify_error: string | null;
  shop_name: string;
  metrics: AlertMetrics;
  status: Exclude<AlertStatus, "all">;
  rule_label: string;
  category: AlertCategory;
  object_name: string;
}

export interface AlertEventListResponse {
  items: AlertEvent[];
  total: number;
  page: number;
  size: number;
}

export interface AlertRule {
  shop_id: ShopId;
  rule_key: AlertRuleKey;
  enabled: boolean;
  notify_dingtalk: boolean;
  config: AlertRuleConfig;
  updated_at: string | null;
  label: string;
  category: AlertCategory;
}

export interface AlertEvaluationResponse {
  evaluated: number;
  triggered: number;
  updated: number;
  resolved: number;
  notifications_sent: number;
  notifications_failed: number;
  skipped: Array<{ shop_id: ShopId; rule_key: AlertRuleKey; reason: string }>;
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

export type ReturnDeadlineStatus = "normal" | "due_soon" | "due_today" | "overdue" | "missing";

export interface ReturnProductAmount {
  currency_code?: string | null;
  price?: number | null;
}

export interface ReturnSummaryShop {
  shop_id: ShopId;
  shop_name: string;
  records: number;
  quantity: number;
}

export interface RfbsReturnSummaryShop {
  shop_id: ShopId;
  shop_name: string;
  records: number;
}

export interface ReturnSummary {
  records: number;
  shops: ReturnSummaryShop[];
}

export interface RfbsReturnSummary {
  records: number;
  shops: RfbsReturnSummaryShop[];
}

export interface ReturnRecord {
  shop_id: ShopId;
  shop_name: string;
  occurred_at: string | null;
  posting_number: string | null;
  sku: string | null;
  offer_id: string | null;
  product_name: string | null;
  quantity: number | null;
  reason: string | null;
  reason_raw: string | null;
  status: string | null;
  compensation_status: string | null;
  product_amount: ReturnProductAmount | number | null;
  product_currency: string | null;
  logistic_return_at: string | null;
  buyer_comment_raw: string | null;
  type: string | null;
  cancelled_at: string | null;
  complaint_deadline: string | null;
  complaint_deadline_status: ReturnDeadlineStatus;
}

export interface ReturnsResponse {
  summary: ReturnSummary;
  items: ReturnRecord[];
  total: number;
  page: number;
  size: number;
  data_through: string | null;
}

export interface RfbsReturnRecord {
  shop_id: ShopId;
  shop_name: string;
  settlement_currency: string;
  return_id: number;
  return_number: string;
  created_at: string | null;
  posting_number: string | null;
  offer_id: string | null;
  sku: string | null;
  product_name: string | null;
  status_raw: string | null;
  status_name: string | null;
  quantity: number | null;
  reason_raw: string | null;
  reason_name: string | null;
  compensation_status: string | null;
  product_amount: number | null;
  product_currency: string | null;
  logistic_return_at: string | null;
  buyer_comment_raw: string | null;
  refund_amount: number | null;
  refund_currency: string | null;
  platform_compensation_rub: string | number | null;
  platform_compensated_at: string | null;
  logistics_compensation_cny: string | number | null;
  logistics_compensated_at: string | null;
  return_method: string | null;
  return_result: string | null;
  platform_compensation_original_currency: string;
  platform_compensation_converted_amount: string | null;
  platform_compensation_converted_currency: string;
  platform_compensation_base_rates: Record<string, string>;
  platform_compensation_missing_rate: boolean;
  platform_compensated_at_beijing: string | null;
  logistics_compensation_original_currency: string;
  logistics_compensation_converted_amount: string | null;
  logistics_compensation_converted_currency: string;
  logistics_compensation_base_rates: Record<string, string>;
  logistics_compensation_missing_rate: boolean;
  logistics_compensated_at_beijing: string | null;
  complaint_deadline: string | null;
  complaint_deadline_status: ReturnDeadlineStatus;
}

export interface RfbsReturnsResponse {
  summary: RfbsReturnSummary;
  items: RfbsReturnRecord[];
  total: number;
  page: number;
  size: number;
  data_through: string | null;
}

export type ComplaintDeadlineStatus = "normal" | "due_soon" | "due_today" | "overdue" | "missing";
export type ComplaintStatusFilter = "" | "unfiled" | "open" | "closed";

export interface ComplaintRecord {
  shop_id: ShopId;
  complaint_number: string;
  posting_number: string;
  complaint_at: string;
  channel: string;
  resolved: number | null;
  package_returned: number | null;
  compensation_amount: number | null;
  compensation_currency: string | null;
  notes: string | null;
  not_received_return: number | null;
  warehouse: string | null;
  order_process_status: string | null;
  complaint_status: string | null;
  compensation_status: string | null;
  platform_compensation_rub: string | number | null;
  platform_compensated_at: string | null;
  logistics_compensation_cny: string | number | null;
  logistics_compensated_at: string | null;
  created_at: string;
  updated_at: string;
  settlement_currency: string;
  platform_compensation_original_currency: string;
  platform_compensation_converted_amount: string | null;
  platform_compensation_converted_currency: string;
  platform_compensation_base_rates: Record<string, string>;
  platform_compensation_missing_rate: boolean;
  platform_compensated_at_beijing: string | null;
  logistics_compensation_original_currency: string;
  logistics_compensation_converted_amount: string | null;
  logistics_compensation_converted_currency: string;
  logistics_compensation_base_rates: Record<string, string>;
  logistics_compensation_missing_rate: boolean;
  logistics_compensated_at_beijing: string | null;
}

export interface ShippingComplaintOrderItem {
  shop_id: ShopId;
  posting_number: string;
  sku: string | null;
  offer_id: string | null;
  product_name_raw: string | null;
  quantity: number;
  unit_price: number | null;
  price_currency: string | null;
  product_name: string | null;
}

export interface ShippingComplaintOrder {
  shop_id: ShopId;
  shop_name: string;
  posting_number: string;
  created_at: string | null;
  shipped_at: string | null;
  tracking_number: string | null;
  status_raw: string;
  cancel_reason_raw: string | null;
  shipped: number;
  data_anomaly: number;
  amount_original: number | null;
  amount_currency: string | null;
  status_changed_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  complaint_deadline: string | null;
  complaint_deadline_status: ComplaintDeadlineStatus;
  items: ShippingComplaintOrderItem[];
  complaints: ComplaintRecord[];
}

export interface ShippingComplaintsResponse {
  items: ShippingComplaintOrder[];
  total: number;
  page: number;
  size: number;
  data_through: string | null;
}

export interface ReceivedDisputeRecord {
  shop_id: ShopId;
  shop_name: string;
  settlement_currency: string;
  return_number: string;
  created_at: string | null;
  posting_number: string | null;
  sku: string | null;
  offer_id: string | null;
  product_name: string | null;
  product_amount: number | null;
  product_currency: string | null;
  reason_raw: string | null;
  reason_name: string | null;
  buyer_comment_raw: string | null;
  refund_type: string | null;
  refund_amount: number | null;
  refund_currency: string | null;
  platform_compensation_rub: string | number | null;
  platform_compensated_at: string | null;
  logistics_compensation_cny: string | number | null;
  logistics_compensated_at: string | null;
  process_status: string | null;
  return_method: string | null;
  iml_return_number: string | null;
  iml_system_sn: string | null;
  buyer_tracking_number: string | null;
  handling_method: string | null;
  video_recorded: number | null;
  outbound_order_number: string | null;
  return_result: string | null;
  notes: string | null;
  manual_created_at: string | null;
  updated_at: string | null;
  complaint_deadline: string | null;
  complaint_deadline_status: ComplaintDeadlineStatus;
  platform_compensation_original_currency: string;
  platform_compensation_converted_amount: string | null;
  platform_compensation_converted_currency: string;
  platform_compensation_base_rates: Record<string, string>;
  platform_compensation_missing_rate: boolean;
  platform_compensated_at_beijing: string | null;
  logistics_compensation_original_currency: string;
  logistics_compensation_converted_amount: string | null;
  logistics_compensation_converted_currency: string;
  logistics_compensation_base_rates: Record<string, string>;
  logistics_compensation_missing_rate: boolean;
  logistics_compensated_at_beijing: string | null;
}

export interface ReceivedDisputesResponse {
  items: ReceivedDisputeRecord[];
  total: number;
  page: number;
  size: number;
  data_through: string | null;
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

export interface RiskStats {
  valid: number;
  cancelled: number;
  unclaimed: number;
  customs: number;
  cancelled_rate: number | null;
  unclaimed_rate: number | null;
  customs_rate: number | null;
}

export interface RiskItem {
  shop_id: ShopId;
  shop_name: string;
  item_key: string;
  sku: string;
  primary_offer_id: string | null;
  member_count: number;
  product_name: string;
  search_text: string;
  total: RiskStats;
  channels: Record<Channel, RiskStats | null>;
}

export interface RiskResponse {
  range: { from: string; to: string };
  summary: RiskStats;
  items: RiskItem[];
}

export interface RiskReasonStats {
  orders: number;
  pieces: number;
}

export interface RiskReasonRow {
  reason_raw: string;
  reason_name: string;
  total: RiskReasonStats;
  channels: Record<Channel, RiskReasonStats>;
}

export interface RiskReasonDetail {
  shop_id: ShopId;
  shop_name: string;
  channel: Channel;
  posting_number: string;
  pieces: number;
}

export interface RiskReasonsResponse {
  range: { from: string; to: string };
  items: RiskReasonRow[];
  details: RiskReasonDetail[];
}

export type SyncModule = "orders" | "returns" | "stock";
export type ManualSyncModule = SyncModule | "ad_campaigns" | "ad_campaign_daily" | "ad_sku_daily";
export type AutoSyncModule = SyncModule | "ad_campaign_daily" | "ad_sku_daily";

export interface SyncRun {
  id: number;
  shop_id: ShopId;
  shop_name: string;
  module: string;
  range_from: string;
  range_to: string;
  status: string;
  progress_total: number;
  progress_done: number;
  records: number;
  data_through: string | null;
  current_from: string | null;
  current_to: string | null;
  run_source: string | null;
  scheduled_slot: string | null;
  started_at: string;
  finished_at: string | null;
  error: string | null;
}

export interface SyncTaskResponse {
  run_id: number;
  status: string;
  progress_total: number;
}

export interface PerformanceSyncResponse {
  shop_id: ShopId;
  success: boolean;
  fetched: number;
  inserted_or_updated: number;
  run_id?: number;
}

export interface PerformanceStatisticsBreakdown {
  fetched: number;
  inserted_or_updated: number;
  dates?: string[];
}

export interface PerformanceStatisticsSyncResponse extends PerformanceSyncResponse {
  date_from: string;
  date_to: string;
  campaign_daily: PerformanceStatisticsBreakdown;
  sku: PerformanceStatisticsBreakdown;
  sku_skipped_dates?: string[];
}

export interface AutoSyncSetting {
  shop_id: ShopId;
  module: AutoSyncModule;
  enabled: number;
  interval_hours: number;
  range_days: number;
}

export interface AutoSyncSettingValue {
  enabled: boolean;
  interval_hours: number;
  range_days: number;
}

export type AutoSyncSettingsPayload = Record<"1" | "2", Record<AutoSyncModule, AutoSyncSettingValue>>;

export interface ExchangeRate {
  base_rate: string;
  valid_from_utc: string;
  valid_to_utc: string;
  from_currency?: string;
  to_currency?: string;
  rate_with_adjustment?: string | null;
  source?: string;
  fetched_at?: string;
}

export interface ExchangeRateStatus {
  source: string;
  last_success_at: string | null;
  data_through: string | null;
  rates: Record<string, ExchangeRate | null>;
}

export interface ExchangeRateSyncResponse {
  records: number;
  segments: number;
  data_through: string;
}

export type ProductRuleMemberType = "sku" | "offer_id";
export type ProductRuleWriteKind = "short_name" | "delete_short_name" | "merge" | "dissolve";

export interface ProductRulesSummary {
  short_names: number;
  merges: number;
}

export interface ProductShortName {
  sku: string;
  short_name: string;
  updated_at: string;
}

export interface ProductRuleMember {
  key_type: ProductRuleMemberType;
  key_value: string;
}

export interface ProductRuleGroup {
  id: number;
  primary_offer_id: string | null;
  primary_sku: string | null;
  status: string;
  note: string;
  updated_at: string;
  product_name: string;
  members: ProductRuleMember[];
}

export interface ProductRuleConflict {
  key_type: "merge";
  key_value: string;
  note: string;
}

export interface ProductRuleProduct {
  sku: string;
  offer_id: string;
  product_name: string;
}

export interface ProductRulesResponse {
  summary: ProductRulesSummary;
  short_names: ProductShortName[];
  groups: ProductRuleGroup[];
  products: ProductRuleProduct[];
  conflicts: ProductRuleConflict[];
  fixed_rule: string;
}

export interface ProductRuleShortNamePayload {
  kind: "short_name";
  sku: string;
  short_name: string;
}

export interface ProductRuleDeleteShortNamePayload {
  kind: "delete_short_name";
  sku: string;
}

export interface ProductRuleMergePayload {
  kind: "merge";
  id: number;
  primary_offer_id: string;
  primary_sku: string;
  members: ProductRuleMember[];
}

export interface ProductRuleDissolvePayload {
  kind: "dissolve";
  id: number;
}
