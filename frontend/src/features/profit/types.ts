import type { Channel, ShopId } from "../../shared/types/common";

export type ActualProfitStatus = "ready" | "incomplete";
export type ActualProfitFinanceStatus = "available" | "missing";
export type ActualProfitErpStatus = "complete" | "incomplete";

export interface ActualProfitFinance {
  status: ActualProfitFinanceStatus;
  operation_count: number;
  currency: string | null;
  net_amount: string | null;
  net_cny: string | null;
}

export interface ActualProfitErpCost {
  status: ActualProfitErpStatus;
  item_count: number;
  matched_items: number;
  missing_items: number;
  quantity_mismatch_items: number;
  offer_id_mismatch_items: number;
  exchange_rate_original: string | null;
  total_cost_cny: string | null;
}

export interface ActualProfitOrder {
  shop_id: ShopId;
  shop_name: string;
  posting_number: string;
  channel: Channel;
  created_at: string;
  status_raw: string;
  finance: ActualProfitFinance;
  erp_cost: ActualProfitErpCost;
  actual_profit_cny: string | null;
  profit_status: ActualProfitStatus;
  incomplete_reasons: string[];
}

export interface ActualProfitResponse {
  items: ActualProfitOrder[];
  total: number;
  page: number;
  size: number;
}
