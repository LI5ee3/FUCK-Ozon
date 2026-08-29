import type { ShopId } from "../../shared/types/common";

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
