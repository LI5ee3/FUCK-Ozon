import type { ShopId } from "../../shared/types/common";

export type AlertStatus = "open" | "resolved" | "all";
export type AlertSeverity = "critical" | "high" | "warning";
export type AlertCategory = "advertising" | "inventory" | "sales";
export type AlertRuleKey =
  | "ad_spend_spike"
  | "ad_drr_high"
  | "ad_clicks_no_orders"
  | "ad_orders_drop"
  | "inventory_risk"
  | "sales_drop";
export type AlertMetricValue = string | number | boolean | null;
export type AlertMetrics = Record<string, AlertMetricValue>;
export type AlertRuleConfig = Record<string, number>;

export interface AlertSummary {
  active: number;
  critical: number;
  high: number;
  warning: number;
  advertising: number;
  inventory: number;
  sales: number;
}

export interface AlertEvent {
  id: number;
  shop_id: ShopId;
  rule_key: AlertRuleKey;
  entity_type: string;
  entity_id: string;
  severity: AlertSeverity;
  title: string;
  message: string;
  first_seen_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  acknowledged_at: string | null;
  last_notified_at: string | null;
  last_notify_error: string | null;
  shop_name: string;
  metrics: AlertMetrics;
  status: Exclude<AlertStatus, "all">;
  rule_label: string;
  category: AlertCategory;
  object_name: string;
}

export interface AlertEventListResponse {
  items: AlertEvent[];
  total: number;
  page: number;
  size: number;
}

export interface AlertRule {
  shop_id: ShopId;
  rule_key: AlertRuleKey;
  enabled: boolean;
  notify_dingtalk: boolean;
  config: AlertRuleConfig;
  updated_at: string | null;
  label: string;
  category: AlertCategory;
}

export interface AlertEvaluationResponse {
  evaluated: number;
  triggered: number;
  updated: number;
  resolved: number;
  notifications_sent: number;
  notifications_failed: number;
  skipped: Array<{ shop_id: ShopId; rule_key: AlertRuleKey; reason: string }>;
}
