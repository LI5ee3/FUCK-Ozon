export type ForecastCurrency = "USD" | "CNY";

export interface ProductForecastCost {
  id: number;
  product_identity: string;
  purchase_cost: number;
  purchase_currency: ForecastCurrency;
  weight_grams: number | null;
  length_cm: number | null;
  width_cm: number | null;
  height_cm: number | null;
  packing_cost_cny: number | null;
  other_cost_cny: number | null;
  note: string;
  created_at: string;
  updated_at: string;
}

export interface ProductListing {
  shop_id: number;
  sku: string;
  offer_id: string;
}

export interface ProductCostRow {
  product_identity: string | null;
  display_name: string;
  ozon_skus: string[];
  offer_ids: string[];
  listings: ProductListing[];
  sku: string;
  offer_id: string;
  forecast_cost: ProductForecastCost | null;
  configured: boolean;
  updated_at: string | null;
  conflict: boolean;
  conflict_message: string | null;
}

export interface ProductCostsResponse {
  items: ProductCostRow[];
  total: number;
  page: number;
  size: number;
}

export interface SaveProductForecastCostPayload {
  sku: string;
  offer_id: string;
  purchase_cost: number;
  purchase_currency: ForecastCurrency;
  weight_grams: number | null;
  length_cm: number | null;
  width_cm: number | null;
  height_cm: number | null;
  packing_cost_cny: number | null;
  other_cost_cny: number | null;
  note: string;
  change_note: string;
}

export interface SaveProductForecastCostResponse {
  ok: boolean;
  created: boolean;
  changed: boolean;
  product_identity: string;
  forecast_cost: ProductForecastCost;
}

export interface ProductForecastCostHistory extends Omit<ProductForecastCost, "created_at" | "updated_at" | "id"> {
  id: number;
  change_note: string;
  recorded_at: string;
}

export interface ProductCostHistoryResponse {
  product_identity: string;
  items: ProductForecastCostHistory[];
  total: number;
  limit: number;
}
