import { request, requestJson } from "./client";
import type {
  ComplaintStatusFilter,
  OkResponse,
  ReceivedDisputesResponse,
  ShippingComplaintsResponse,
  ShopId,
  ShopSelection,
} from "../types/api";

export interface ComplaintsQuery {
  shopId?: ShopSelection;
  page?: number;
  size?: number;
  search?: string;
  status?: ComplaintStatusFilter;
  from?: string;
  to?: string;
}

function queryString(values: ComplaintsQuery): string {
  const query = new URLSearchParams();
  if (values.shopId !== undefined) query.set("shop_id", String(values.shopId));
  if (values.page !== undefined) query.set("page", String(values.page));
  if (values.size !== undefined) query.set("size", String(values.size));
  if (values.search) query.set("q", values.search);
  if (values.status) query.set("status", values.status);
  if (values.from) query.set("from", values.from);
  if (values.to) query.set("to", values.to);
  return query.toString();
}

export function listShippingComplaints(values: ComplaintsQuery = {}): Promise<ShippingComplaintsResponse> {
  return request<ShippingComplaintsResponse>(`/api/exception-complaints/shipping?${queryString(values)}`);
}

export function listReceivedDisputes(values: ComplaintsQuery = {}): Promise<ReceivedDisputesResponse> {
  return request<ReceivedDisputesResponse>(`/api/exception-complaints/received?${queryString(values)}`);
}

export interface ShippingComplaintPayload {
  shop_id: ShopId;
  posting_number: string;
  complaint_number: string;
  complaint_at: string;
  channel: string;
  not_received_return: boolean | null;
  warehouse: string;
  order_process_status: string;
  complaint_status: string;
  compensation_status: string;
  platform_compensation_rub: number | null;
  platform_compensated_at: string;
  logistics_compensation_cny: number | null;
  logistics_compensated_at: string;
  resolved: boolean | null;
  package_returned: null;
  notes: string;
}

export interface ReceivedDisputePayload {
  shop_id: ShopId;
  return_number: string;
  refund_type: string;
  refund_amount: number | null;
  refund_currency: string;
  platform_compensation_rub: number | null;
  platform_compensated_at: string;
  logistics_compensation_cny: number | null;
  logistics_compensated_at: string;
  process_status: string;
  return_method: string;
  iml_return_number: string;
  iml_system_sn: string;
  buyer_tracking_number: string;
  handling_method: string;
  video_recorded: boolean | null;
  outbound_order_number: string;
  return_result: string;
  notes: string;
}

export function saveShippingComplaint(body: ShippingComplaintPayload): Promise<OkResponse> {
  return requestJson<OkResponse>("/api/exception-complaints/shipping", "PUT", body);
}

export function saveReceivedDispute(body: ReceivedDisputePayload): Promise<OkResponse> {
  return requestJson<OkResponse>("/api/exception-complaints/received", "PUT", body);
}
