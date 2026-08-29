import { beforeEach, describe, expect, it, vi } from "vitest";
import { useShop } from "./useShop";

const listShops = vi.hoisted(() => vi.fn());
vi.mock("../api/shops", () => ({
  listShops,
  updateShops: vi.fn(),
}));

describe("useShop", () => {
  const shop = useShop();

  beforeEach(() => {
    shop.shops.value = [];
    shop.selectShop(0);
    listShops.mockReset();
  });

  it("loads shop options and accepts only supported selections", async () => {
    listShops.mockResolvedValue([
      { id: 1, name: "店铺一" },
      { id: 2, name: "店铺二" },
    ]);
    await shop.load();
    expect(shop.options.value).toEqual([
      { label: "两店铺合并", value: 0 },
      { label: "店铺一", value: 1 },
      { label: "店铺二", value: 2 },
    ]);

    for (const value of [0, 1, 2] as const) {
      shop.selectShop(value);
      expect(shop.selectedShopId.value).toBe(value);
    }
    shop.selectShop(99);
    shop.selectShop("invalid");
    shop.selectShop(null);
    expect(shop.selectedShopId.value).toBe(2);
  });
});
