export type ShopId = 1 | 2;
export type ShopSelection = 0 | ShopId;
export type Granularity = "day" | "week" | "month";
export type Channel = "FBP" | "realFBS" | "WHD";

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
