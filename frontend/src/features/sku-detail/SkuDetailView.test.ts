import { flushPromises, shallowMount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SkuDetailView from "./SkuDetailView.vue";
import type { SkuDetailResponse } from "./types";
import { beijingToday, shiftDays } from "../../shared/utils/date";

const api = vi.hoisted(() => ({
  getSkuDetail: vi.fn(),
  getSkuTraffic: vi.fn(),
  getSkuQueryDetails: vi.fn(),
}));
vi.mock("./api", () => api);

function coreResponse(): SkuDetailResponse {
  return {
    identity: {
      shop_id: 1,
      shop_name: "店铺一",
      sku: "SKU-1",
      offer_id: "OFFER-1",
      display_name: "商品一",
      product_name_raw: "商品一",
      group_id: null,
      primary_offer_id: null,
    },
    period: { from: "2026-08-01", to: "2026-08-30" },
    sales: {
      status: "available",
      summary: {
        orders: 2, units: 3, revenue: 300, currency: "CNY", revenue_complete: true,
        avg_units_per_day: 0.1, sales_7: 3, sales_15: 3, sales_30: 3, period_days: 30,
      },
      channels: [
        { channel: "FBP", orders: 2, units: 3, revenue: 300, currency: "CNY", revenue_complete: true },
        { channel: "realFBS", orders: 0, units: 0, revenue: 0, currency: "CNY", revenue_complete: true },
        { channel: "WHD", orders: 0, units: 0, revenue: 0, currency: "CNY", revenue_complete: true },
      ],
      trend: [{ date: "2026-08-01", orders: 2, units: 3, revenue: 300, currency: "CNY", revenue_complete: true }],
      data_through: "2026-08-30T00:00:00Z",
    },
    inventory: {
      status: "available", channels: [], fbp_present: 10, fbp_reserved: 1,
      realfbs_present: 0, realfbs_reserved: 0, whd_present: 0, whd_reserved: 0,
      sales_7: 3, sales_15: 3, sales_30: 3, daily_7: 0.4, daily_15: 0.2, daily_30: 0.1,
      forecast_daily: 0.2, trend: "稳定", trend_7_vs_30: 1, days_cover: 50,
      expected_stockout_date: null, lead_time_days: 25, target_cover_days: 60,
      recommended_replenishment: 0, risk_code: "sufficient", risk_status: "库存充足", data_through: null,
    },
    advertising: {
      status: "empty",
      summary: {
        impressions: 0, clicks: 0, cart_adds: 0, spend_rub: 0, orders: 0, revenue_rub: 0,
        ctr: null, avg_cpc_rub: null, drr: null, roas: null, campaign_count: 0, currency: "RUB",
      },
      trend: [], currency: "RUB", ad_order_share: null, data_through: null,
    },
    after_sales: {
      status: "available", orders: 2, cancelled_before_ship: 0, cancel_rate: 0,
      returns: 0, return_orders: 0, return_rate: 0, complaints: 0, complaint_orders: 0,
      complaint_rate: 0, cancel_reasons: [], completeness: {},
    },
    profit: {
      status: "unavailable", candidate_orders: 2, attributed_orders: 0,
      unattributed_multi_sku_orders: 0, incomplete_orders: 0, actual_profit_cny: null,
      avg_profit_per_unit_cny: null, units: 0, currency: "CNY", incomplete_reasons: {},
    },
    signals: [],
    freshness: { orders: null, inventory: null, advertising: null, finance: null, erp_cost: null },
  };
}

describe("SkuDetailView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads Core with an explicit shop and isolates Analytics failures", async () => {
    api.getSkuDetail.mockResolvedValue(coreResponse());
    api.getSkuTraffic.mockRejectedValue(new Error("Analytics unavailable"));
    api.getSkuQueryDetails.mockResolvedValue({ items: [], total: 0, page: 1, size: 20, data_through: "2026-08-27" });
    const analyticsTo = shiftDays(beijingToday(), -3);
    const coreTo = shiftDays(analyticsTo, 2);
    const coreFrom = shiftDays(coreTo, -29);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/sku/:sku", name: "sku-detail", component: SkuDetailView }],
    });
    await router.push(`/sku/SKU-1?shop_id=1&from=${coreFrom}&to=${coreTo}`);
    await router.isReady();
    const wrapper = shallowMount(SkuDetailView, { global: { plugins: [router] } });
    await flushPromises();

    expect(api.getSkuDetail).toHaveBeenCalledWith({ shopId: 1, sku: "SKU-1", from: coreFrom, to: coreTo });
    expect(api.getSkuTraffic).toHaveBeenCalledWith({ shopId: 1, sku: "SKU-1", from: coreFrom, to: analyticsTo });
    expect(api.getSkuQueryDetails).toHaveBeenCalledWith({ shopId: 1, sku: "SKU-1", from: coreFrom, to: analyticsTo }, 1, 20);
    expect(wrapper.text()).toContain("周期销量");
    expect(wrapper.text()).toContain("Analytics unavailable");
    expect(wrapper.text()).not.toContain("SKU 经营详情加载失败");
  });

  it("does not request Analytics when the selected period is entirely newer than T-3", async () => {
    api.getSkuDetail.mockResolvedValue(coreResponse());
    const analyticsTo = shiftDays(beijingToday(), -3);
    const from = shiftDays(analyticsTo, 1);
    const to = shiftDays(analyticsTo, 2);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/sku/:sku", name: "sku-detail", component: SkuDetailView }],
    });
    await router.push(`/sku/SKU-1?shop_id=1&from=${from}&to=${to}`);
    await router.isReady();
    const wrapper = shallowMount(SkuDetailView, { global: { plugins: [router] } });
    await flushPromises();

    expect(api.getSkuDetail).toHaveBeenCalledWith({ shopId: 1, sku: "SKU-1", from, to });
    expect(api.getSkuTraffic).not.toHaveBeenCalled();
    expect(api.getSkuQueryDetails).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("该经营周期暂无可用数据");
  });

  it("does not request Core without an explicit valid shop", async () => {
    for (const query of ["", "?shop_id=0", "?shop_id=abc"]) {
      const router = createRouter({
        history: createMemoryHistory(),
        routes: [{ path: "/sku/:sku", name: "sku-detail", component: SkuDetailView }],
      });
      await router.push(`/sku/SKU-1${query}`);
      await router.isReady();
      const wrapper = shallowMount(SkuDetailView, { global: { plugins: [router] } });
      await flushPromises();
      expect(api.getSkuDetail).not.toHaveBeenCalled();
      expect(wrapper.text()).toContain("请选择具体店铺后查看 SKU 经营详情");
      wrapper.unmount();
    }
  });
});
