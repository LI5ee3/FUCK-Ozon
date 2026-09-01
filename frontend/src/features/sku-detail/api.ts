import { request } from "../../shared/api/client";
import type { ShopId } from "../../shared/types/common";
import type { AnalyticsDataResponse, AnalyticsProductQueryDetailResponse } from "../analytics/types";
import type { SkuDetailResponse } from "./types";

export interface SkuDetailQuery {
  shopId: ShopId;
  sku: string;
  from: string;
  to: string;
}

type SkuDetailFilters = Pick<SkuDetailQuery, "shopId" | "from" | "to">;

function queryString(values: SkuDetailFilters): string {
  return new URLSearchParams({
    shop_id: String(values.shopId),
    from: values.from,
    to: values.to,
  }).toString();
}

export function getSkuDetail(values: SkuDetailQuery): Promise<SkuDetailResponse> {
  return request<SkuDetailResponse>(`/api/sku-detail/${encodeURIComponent(values.sku)}?${queryString(values)}`);
}

export function getSkuTraffic(values: SkuDetailQuery): Promise<AnalyticsDataResponse> {
  const query = new URLSearchParams(queryString(values));
  query.set("sku", values.sku);
  return request<AnalyticsDataResponse>(`/api/analytics/data?${query}`);
}

export function getSkuQueryDetails(values: SkuDetailQuery, page: number, size: number): Promise<AnalyticsProductQueryDetailResponse> {
  const query = new URLSearchParams(queryString(values));
  query.set("sku", values.sku);
  query.set("page", String(page));
  query.set("size", String(size));
  return request<AnalyticsProductQueryDetailResponse>(`/api/analytics/product-queries/details?${query}`);
}
