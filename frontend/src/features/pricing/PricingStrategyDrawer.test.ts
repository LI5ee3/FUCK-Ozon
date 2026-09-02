import { defineComponent, h, type Component } from "vue";
import { flushPromises, shallowMount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PricingStrategyDrawer from "./PricingStrategyDrawer.vue";
import type { PricingItem, PricingStrategyResponse } from "./types";

const api = vi.hoisted(() => ({ getPricingStrategy: vi.fn() }));
vi.mock("./api", () => api);

const SlotStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) { return () => h("div", attrs, [slots.header?.(), slots.default?.()]); },
});
const TagStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) { return () => h("span", attrs, slots.default?.()); },
});
const stubs: Record<string, Component> = {
  NDrawer: SlotStub,
  NDrawerContent: SlotStub,
  NTag: TagStub,
};

const item: PricingItem = {
  row_key: "2:product_id:1",
  shop_id: 2,
  snapshot_key: "product_id:1",
  shop_name: "店铺 2",
  product: {
    product_identity: "offer:O-1", product_id: "1", offer_id: "O-1", sku: "SKU-1",
    display_name: "测试商品", group_id: null, primary_offer_id: "O-1",
  },
  price: { observed_at: "2026-09-01T00:00:00Z", currency: "CNY", base_price: "100", marketing_seller_price: "90", effective_price: "90", old_price: null, min_price: "80", auto_action_enabled: null },
  sales_30: { units: 4, revenue: "700", currency: "CNY", weighted_avg_price: "175", sold_price_status: "available", price_vs_30d_pct: -48.6 },
  cost_basis: { status: "available", sku: "SKU-1", unit_cost_cny: "20", source_order: "P-1", updated_at: "2026-08-31T00:00:00Z" },
  economics: { status: "complete", currency: "CNY", current_effective_price: "90", unit_cost: "20", sales_commission_pct: 10, sales_commission_field: "sales_percent_fbp", acquiring_amount: "3", acquiring_rate: 0.03, projected_base_profit: "58", projected_base_margin_pct: 64, break_even_price: "22", target_margin_price: "31", incomplete_reasons: [], acquiring_rate_assumption: "" },
  competitiveness: { color_index: "GREEN", ozon: { min_price: "80", min_price_currency: "CNY", index: "1" }, external: { min_price: null, min_price_currency: null, index: null }, self_marketplace: { min_price: null, min_price_currency: null, index: null } },
  stock: { present: 8, reserved: 2, effective_stock: 6, observed_at: "2026-09-01T00:00:00Z" },
  health_flags: ["healthy"], primary_health: "healthy",
};

function responseFor(signal: PricingStrategyResponse["strategy"]["signal"] = "hold"): PricingStrategyResponse {
  return {
    as_of: "2026-09-02T04:00:00Z", shop_id: 2, shop_name: "店铺 2", snapshot_key: item.snapshot_key,
    reference_channel: "FBP", target_margin_pct: 20, product: item.product,
    current: { price: item.price, sales_30: item.sales_30, economics: item.economics, competitiveness: item.competitiveness, stock: item.stock },
    strategy: {
      status: "available", signal, currency: "CNY", current_price: "90", break_even_price: "22", target_margin_price: "31", sold_price_30: "175", sold_price_status: "available", market_reference_price: "80",
      observation_range: { status: signal === "margin_market_conflict" ? "conflict" : "available", lower: signal === "margin_market_conflict" ? null : "31", upper: signal === "margin_market_conflict" ? null : "80" },
      market_sources: {
        ozon: { price: "80", currency: "CNY", converted_price: "80", converted_currency: "CNY", status: "available" },
        external: { price: null, currency: null, converted_price: null, converted_currency: "CNY", status: "missing_price" },
        self_marketplace: { price: null, currency: null, converted_price: null, converted_currency: "CNY", status: "missing_price" },
      },
      reason_codes: [], warnings: [],
    },
    history: { days: 90, from: "2026-06-03T00:00:00Z", to: "2026-09-01T00:00:00Z", snapshot_count: 3, price_change_count: 1, points: [], events: [{
      observed_at: "2026-08-25T00:00:00Z", previous_observed_at: "2026-08-24T00:00:00Z", event_day: "2026-08-25", previous_currency: "CNY", currency: "CNY", types: ["effective_price_changed"], changes: { effective_price: { from: "90", to: "80" } }, effective_price_change_pct: -11.1, price_change_status: "available", impact: null,
    }] },
  };
}

let mounted: VueWrapper[] = [];

beforeEach(() => {
  vi.clearAllMocks();
  api.getPricingStrategy.mockResolvedValue(responseFor());
});

afterEach(() => {
  mounted.forEach((wrapper) => wrapper.unmount());
  mounted = [];
});

async function mountDrawer(data = responseFor()): Promise<VueWrapper> {
  api.getPricingStrategy.mockResolvedValue(data);
  const wrapper = shallowMount(PricingStrategyDrawer, {
    props: { show: true, item, channel: "FBP", targetMarginPct: 20 },
    global: { stubs },
  });
  mounted.push(wrapper);
  await flushPromises();
  return wrapper;
}

describe("PricingStrategyDrawer", () => {
  it("requests and renders strategy anchors, history, and both disclaimers", async () => {
    const wrapper = await mountDrawer();
    expect(api.getPricingStrategy).toHaveBeenCalledWith({ shopId: 2, snapshotKey: "product_id:1", channel: "FBP", targetMarginPct: 20, historyDays: 90 });
    expect(wrapper.text()).toContain("hold");
    expect(wrapper.text()).toContain("当前测算售价");
    expect(wrapper.text()).toContain("基础保本价");
    expect(wrapper.text()).toContain("目标毛利价");
    expect(wrapper.text()).toContain("市场参考");
    expect(wrapper.text()).toContain("30天成交均价");
    expect(wrapper.text()).toContain("价格观察区间");
    expect(wrapper.text()).toContain("价格历史");
    expect(wrapper.text()).toContain("价格事件前后销售变化仅为历史事实对比，不代表价格变化与销量变化存在因果关系。");
    expect(wrapper.text()).toContain("策略结果仅用于经营决策辅助，不会自动修改 Ozon 商品价格。");
    expect(wrapper.text()).not.toMatch(/修改价格|应用价格|执行调价|自动调价/);
  });

  it("renders conflict and pending states without fake after-window changes", async () => {
    const conflict = responseFor("margin_market_conflict");
    const wrapper = await mountDrawer(conflict);
    expect(wrapper.text()).toContain("margin_market_conflict");
    expect(wrapper.text()).toContain("暂无兼顾目标毛利与当前市场参考的价格观察区间");

    const pending = responseFor();
    pending.history.events[0].impact = {
      status: "pending", before: null, after: null, units_delta: null, units_change_pct: null,
      revenue_delta: null, revenue_change_pct: null, weighted_avg_price_change_pct: null,
      reason: "after_window_incomplete",
    };
    const pendingWrapper = await mountDrawer(pending);
    expect(pendingWrapper.text()).toContain("后 7 日观察窗口尚未完成");
    expect(pendingWrapper.text()).not.toContain("销量 +");

    const insufficient = responseFor("insufficient_data");
    insufficient.strategy.market_reference_price = null;
    insufficient.strategy.observation_range = { status: "unavailable", lower: null, upper: null };
    const insufficientWrapper = await mountDrawer(insufficient);
    expect(insufficientWrapper.text()).toContain("insufficient_data");
    expect(insufficientWrapper.text()).toContain("核心价格数据不足");
  });
});
