import type { Channel } from "../../shared/types/common";

export type Granularity = "day" | "week" | "month";

export interface GmvSummary {
  amount: number;
  currency: string;
  missing_rate_orders: number;
}

export interface OverviewTotals {
  orders: number;
  pieces: number;
  cancelled_orders: number;
  cancelled_pieces: number;
  cancel_rate: number;
}

export interface OverviewChannel {
  channel: Channel;
  orders: number;
  pieces: number;
  cancelled_pieces: number;
}

export interface TimelinessOverview {
  channel: Channel;
  ship_samples: number;
  delivery_samples: number;
  p50_ship_hours: number | null;
  p50_delivery_hours: number | null;
  p90_delivery_hours: number | null;
  ship_sample_insufficient: boolean;
  delivery_sample_insufficient: boolean;
}

export interface TopProduct {
  name: string;
  pieces: number;
  orders: number;
  cancel_rate: number;
}

export interface TrendChannelValue {
  orders: number;
  gmv: GmvSummary;
}

export type TrendChannels = Record<Channel, TrendChannelValue>;

export interface TrendBucket {
  key: string;
  from: string;
  to: string;
  orders: number;
  gmv: GmvSummary;
  channels: TrendChannels;
}

export interface DashboardSummary {
  range: { from: string; to: string };
  granularity: Granularity;
  totals: OverviewTotals;
  channels: OverviewChannel[];
  buckets: TrendBucket[];
  gmv: GmvSummary;
  timeliness: TimelinessOverview[];
  top_products: TopProduct[];
  data_through: string | null;
}

export interface OrderTrend {
  granularity: Granularity;
  from: string;
  to: string;
  buckets: TrendBucket[];
}
