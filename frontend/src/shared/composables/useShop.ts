import { computed, ref } from "vue";
import { listShops } from "../api/shops";
import type { Shop, ShopSelection } from "../types/common";

const shops = ref<Shop[]>([]);
const selectedShopId = ref<ShopSelection>(0);
const options = computed(() => [
  { label: "两店铺合并", value: 0 },
  ...shops.value.map((shop) => ({ label: shop.name, value: shop.id })),
]);

export function useShop() {
  async function load(): Promise<void> {
    shops.value = await listShops();
  }

  function selectShop(value: string | number | null): void {
    if (value === 0 || value === "0") selectedShopId.value = 0;
    if (value === 1 || value === "1") selectedShopId.value = 1;
    if (value === 2 || value === "2") selectedShopId.value = 2;
  }

  return { shops, selectedShopId, options, load, selectShop };
}
