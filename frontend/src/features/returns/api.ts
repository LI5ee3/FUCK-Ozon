import { request } from "../../shared/api/client";
import type { RfbsReturnsResponse, ReturnsResponse } from "./types";
import type { ShopSelection } from "../../shared/types/common";

export interface ReturnsQuery {
  shopId?: ShopSelection;
  page?: number;
  size?: number;
  search?: string;
  from?: string;
  to?: string;
}

function queryString(values: ReturnsQuery): string {
  const query = new URLSearchParams();
  if (values.shopId !== undefined) query.set("shop_id", String(values.shopId));
  if (values.page !== undefined) query.set("page", String(values.page));
  if (values.size !== undefined) query.set("size", String(values.size));
  if (values.search) query.set("q", values.search);
  if (values.from) query.set("from", values.from);
  if (values.to) query.set("to", values.to);
  return query.toString();
}

export function listReturns(values: ReturnsQuery = {}): Promise<ReturnsResponse> {
  return request<ReturnsResponse>(`/api/returns?${queryString(values)}`);
}

export function listRfbsReturns(values: ReturnsQuery = {}): Promise<RfbsReturnsResponse> {
  return request<RfbsReturnsResponse>(`/api/rfbs-returns?${queryString(values)}`);
}
