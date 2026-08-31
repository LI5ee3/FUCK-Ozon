import type { ShopId } from "../../shared/types/common";

export type ComplaintDeadlineStatus = "normal" | "due_soon" | "due_today" | "overdue" | "missing";
export type ComplaintStatusFilter = "" | "unfiled" | "open" | "closed";

export interface ComplaintRecord {
  shop_id: ShopId;
  complaint_number: string;
  posting_number: string;
  complaint_at: string;
  channel: string;
  resolved: number | null;
  package_returned: number | null;
  compensation_amount: number | null;
  compensation_currency: string | null;
  notes: string | null;
  not_received_return: number | null;
  warehouse: string | null;
  order_process_status: string | null;
  complaint_status: string | null;
  compensation_status: string | null;
  platform_compensation_rub: string | number | null;
  platform_compensated_at: string | null;
  logistics_compensation_cny: string | number | null;
  logistics_compensated_at: string | null;
  created_at: string;
  updated_at: string;
  settlement_currency: string;
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
}

export interface ShippingComplaintOrderItem {
  shop_id: ShopId;
  posting_number: string;
  sku: string | null;
  offer_id: string | null;
  product_name_raw: string | null;
  quantity: number;
  unit_price: number | null;
  price_currency: string | null;
  product_name: string | null;
}

export interface ShippingComplaintOrder {
  shop_id: ShopId;
  shop_name: string;
  posting_number: string;
  created_at: string | null;
  shipped_at: string | null;
  tracking_number: string | null;
  status_raw: string;
  cancel_reason_raw: string | null;
  shipped: number;
  data_anomaly: number;
  amount_original: number | null;
  amount_currency: string | null;
  status_changed_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  complaint_deadline: string | null;
  complaint_deadline_status: ComplaintDeadlineStatus;
  items: ShippingComplaintOrderItem[];
  complaints: ComplaintRecord[];
}

export interface ShippingComplaintsResponse {
  items: ShippingComplaintOrder[];
  total: number;
  page: number;
  size: number;
  data_through: string | null;
}

export interface ReceivedDisputeRecord {
  shop_id: ShopId;
  shop_name: string;
  settlement_currency: string;
  return_number: string;
  created_at: string | null;
  posting_number: string | null;
  sku: string | null;
  offer_id: string | null;
  product_name: string | null;
  product_amount: number | null;
  product_currency: string | null;
  reason_raw: string | null;
  reason_name: string | null;
  buyer_comment_raw: string | null;
  refund_type: string | null;
  refund_amount: number | null;
  refund_currency: string | null;
  platform_compensation_rub: string | number | null;
  platform_compensated_at: string | null;
  logistics_compensation_cny: string | number | null;
  logistics_compensated_at: string | null;
  process_status: string | null;
  return_method: string | null;
  iml_return_number: string | null;
  iml_system_sn: string | null;
  buyer_tracking_number: string | null;
  handling_method: string | null;
  video_recorded: number | null;
  outbound_order_number: string | null;
  return_result: string | null;
  notes: string | null;
  manual_created_at: string | null;
  updated_at: string | null;
  complaint_deadline: string | null;
  complaint_deadline_status: ComplaintDeadlineStatus;
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
}

export interface ReceivedDisputesResponse {
  items: ReceivedDisputeRecord[];
  total: number;
  page: number;
  size: number;
  data_through: string | null;
}
