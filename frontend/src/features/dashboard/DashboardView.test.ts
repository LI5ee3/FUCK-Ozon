import { flushPromises, shallowMount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import DashboardView from "./DashboardView.vue";
import type { DashboardSummary, TopProduct } from "./types";

const api = vi.hoisted(() => ({ getDashboardSummary: vi.fn(), getOrderTrend: vi.fn() }));
vi.mock("./api", () => api);
vi.mock("naive-ui", async () => ({
  ...await vi.importActual<typeof import("naive-ui")>("naive-ui"),
  useMessage: () => ({ error: vi.fn() }),
}));

describe("Top Products insights", () => {
  it.each([false, true])("only renders insights when products exist: %s", async (hasProducts) => {
    const products: TopProduct[] = hasProducts ? [{ name: "商品", pieces: 10, orders: 5, cancel_rate: 0 }] : [];
    const summary: DashboardSummary = {
      range: { from: "2026-08-01", to: "2026-08-31" }, granularity: "week",
      totals: { orders: 5, pieces: 10, cancelled_orders: 0, cancelled_pieces: 0, cancel_rate: 0 },
      channels: [], buckets: [], gmv: { amount: 0, currency: "CNY", missing_rate_orders: 0 },
      timeliness: [], top_products: products, data_through: null,
    };
    api.getDashboardSummary.mockResolvedValue(summary);
    api.getOrderTrend.mockResolvedValue({ granularity: "week", buckets: [], from: "", to: "" });
    const wrapper = shallowMount(DashboardView, { global: { renderStubDefaultSlot: true } });
    await flushPromises();
    expect(wrapper.text().includes("榜首爆品销量")).toBe(hasProducts);
    expect(wrapper.text().includes("Top 5 综合取消率")).toBe(hasProducts);
    expect(wrapper.text().includes("履约健康")).toBe(hasProducts);
    expect(wrapper.find('empty-state-stub[title="所选范围暂无商品数据"]').exists()).toBe(!hasProducts);
  });
});
