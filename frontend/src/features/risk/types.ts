import type { Channel, ShopId } from "../../shared/types/common";

export interface RiskStats {
  valid: number;
  cancelled: number;
  unclaimed: number;
  customs: number;
  cancelled_rate: number | null;
  unclaimed_rate: number | null;
  customs_rate: number | null;
}

export interface RiskItem {
  shop_id: ShopId;
  shop_name: string;
  item_key: string;
  sku: string;
  primary_offer_id: string | null;
  member_count: number;
  product_name: string;
  search_text: string;
  total: RiskStats;
  channels: Record<Channel, RiskStats | null>;
}

export interface RiskResponse {
  range: { from: string; to: string };
  summary: RiskStats;
  items: RiskItem[];
}

export interface RiskReasonStats {
  orders: number;
  pieces: number;
}

export interface RiskReasonRow {
  reason_raw: string;
  reason_name: string;
  total: RiskReasonStats;
  channels: Record<Channel, RiskReasonStats>;
}

export interface RiskReasonDetail {
  shop_id: ShopId;
  shop_name: string;
  channel: Channel;
  posting_number: string;
  pieces: number;
}

export interface RiskReasonsResponse {
  range: { from: string; to: string };
  items: RiskReasonRow[];
  details: RiskReasonDetail[];
}
