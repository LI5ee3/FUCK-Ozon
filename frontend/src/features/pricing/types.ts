import type { Channel, ShopId, ShopSelection } from "../../shared/types/common";

export type PricingHealth = "incomplete" | "loss" | "low_margin" | "price_red" | "price_yellow" | "no_price_index" | "healthy";
export type PricingHealthFilter = "" | PricingHealth;
export type PricingSort = "" | "current_price" | "sold_price_30" | "price_vs_30d" | "projected_margin" | "break_even_price" | "target_margin_price" | "sales_30" | "effective_stock" | "price_index";
export type SortOrder = "asc" | "desc";

export interface PricingProduct {
  product_identity: string;
  product_id: string | null;
  offer_id: string | null;
  sku: string | null;
  display_name: string;
  group_id: number | null;
  primary_offer_id: string | null;
}

export interface PricingPrice {
  observed_at: string | null;
  currency: string | null;
  base_price: string | null;
  marketing_seller_price: string | null;
  effective_price: string | null;
  old_price: string | null;
  min_price: string | null;
  auto_action_enabled: boolean | null;
}

export interface PricingSales30 {
  units: number;
  revenue: string | null;
  currency: string | null;
  weighted_avg_price: string | null;
  sold_price_status: string;
  price_vs_30d_pct: number | null;
}

export interface PricingCostBasis {
  status: "available" | "unavailable";
  sku: string | null;
  unit_cost_cny: string | null;
  source_order: string | null;
  updated_at: string | null;
}

export interface PricingEconomics {
  status: "complete" | "incomplete";
  currency: string;
  current_effective_price: string | null;
  unit_cost: string | null;
  sales_commission_pct: number | null;
  sales_commission_field: string;
  acquiring_amount: string | null;
  acquiring_rate: number | null;
  projected_base_profit: string | null;
  projected_base_margin_pct: number | null;
  break_even_price: string | null;
  target_margin_price: string | null;
  incomplete_reasons: string[];
  acquiring_rate_assumption: string;
}

export interface PricingIndexValue {
  min_price: string | null;
  min_price_currency: string | null;
  index: string | null;
}

export interface PricingCompetitiveness {
  color_index: string | null;
  ozon: PricingIndexValue;
  external: PricingIndexValue;
  self_marketplace: PricingIndexValue;
}

export interface PricingStock {
  present: number | null;
  reserved: number | null;
  effective_stock: number | null;
  observed_at: string | null;
}

export interface PricingItem {
  row_key: string;
  shop_id: ShopId;
  shop_name: string;
  product: PricingProduct;
  price: PricingPrice;
  sales_30: PricingSales30;
  cost_basis: PricingCostBasis;
  economics: PricingEconomics;
  competitiveness: PricingCompetitiveness;
  stock: PricingStock;
  health_flags: PricingHealth[];
  primary_health: PricingHealth;
}

export interface PricingSummary {
  products: number;
  economics_ready: number;
  loss: number;
  low_margin: number;
  price_red: number;
  price_yellow: number;
  incomplete: number;
  no_price_index: number;
}

export interface PricingFreshnessShop {
  status: "available" | "missing";
  data_through: string | null;
  source: "sync_run" | "snapshot" | "none";
}

export interface PricingFreshness {
  prices: {
    status: "available" | "missing";
    data_through: string | null;
    shops: Record<string, PricingFreshnessShop>;
  };
  orders: { status: "available" | "missing"; data_through: string | null };
  stock: { status: "available" | "missing"; observed_at: string | null };
  erp_cost: { status: "available" | "missing"; updated_at: string | null };
  exchange_rate: { status: "available" | "missing"; currencies: string[]; sales_exchange_rates: Record<string, string> };
}

export interface PricingResponse {
  as_of: string;
  sales_window: { from: string; to: string; days: 30 };
  reference_channel: Channel;
  target_margin_pct: number;
  freshness: PricingFreshness;
  summary: PricingSummary;
  items: PricingItem[];
  total: number;
  page: number;
  size: number;
}

export interface PricingQuery {
  shopId: ShopSelection;
  q?: string;
  channel: Channel;
  health?: PricingHealthFilter;
  targetMarginPct: number;
  sortBy?: Exclude<PricingSort, "">;
  sortOrder?: SortOrder;
  page: number;
  size: number;
}
