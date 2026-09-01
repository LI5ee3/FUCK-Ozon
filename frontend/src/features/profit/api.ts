import { request } from "../../shared/api/client";
import type { ShopSelection } from "../../shared/types/common";
import type { ActualProfitResponse } from "./types";

export interface ActualProfitQuery {
  shopId: ShopSelection;
  dateFrom: string;
  dateTo: string;
  search?: string;
  page: number;
  size: number;
}

export function listActualOrderProfits(values: ActualProfitQuery): Promise<ActualProfitResponse> {
  const query = new URLSearchParams({
    shop_id: String(values.shopId),
    from: values.dateFrom,
    to: values.dateTo,
    page: String(values.page),
    size: String(values.size),
  });
  if (values.search?.trim()) query.set("q", values.search.trim());
  return request<ActualProfitResponse>(`/api/profit/actual/orders?${query}`);
}
