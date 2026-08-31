import { request } from "../../shared/api/client";

export interface ProductCommission {
  shop_id: number;
  sku: string;
  offer_id: string;
  product_id: number | string;
  sales_percent_fbp: number | null;
  sales_percent_rfbs: number | null;
  fetched_at: string;
}

export function getProductCommission(shopId: number, sku: string): Promise<ProductCommission> {
  const query = new URLSearchParams({ shop_id: String(shopId), sku });
  return request<ProductCommission>(`/api/product-commission?${query}`);
}
