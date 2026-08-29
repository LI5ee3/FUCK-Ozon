import { request } from "../../shared/api/client";
import type { RiskReasonsResponse, RiskResponse } from "./types";
import type { ShopSelection } from "../../shared/types/common";

export interface RiskQuery {
  shopId?: ShopSelection;
  from?: string;
  to?: string;
}

export interface RiskReasonQuery extends RiskQuery {
  reason?: string;
}

function queryString(values: RiskQuery): string {
  const query = new URLSearchParams();
  if (values.shopId !== undefined) query.set("shop_id", String(values.shopId));
  if (values.from) query.set("from", values.from);
  if (values.to) query.set("to", values.to);
  return query.toString();
}

export function getRisk(values: RiskQuery = {}): Promise<RiskResponse> {
  return request<RiskResponse>(`/api/risk?${queryString(values)}`);
}

export function getRiskReasons(values: RiskReasonQuery = {}): Promise<RiskReasonsResponse> {
  const query = new URLSearchParams(queryString(values));
  if (values.reason) query.set("reason", values.reason);
  return request<RiskReasonsResponse>(`/api/risk/reasons?${query}`);
}
