import { request, requestJson } from "./client";
import type {
  ProductRuleDeleteShortNamePayload,
  ProductRuleDissolvePayload,
  ProductRuleMergePayload,
  ProductRuleShortNamePayload,
  ProductRulesResponse,
} from "../types/api";

export function getProductRules(search = ""): Promise<ProductRulesResponse> {
  const query = new URLSearchParams();
  if (search.trim()) query.set("q", search.trim());
  const suffix = query.toString();
  return request<ProductRulesResponse>(`/api/product-rules${suffix ? `?${suffix}` : ""}`);
}

export function saveShortName(sku: string, shortName: string): Promise<{ ok: boolean }> {
  const payload: ProductRuleShortNamePayload = { kind: "short_name", sku, short_name: shortName };
  return requestJson<{ ok: boolean }>("/api/product-rules", "PUT", payload);
}

export function deleteShortName(sku: string): Promise<{ ok: boolean }> {
  const payload: ProductRuleDeleteShortNamePayload = { kind: "delete_short_name", sku };
  return requestJson<{ ok: boolean }>("/api/product-rules", "PUT", payload);
}

export function saveMergeGroup(payload: ProductRuleMergePayload): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>("/api/product-rules", "PUT", payload);
}

export function dissolveMergeGroup(id: number): Promise<{ ok: boolean }> {
  const payload: ProductRuleDissolvePayload = { kind: "dissolve", id };
  return requestJson<{ ok: boolean }>("/api/product-rules", "PUT", payload);
}
