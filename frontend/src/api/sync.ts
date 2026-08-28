import { request, requestJson } from "./client";
import type {
  AutoSyncSetting,
  AutoSyncSettingsPayload,
  ExchangeRateStatus,
  ExchangeRateSyncResponse,
  ManualSyncModule,
  PerformanceStatisticsSyncResponse,
  PerformanceSyncResponse,
  ShopId,
  SyncModule,
  SyncRun,
  SyncTaskResponse,
} from "../types/api";

export function getSyncRuns(): Promise<SyncRun[]> {
  return request<SyncRun[]>("/api/sync");
}

export function getSyncRun(runId: number): Promise<SyncRun> {
  return request<SyncRun>(`/api/sync/${runId}`);
}

export function startSync(module: SyncModule, shopId: ShopId, from: string, to: string): Promise<SyncTaskResponse> {
  const query = new URLSearchParams({ shop_id: String(shopId) });
  return requestJson<SyncTaskResponse>(`/api/sync/${module}?${query}`, "POST", { from, to });
}

export function syncPerformanceCampaigns(shopId: ShopId): Promise<PerformanceSyncResponse> {
  return requestJson<PerformanceSyncResponse>("/api/performance/campaigns/sync", "POST", {
    shop_id: shopId,
  });
}

export function syncPerformanceStatistics(
  shopId: ShopId,
  from: string,
  to: string,
  module: Extract<ManualSyncModule, "ad_campaign_daily" | "ad_sku_daily">,
): Promise<PerformanceStatisticsSyncResponse> {
  return requestJson<PerformanceStatisticsSyncResponse>("/api/performance/statistics/sync", "POST", {
    shop_id: shopId,
    date_from: from,
    date_to: to,
    module,
  });
}

export function getAutoSyncSettings(): Promise<AutoSyncSetting[]> {
  return request<AutoSyncSetting[]>("/api/auto-sync-settings");
}

export function updateAutoSyncSettings(payload: AutoSyncSettingsPayload): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>("/api/auto-sync-settings", "PUT", payload);
}

export function getExchangeRateStatus(): Promise<ExchangeRateStatus> {
  return request<ExchangeRateStatus>("/api/exchange-rates");
}

export function syncExchangeRates(from: string, to: string): Promise<ExchangeRateSyncResponse> {
  return requestJson<ExchangeRateSyncResponse>("/api/exchange-rates/sync", "POST", { from, to });
}
