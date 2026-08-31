import type { ShopId } from "../../shared/types/common";

export type ReturnDeadlineStatus = "normal" | "due_soon" | "due_today" | "overdue" | "missing";

export interface ReturnProductAmount {
  currency_code?: string | null;
  price?: number | null;
}

export interface ReturnSummaryShop {
  shop_id: ShopId;
  shop_name: string;
  records: number;
  quantity: number;
}

export interface RfbsReturnSummaryShop {
  shop_id: ShopId;
  shop_name: string;
  records: number;
}

export interface ReturnSummary {
  records: number;
  shops: ReturnSummaryShop[];
}

export interface RfbsReturnSummary {
  records: number;
  shops: RfbsReturnSummaryShop[];
}

export interface ReturnRecord {
  shop_id: ShopId;
  shop_name: string;
  occurred_at: string | null;
  posting_number: string | null;
  sku: string | null;
  offer_id: string | null;
  product_name: string | null;
  quantity: number | null;
  reason: string | null;
  reason_raw: string | null;
  status: string | null;
  compensation_status: string | null;
  product_amount: ReturnProductAmount | number | null;
  product_currency: string | null;
  logistic_return_at: string | null;
  buyer_comment_raw: string | null;
  type: string | null;
  cancelled_at: string | null;
  complaint_deadline: string | null;
  complaint_deadline_status: ReturnDeadlineStatus;
}

export interface ReturnsResponse {
  summary: ReturnSummary;
  items: ReturnRecord[];
  total: number;
  page: number;
  size: number;
  data_through: string | null;
}

export interface RfbsReturnRecord {
  shop_id: ShopId;
  shop_name: string;
  settlement_currency: string;
  return_id: number;
  return_number: string;
  created_at: string | null;
  posting_number: string | null;
  offer_id: string | null;
  sku: string | null;
  product_name: string | null;
  status_raw: string | null;
  status_name: string | null;
  quantity: number | null;
  reason_raw: string | null;
  reason_name: string | null;
  compensation_status: string | null;
  product_amount: number | null;
  product_currency: string | null;
  logistic_return_at: string | null;
  buyer_comment_raw: string | null;
  refund_amount: number | null;
  refund_currency: string | null;
  platform_compensation_rub: string | number | null;
  platform_compensated_at: string | null;
  logistics_compensation_cny: string | number | null;
  logistics_compensated_at: string | null;
  return_method: string | null;
  return_result: string | null;
  platform_compensation_original_currency: string;
  platform_compensation_converted_amount: string | null;
  platform_compensation_converted_currency: string;
  platform_compensation_service_penalty_exchange_rates: Record<string, string>;
  platform_compensation_missing_rate: boolean;
  platform_compensated_at_beijing: string | null;
  logistics_compensation_original_currency: string;
  logistics_compensation_converted_amount: string | null;
  logistics_compensation_converted_currency: string;
  logistics_compensation_service_penalty_exchange_rates: Record<string, string>;
  logistics_compensation_missing_rate: boolean;
  logistics_compensated_at_beijing: string | null;
  complaint_deadline: string | null;
  complaint_deadline_status: ReturnDeadlineStatus;
}

export interface RfbsReturnsResponse {
  summary: RfbsReturnSummary;
  items: RfbsReturnRecord[];
  total: number;
  page: number;
  size: number;
  data_through: string | null;
}
