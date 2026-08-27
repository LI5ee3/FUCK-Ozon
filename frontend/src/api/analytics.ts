import { request } from "./client";
import type {
  AnalyticsDataResponse,
  AnalyticsProductQueryDetailResponse,
  AnalyticsProductQueryResponse,
  ShopId,
  ShopSelection,
} from "../types/api";

export interface AnalyticsQuery {
  shopId: ShopSelection;
  sku?: string;
  page?: number;
  size?: number;
  from?: string;
  to?: string;
}

export interface AnalyticsDetailQuery extends Omit<AnalyticsQuery, "shopId" | "sku"> {
  shopId: ShopId;
  sku: string;
}

function queryString(values: AnalyticsQuery): string {
  const query = new URLSearchParams({ shop_id: String(values.shopId) });
  if (values.sku) query.set("sku", values.sku);
  if (values.page !== undefined) query.set("page", String(values.page));
  if (values.size !== undefined) query.set("size", String(values.size));
  if (values.from) query.set("from", values.from);
  if (values.to) query.set("to", values.to);
  return query.toString();
}

export function getAnalyticsData(values: AnalyticsQuery): Promise<AnalyticsDataResponse> {
  return request<AnalyticsDataResponse>(`/api/analytics/data?${queryString(values)}`);
}

export function getProductQueries(values: AnalyticsQuery): Promise<AnalyticsProductQueryResponse> {
  return request<AnalyticsProductQueryResponse>(`/api/analytics/product-queries?${queryString(values)}`);
}

export function getProductQueryDetails(values: AnalyticsDetailQuery): Promise<AnalyticsProductQueryDetailResponse> {
  return request<AnalyticsProductQueryDetailResponse>(`/api/analytics/product-queries/details?${queryString(values)}`);
}
