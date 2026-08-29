import { request } from "../../shared/api/client";
import type {
  InventoryResponse,
  InventoryRiskFilter,
  InventorySort,
  SortOrder,
} from "./types";
import type { Channel, ShopSelection } from "../../shared/types/common";

export interface InventoryQuery {
  shopId?: ShopSelection;
  page?: number;
  size?: number;
  sku?: string;
  offerId?: string;
  productName?: string;
  channel?: Channel;
  risk?: InventoryRiskFilter;
  sortBy?: Exclude<InventorySort, "">;
  sortOrder?: SortOrder;
}

export function listInventory(queryValues: InventoryQuery = {}): Promise<InventoryResponse> {
  const query = new URLSearchParams();
  if (queryValues.shopId !== undefined) query.set("shop_id", String(queryValues.shopId));
  if (queryValues.page !== undefined) query.set("page", String(queryValues.page));
  if (queryValues.size !== undefined) query.set("size", String(queryValues.size));
  if (queryValues.sku) query.set("sku", queryValues.sku);
  if (queryValues.offerId) query.set("offer_id", queryValues.offerId);
  if (queryValues.productName) query.set("product_name", queryValues.productName);
  if (queryValues.channel) query.set("channel", queryValues.channel);
  if (queryValues.risk) query.set("risk", queryValues.risk);
  if (queryValues.sortBy) query.set("sort_by", queryValues.sortBy);
  if (queryValues.sortOrder) query.set("sort_order", queryValues.sortOrder);
  return request<InventoryResponse>(`/api/stock?${query}`);
}
