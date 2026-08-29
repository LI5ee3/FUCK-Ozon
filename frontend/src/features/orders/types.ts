import type { Channel, ShopId } from "../../shared/types/common";

export type OrderStatusFilter = "" | "pending" | "shipping" | "delivered" | "cancelled";

export interface OrderItem {
  shop_id: ShopId;
  posting_number: string;
  sku: string | null;
  offer_id: string | null;
  product_name_raw: string | null;
  product_name_original: string | null;
  quantity: number;
  unit_price: number | null;
  price_currency: string | null;
}

export interface Order {
  shop_id: ShopId;
  shop_name: string;
  posting_number: string;
  channel: Channel;
  created_at: string;
  shipped_at: string | null;
  delivered_at: string | null;
  status_raw: string;
  cancel_reason_raw: string | null;
  shipped: number;
  data_anomaly: number;
  amount_original: number | null;
  amount_currency: string | null;
  items: OrderItem[];
  sku_types: number;
  pieces: number;
}

export interface OrderStatusCounts {
  all: number;
  pending: number;
  shipping: number;
  delivered: number;
  cancelled: number;
  cancelled_shipped: number;
  anomaly: number;
}

export interface OrderListResponse {
  items: Order[];
  total: number;
  page: number;
  size: number;
  status_counts: OrderStatusCounts;
}
