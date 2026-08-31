import type { ShopId } from "../../shared/types/common";

export type SyncModule = "orders" | "returns" | "stock";
export type ManualSyncModule = SyncModule | "ad_campaigns" | "ad_campaign_daily" | "ad_sku_daily";
export type AutoSyncModule = SyncModule | "ad_campaign_daily" | "ad_sku_daily";

export interface SyncRun {
  id: number;
  shop_id: ShopId;
  shop_name: string;
  module: string;
  range_from: string;
  range_to: string;
  status: string;
  progress_total: number;
  progress_done: number;
  records: number;
  data_through: string | null;
  current_from: string | null;
  current_to: string | null;
  run_source: string | null;
  scheduled_slot: string | null;
  started_at: string;
  finished_at: string | null;
  error: string | null;
}

export interface SyncTaskResponse {
  run_id: number;
  status: string;
  progress_total: number;
}

export interface PerformanceSyncResponse {
  shop_id: ShopId;
  success: boolean;
  fetched: number;
  inserted_or_updated: number;
  run_id?: number;
}

export interface PerformanceStatisticsBreakdown {
  fetched: number;
  inserted_or_updated: number;
  dates?: string[];
}

export interface PerformanceStatisticsSyncResponse extends PerformanceSyncResponse {
  date_from: string;
  date_to: string;
  campaign_daily: PerformanceStatisticsBreakdown;
  sku: PerformanceStatisticsBreakdown;
  sku_skipped_dates?: string[];
}

export interface AutoSyncSetting {
  shop_id: ShopId;
  module: AutoSyncModule;
  enabled: number;
  interval_hours: number;
  range_days: number;
}

export interface AutoSyncSettingValue {
  enabled: boolean;
  interval_hours: number;
  range_days: number;
}

export type AutoSyncSettingsPayload = Record<"1" | "2", Record<AutoSyncModule, AutoSyncSettingValue>>;

export interface ExchangeRate {
  service_penalty_exchange_rate: string;
  sales_exchange_rate: string;
  valid_from_utc: string;
  valid_to_utc: string;
  from_currency?: string;
  to_currency?: string;
  source?: string;
  fetched_at?: string;
}

export interface ExchangeRateStatus {
  source: string;
  last_success_at: string | null;
  data_through: string | null;
  rates: Record<string, ExchangeRate | null>;
}

export interface ExchangeRateSyncResponse {
  records: number;
  segments: number;
  data_through: string;
}
