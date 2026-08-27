import { request } from "./client";
import type { DashboardSummary, Granularity, OrderTrend, ShopSelection } from "../types/api";

export function getDashboardSummary(
  shopId: ShopSelection,
  from?: string,
  to?: string,
  granularity: Granularity = "week",
): Promise<DashboardSummary> {
  const query = new URLSearchParams({ shop_id: String(shopId), granularity });
  if (from) query.set("from", from);
  if (to) query.set("to", to);
  return request<DashboardSummary>(`/api/summary?${query}`);
}

export function getOrderTrend(shopId: ShopSelection, granularity: Granularity = "day"): Promise<OrderTrend> {
  const query = new URLSearchParams({ shop_id: String(shopId), granularity });
  return request<OrderTrend>(`/api/order-trend?${query}`);
}
