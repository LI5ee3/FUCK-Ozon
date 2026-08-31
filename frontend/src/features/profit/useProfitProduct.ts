import { onBeforeUnmount, ref } from "vue";
import { getErrorMessage } from "../../shared/api/client";
import { listProductCosts } from "../product-costs/api";
import type { ProductCostRow } from "../product-costs/types";

const SEARCH_DEBOUNCE_MS = 300;
const SEARCH_PAGE_SIZE = 50;

export function useProfitProduct() {
  const products = ref<ProductCostRow[]>([]);
  const loading = ref(false);
  const error = ref("");
  let timer: ReturnType<typeof setTimeout> | undefined;
  let requestId = 0;

  function search(query: string): void {
    clearTimeout(timer);
    const value = query.trim();
    const currentRequest = ++requestId;
    error.value = "";
    products.value = [];
    if (!value) {
      loading.value = false;
      return;
    }
    loading.value = true;
    timer = setTimeout(async () => {
      timer = undefined;
      try {
        const result = await listProductCosts({ search: value, page: 1, size: SEARCH_PAGE_SIZE });
        if (!Array.isArray(result.items)) throw new Error("商品搜索结果格式无效");
        if (currentRequest === requestId) products.value = result.items;
      } catch (cause) {
        if (currentRequest === requestId) error.value = getErrorMessage(cause);
      } finally {
        if (currentRequest === requestId) loading.value = false;
      }
    }, SEARCH_DEBOUNCE_MS);
  }

  function clear(): void {
    clearTimeout(timer);
    timer = undefined;
    requestId += 1;
    products.value = [];
    loading.value = false;
    error.value = "";
  }

  onBeforeUnmount(clear);
  return { products, loading, error, search, clear };
}
