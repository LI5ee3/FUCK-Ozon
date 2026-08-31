import { onBeforeUnmount, ref } from "vue";
import { getErrorMessage } from "../../shared/api/client";
import { getExchangeRateStatus } from "../sync/api";
import type { ExchangeRate, ExchangeRateStatus } from "../sync/types";

function validRate(value: unknown): value is ExchangeRate {
  if (!value || typeof value !== "object") return false;
  const rate = value as Record<string, unknown>;
  const serviceRate = Number(rate.service_penalty_exchange_rate);
  const salesRate = Number(rate.sales_exchange_rate);
  return typeof rate.service_penalty_exchange_rate === "string"
    && rate.service_penalty_exchange_rate.trim() !== ""
    && Number.isFinite(serviceRate) && serviceRate > 0
    && (rate.sales_exchange_rate === null
      || (typeof rate.sales_exchange_rate === "string"
        && rate.sales_exchange_rate.trim() !== ""
        && Number.isFinite(salesRate) && salesRate > 0))
    && typeof rate.valid_from_utc === "string" && rate.valid_from_utc.trim() !== ""
    && typeof rate.valid_to_utc === "string" && rate.valid_to_utc.trim() !== "";
}

function isUsableResponse(value: unknown): value is ExchangeRateStatus {
  if (!value || typeof value !== "object") return false;
  const response = value as Record<string, unknown>;
  const rates = response.rates;
  if (!rates || typeof rates !== "object") return false;
  const rateMap = rates as Record<string, unknown>;
  return response.source === "ozon_xapi"
    && (response.last_success_at === null || typeof response.last_success_at === "string")
    && (response.data_through === null || typeof response.data_through === "string")
    && typeof response.as_of === "string" && response.as_of.trim() !== ""
    && (rateMap.USD === null || validRate(rateMap.USD))
    && (rateMap.CNY === null || validRate(rateMap.CNY));
}

export function useProfitServicePenaltyRate() {
  const rates = ref<ExchangeRateStatus | null>(null);
  const loading = ref(false);
  const error = ref("");
  let requestId = 0;
  let loaded = false;

  async function load(): Promise<void> {
    if (loaded || loading.value) return;
    const currentRequest = ++requestId;
    loading.value = true;
    error.value = "";
    try {
      const result = await getExchangeRateStatus();
      if (!isUsableResponse(result)) throw new Error("Ozon服务和罚款汇率响应格式无效");
      if (currentRequest !== requestId) return;
      rates.value = result;
      loaded = true;
    } catch (cause) {
      if (currentRequest === requestId) error.value = getErrorMessage(cause);
    } finally {
      if (currentRequest === requestId) loading.value = false;
    }
  }

  function clear(): void {
    requestId += 1;
    rates.value = null;
    loading.value = false;
    error.value = "";
    loaded = false;
  }

  onBeforeUnmount(clear);
  return { rates, loading, error, load, clear };
}
