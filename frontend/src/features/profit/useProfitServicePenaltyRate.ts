import { onBeforeUnmount, ref } from "vue";
import { getErrorMessage } from "../../shared/api/client";
import { getCurrentServicePenaltyExchangeRates, type CurrentServicePenaltyExchangeRates } from "./servicePenalty";

function validRate(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const rate = value as Record<string, unknown>;
  const number = Number(rate.service_penalty_exchange_rate);
  return typeof rate.service_penalty_exchange_rate === "string"
    && rate.service_penalty_exchange_rate.trim() !== ""
    && Number.isFinite(number) && number > 0
    && typeof rate.valid_from_utc === "string" && rate.valid_from_utc.trim() !== ""
    && typeof rate.valid_to_utc === "string" && rate.valid_to_utc.trim() !== "";
}

function isUsableResponse(value: unknown): value is CurrentServicePenaltyExchangeRates {
  if (!value || typeof value !== "object") return false;
  const response = value as Record<string, unknown>;
  const rates = response.rates;
  if (!rates || typeof rates !== "object") return false;
  const rateMap = rates as Record<string, unknown>;
  return response.source === "ozon_xapi"
    && typeof response.as_of === "string" && response.as_of.trim() !== ""
    && (rateMap.USD === null || validRate(rateMap.USD))
    && (rateMap.CNY === null || validRate(rateMap.CNY))
    && (response.error === undefined || typeof response.error === "string");
}

export function useProfitServicePenaltyRate() {
  const rates = ref<CurrentServicePenaltyExchangeRates | null>(null);
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
      const result = await getCurrentServicePenaltyExchangeRates();
      if (!isUsableResponse(result)) throw new Error("Ozon服务和罚款汇率响应格式无效");
      if (currentRequest !== requestId) return;
      rates.value = result;
      error.value = result.error ?? "";
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
