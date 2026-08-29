import { request } from "../../shared/api/client";
import type { OrderListResponse, OrderStatusFilter } from "./types";
import type { Channel, ShopSelection } from "../../shared/types/common";

export interface OrderQuery {
  shopId?: ShopSelection;
  channel?: Channel;
  search?: string;
  page?: number;
  size?: number;
  from?: string;
  to?: string;
  status?: Exclude<OrderStatusFilter, "">;
}

export function listOrders(queryValues: OrderQuery = {}): Promise<OrderListResponse> {
  const query = new URLSearchParams();
  if (queryValues.shopId !== undefined) query.set("shop_id", String(queryValues.shopId));
  if (queryValues.channel) query.set("channel", queryValues.channel);
  if (queryValues.search) query.set("q", queryValues.search);
  if (queryValues.page !== undefined) query.set("page", String(queryValues.page));
  if (queryValues.size !== undefined) query.set("size", String(queryValues.size));
  if (queryValues.from) query.set("from", queryValues.from);
  if (queryValues.to) query.set("to", queryValues.to);
  if (queryValues.status) query.set("status", queryValues.status);
  return request<OrderListResponse>(`/api/orders?${query}`);
}
