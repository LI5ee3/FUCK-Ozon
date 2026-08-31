import { request, requestJson } from "../../shared/api/client";
import type {
  ProductCostHistoryResponse,
  ProductCostsResponse,
  SaveProductForecastCostPayload,
  SaveProductForecastCostResponse,
} from "./types";

export interface ProductCostsQuery {
  search?: string;
  page?: number;
  size?: number;
}

export function listProductCosts(queryValues: ProductCostsQuery = {}): Promise<ProductCostsResponse> {
  const query = new URLSearchParams();
  if (queryValues.search?.trim()) query.set("q", queryValues.search.trim());
  if (queryValues.page !== undefined) query.set("page", String(queryValues.page));
  if (queryValues.size !== undefined) query.set("size", String(queryValues.size));
  const suffix = query.toString();
  return request<ProductCostsResponse>(`/api/product-costs${suffix ? `?${suffix}` : ""}`);
}

export function saveProductCost(payload: SaveProductForecastCostPayload): Promise<SaveProductForecastCostResponse> {
  return requestJson<SaveProductForecastCostResponse>("/api/product-costs", "PUT", payload);
}

export function listProductCostHistory(sku: string, offerId: string, limit = 100): Promise<ProductCostHistoryResponse> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (sku) query.set("sku", sku);
  if (offerId) query.set("offer_id", offerId);
  return request<ProductCostHistoryResponse>(`/api/product-costs/history?${query}`);
}
