import { request } from "./client";
import type { ShopSelection, TimelinessResponse } from "../types/api";

export interface TimelinessQuery {
  shopId?: ShopSelection;
  page?: number;
  size?: number;
  search?: string;
  from?: string;
  to?: string;
}

export function listTimeliness(queryValues: TimelinessQuery = {}): Promise<TimelinessResponse> {
  const query = new URLSearchParams();
  if (queryValues.shopId !== undefined) query.set("shop_id", String(queryValues.shopId));
  if (queryValues.page !== undefined) query.set("page", String(queryValues.page));
  if (queryValues.size !== undefined) query.set("size", String(queryValues.size));
  if (queryValues.search) query.set("q", queryValues.search);
  if (queryValues.from) query.set("from", queryValues.from);
  if (queryValues.to) query.set("to", queryValues.to);
  return request<TimelinessResponse>(`/api/timeliness?${query}`);
}
