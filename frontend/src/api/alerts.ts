import { request, requestJson } from "./client";
import type {
  AlertCategory,
  AlertEvaluationResponse,
  AlertEventListResponse,
  AlertRule,
  AlertRuleConfig,
  AlertRuleKey,
  AlertSeverity,
  AlertStatus,
  AlertSummary,
  OkResponse,
  ShopId,
  ShopSelection,
} from "../types/api";

export interface AlertEventsQuery {
  shopId?: ShopSelection;
  status?: AlertStatus;
  severity?: AlertSeverity;
  category?: AlertCategory;
  search?: string;
  page?: number;
  size?: number;
}

function queryString(values: AlertEventsQuery): string {
  const query = new URLSearchParams();
  if (values.shopId !== undefined) query.set("shop_id", String(values.shopId));
  if (values.status) query.set("status", values.status);
  if (values.severity) query.set("severity", values.severity);
  if (values.category) query.set("category", values.category);
  if (values.search) query.set("q", values.search);
  if (values.page !== undefined) query.set("page", String(values.page));
  if (values.size !== undefined) query.set("size", String(values.size));
  return query.toString();
}

export function listAlertEvents(values: AlertEventsQuery = {}): Promise<AlertEventListResponse> {
  return request<AlertEventListResponse>(`/api/alerts?${queryString(values)}`);
}

export function getAlertSummary(shopId: ShopSelection): Promise<AlertSummary> {
  return request<AlertSummary>(`/api/alerts/summary?shop_id=${shopId}`);
}

export function listAlertRules(shopId: ShopSelection = 0): Promise<AlertRule[]> {
  return request<AlertRule[]>(`/api/alert-rules?shop_id=${shopId}`);
}

export function acknowledgeAlert(alertId: number): Promise<OkResponse & { id: number }> {
  return request<OkResponse & { id: number }>(`/api/alerts/${alertId}/acknowledge`, { method: "POST" });
}

export function evaluateAlerts(shopId: ShopSelection): Promise<AlertEvaluationResponse> {
  return requestJson<AlertEvaluationResponse>("/api/alerts/evaluate", "POST", { shop_id: shopId });
}

export interface AlertRuleUpdate {
  shop_id: ShopId;
  enabled: boolean;
  notify_dingtalk: boolean;
  config: AlertRuleConfig;
}

export function updateAlertRule(ruleKey: AlertRuleKey, body: AlertRuleUpdate): Promise<AlertRule> {
  return requestJson<AlertRule>(`/api/alert-rules/${encodeURIComponent(ruleKey)}`, "PUT", body);
}
