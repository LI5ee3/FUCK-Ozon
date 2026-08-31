import { onBeforeUnmount, ref } from "vue";
import { getErrorMessage } from "../../shared/api/client";
import { getProductCommission, type ProductCommission } from "./commission";

function validPercent(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100);
}

function validProductId(value: unknown): value is number | string {
  return (typeof value === "number" && Number.isSafeInteger(value) && value > 0)
    || (typeof value === "string" && /^[0-9]+$/.test(value.trim()) && /[1-9]/.test(value));
}

function isUsableCommission(value: unknown, shopId: number, sku: string): value is ProductCommission {
  if (!value || typeof value !== "object") return false;
  const commission = value as Record<string, unknown>;
  return commission.shop_id === shopId
    && commission.sku === sku
    && typeof commission.offer_id === "string" && commission.offer_id.trim() !== ""
    && validProductId(commission.product_id)
    && validPercent(commission.sales_percent_fbp)
    && validPercent(commission.sales_percent_rfbs)
    && typeof commission.fetched_at === "string" && commission.fetched_at.trim() !== "";
}

export function useProfitCommission() {
  const commission = ref<ProductCommission | null>(null);
  const loading = ref(false);
  const error = ref("");
  const cache = new Map<string, ProductCommission>();
  let requestId = 0;

  function clear(): void {
    requestId += 1;
    commission.value = null;
    loading.value = false;
    error.value = "";
  }

  async function load(shopId: number, sku: string): Promise<void> {
    const key = `${shopId}:${sku}`;
    const currentRequest = ++requestId;
    error.value = "";
    const cached = cache.get(key);
    if (cached) {
      commission.value = cached;
      loading.value = false;
      return;
    }
    commission.value = null;
    loading.value = true;
    try {
      const result = await getProductCommission(shopId, sku);
      if (!isUsableCommission(result, shopId, sku)) throw new Error("Ozon佣金响应格式无效");
      cache.set(key, result);
      if (currentRequest === requestId) commission.value = result;
    } catch (cause) {
      if (currentRequest === requestId) error.value = getErrorMessage(cause);
    } finally {
      if (currentRequest === requestId) loading.value = false;
    }
  }

  onBeforeUnmount(clear);
  return { commission, loading, error, load, clear };
}
