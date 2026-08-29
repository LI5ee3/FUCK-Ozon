import type { Channel, ShopId } from "../../shared/types/common";

export interface TimelinessSummary {
  orders: number;
  shipped_orders: number;
  delivered_orders: number;
  ship_samples: number;
  delivery_samples: number;
  avg_ship_hours: number | null;
  p50_ship_hours: number | null;
  p90_ship_hours: number | null;
  avg_delivery_hours: number | null;
  p50_delivery_hours: number | null;
  p90_delivery_hours: number | null;
}

export interface TimelinessGroup {
  shop_id: ShopId;
  shop_name: string;
  channel: Channel;
  orders: number;
  created: number;
  shipped: number;
  delivered: number;
  ship_samples: number;
  delivery_samples: number;
  ship_sample_insufficient: boolean;
  delivery_sample_insufficient: boolean;
  avg_ship_hours: number | null;
  p50_ship_hours: number | null;
  p90_ship_hours: number | null;
  avg_delivery_hours: number | null;
  p50_delivery_hours: number | null;
  p90_delivery_hours: number | null;
  created_completeness: number;
  shipped_completeness: number;
  delivered_completeness: number;
}

export interface TimelinessItem {
  shop_id: ShopId;
  shop_name: string;
  posting_number: string;
  channel: Channel;
  created_at: string;
  shipped_at: string | null;
  delivered_at: string | null;
  ship_hours: number | null;
  delivery_hours: number | null;
  ship_anomaly: boolean;
  delivery_anomaly: boolean;
}

export interface TimelinessResponse {
  range: { from: string; to: string };
  summary: TimelinessSummary;
  items: TimelinessItem[];
  total: number;
  page: number;
  size: number;
  groups: TimelinessGroup[];
  data_through: string | null;
}
