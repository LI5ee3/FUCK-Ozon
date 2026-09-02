import { request } from "../../shared/api/client";
import type { PricingResponse, PricingQuery, PricingStrategyQuery, PricingStrategyResponse } from "./types";

export function listPricing(values: PricingQuery): Promise<PricingResponse> {
  const query = new URLSearchParams({
    shop_id: String(values.shopId),
    channel: values.channel,
    target_margin_pct: String(values.targetMarginPct),
    page: String(values.page),
    size: String(values.size),
  });
  if (values.q?.trim()) query.set("q", values.q.trim());
  if (values.health) query.set("health", values.health);
  if (values.sortBy) query.set("sort_by", values.sortBy);
  if (values.sortOrder) query.set("sort_order", values.sortOrder);
  return request<PricingResponse>(`/api/pricing?${query}`);
}

export function getPricingStrategy(values: PricingStrategyQuery): Promise<PricingStrategyResponse> {
  const query = new URLSearchParams({
    shop_id: String(values.shopId),
    snapshot_key: values.snapshotKey,
    channel: values.channel,
    target_margin_pct: String(values.targetMarginPct),
    history_days: String(values.historyDays),
  });
  return request<PricingStrategyResponse>(`/api/pricing/strategy?${query}`);
}
