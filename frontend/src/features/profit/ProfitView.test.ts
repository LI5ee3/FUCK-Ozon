import { defineComponent, h, nextTick, type Component } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { flushPromises, shallowMount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProfitView from "./ProfitView.vue";
import type { ProductCostRow } from "../product-costs/types";

const api = vi.hoisted(() => ({
  listProductCosts: vi.fn(),
  saveProductCost: vi.fn(),
  listProductCostHistory: vi.fn(),
}));
const commissionApi = vi.hoisted(() => ({ getProductCommission: vi.fn() }));

vi.mock("../product-costs/api", () => api);
vi.mock("./commission", () => commissionApi);

const usdCost = {
  id: 1,
  product_identity: "OFFER-USD",
  purchase_cost: 60,
  purchase_currency: "USD" as const,
  weight_grams: 200,
  length_cm: 10,
  width_cm: 5,
  height_cm: 3,
  packing_cost_cny: 2,
  other_cost_cny: 1,
  note: "美元成本备注",
  created_at: "2026-08-30T00:00:00Z",
  updated_at: "2026-08-31T00:00:00Z",
};
const cnyCost = { ...usdCost, id: 2, product_identity: "OFFER-CNY", purchase_cost: 400, purchase_currency: "CNY" as const, weight_grams: 100, packing_cost_cny: 0, other_cost_cny: 0 };
const usdRow: ProductCostRow = {
  product_identity: "OFFER-USD", display_name: "美元商品", ozon_skus: ["1936515175"], offer_ids: ["WGMFR265C46BL"],
  listings: [
    { shop_id: 1, sku: "1936515175", offer_id: "WGMFR265C46BL" },
    { shop_id: 2, sku: "3017433550", offer_id: "WGMFR265C46BL" },
  ],
  sku: "1936515175", offer_id: "WGMFR265C46BL", forecast_cost: usdCost, configured: true,
  updated_at: usdCost.updated_at, conflict: false, conflict_message: null,
};
const cnyRow: ProductCostRow = {
  ...usdRow, product_identity: "OFFER-CNY", display_name: "人民币商品", ozon_skus: ["1936515176"], offer_ids: ["WGMFR265C46GR"],
  listings: [{ shop_id: 1, sku: "1936515176", offer_id: "WGMFR265C46GR" }],
  sku: "1936515176", offer_id: "WGMFR265C46GR", forecast_cost: cnyCost, updated_at: cnyCost.updated_at,
};
const unconfiguredRow: ProductCostRow = {
  ...usdRow, product_identity: "OFFER-EMPTY", display_name: "未配置商品", ozon_skus: ["1936515177"], offer_ids: ["WGMFR265C46RD"],
  listings: [{ shop_id: 1, sku: "1936515177", offer_id: "WGMFR265C46RD" }],
  sku: "1936515177", offer_id: "WGMFR265C46RD", forecast_cost: null, configured: false, updated_at: null,
};
const conflictRow: ProductCostRow = {
  ...unconfiguredRow, product_identity: null, display_name: "冲突商品", ozon_skus: ["1936515178"], offer_ids: ["WGMFR265C46BK"],
  sku: "1936515178", offer_id: "WGMFR265C46BK", conflict: true, conflict_message: "商品匹配规则存在冲突",
};
const multiRow: ProductCostRow = {
  ...usdRow, product_identity: "OFFER-MULTI", display_name: "多SKU商品", ozon_skus: ["1936515180", "1936515181"],
  offer_ids: ["WGMFR265C46M1", "WGMFR265C46M2"],
  listings: [
    { shop_id: 1, sku: "1936515180", offer_id: "WGMFR265C46M1" },
    { shop_id: 1, sku: "1936515181", offer_id: "WGMFR265C46M2" },
  ],
  sku: "1936515180", offer_id: "WGMFR265C46M1", forecast_cost: { ...usdCost, id: 3, product_identity: "OFFER-MULTI" },
};
const products = [usdRow, cnyRow, unconfiguredRow, conflictRow, multiRow];

const SlotStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h("div", attrs, [slots.header?.(), slots.icon?.(), slots.default?.()]);
  },
});
const ButtonStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h("button", attrs, [slots.icon?.(), slots.default?.()]);
  },
});
const NumberInputStub = defineComponent({
  inheritAttrs: false,
  props: { value: { type: [String, Number], default: null } },
  emits: ["update:value"],
  setup(props, { attrs, emit }) {
    return () => h("input", {
      ...attrs,
      value: props.value ?? "",
      onInput: (event: Event) => {
        const value = (event.target as HTMLInputElement).value;
        emit("update:value", value === "" ? null : Number(value));
      },
    });
  },
});
const SelectStub = defineComponent({
  inheritAttrs: false,
  props: { value: { type: [String, Number], default: null }, options: { type: Array, default: () => [] } },
  emits: ["update:value", "search", "clear"],
  setup(props, { attrs }) {
    return () => h("div", { ...attrs, "data-value": props.value ?? "" }, (props.options as Array<{ label: string }>).map((option) => h("span", option.label)));
  },
});

const stubs: Record<string, Component> = {
  Alert: SlotStub,
  Button: ButtonStub,
  Card: SlotStub,
  InputNumber: NumberInputStub,
  Select: SelectStub,
  Tag: SlotStub,
};

async function mountProfit(): Promise<VueWrapper> {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/product-costs", component: { template: "<div />" } }] });
  await router.push("/product-costs");
  return shallowMount(ProfitView, { global: { plugins: [router], stubs } });
}

function productSelect(wrapper: VueWrapper) {
  return wrapper.findAllComponents(SelectStub).find((component) => component.attributes("data-testid") === "profit-product-select")!;
}

function numberInput(wrapper: VueWrapper, label: string) {
  return wrapper.findAllComponents(NumberInputStub).find((component) => component.attributes("aria-label") === label)!;
}

function selectInput(wrapper: VueWrapper, label: string) {
  return wrapper.findAllComponents(SelectStub).find((component) => component.attributes("aria-label") === label)!;
}

async function search(wrapper: VueWrapper, query: string): Promise<void> {
  await productSelect(wrapper).vm.$emit("search", query);
  await vi.advanceTimersByTimeAsync(300);
  await flushPromises();
}

describe("ProfitView forecast-cost integration", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    api.listProductCosts.mockResolvedValue({ items: products, total: products.length, page: 1, size: 50 });
    commissionApi.getProductCommission.mockImplementation((shopId: number, sku: string) => {
      const listing = products.flatMap((row) => row.listings).find((item) => item.shop_id === shopId && item.sku === sku);
      return Promise.resolve({
        shop_id: shopId,
        sku,
        offer_id: listing?.offer_id ?? "UNKNOWN",
        product_id: 123,
        sales_percent_fbp: 15,
        sales_percent_rfbs: 12,
        fetched_at: "2026-08-31T08:00:00Z",
      });
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("remotely searches by name, Ozon SKU and offer_id without loading all products", async () => {
    const wrapper = await mountProfit();
    expect(api.listProductCosts).not.toHaveBeenCalled();
    for (const query of ["美元商品", "1936515175", "WGMFR265C46BL"]) await search(wrapper, query);
    expect(api.listProductCosts.mock.calls.map(([query]) => query)).toEqual([
      { search: "美元商品", page: 1, size: 50 },
      { search: "1936515175", page: 1, size: 50 },
      { search: "WGMFR265C46BL", page: 1, size: 50 },
    ]);
  });

  it("loads current USD/CNY forecast parameters, marks overrides, resets on switch, and never persists", async () => {
    const wrapper = await mountProfit();
    await search(wrapper, "商品");
    await productSelect(wrapper).vm.$emit("update:value", "OFFER-USD");
    await nextTick();
    await flushPromises();
    expect(numberInput(wrapper, "采购成本").props("value")).toBe(60);
    expect(numberInput(wrapper, "重量克数").props("value")).toBe(200);
    expect(numberInput(wrapper, "包装成本 CNY").props("value")).toBe(2);
    expect(numberInput(wrapper, "其他成本 CNY").props("value")).toBe(1);
    expect(wrapper.text()).toContain("SKU 成本库");
    expect(wrapper.text()).toContain("¥432.00");
    expect(wrapper.text()).toContain("WGMFR265C46BL");
    expect(wrapper.text()).toContain("1936515175");
    expect(wrapper.text()).toContain("10 × 5 × 3 cm");
    expect(wrapper.text()).toContain("美元成本备注");

    await numberInput(wrapper, "平台售价").vm.$emit("update:value", 100);
    await nextTick();
    expect(commissionApi.getProductCommission).toHaveBeenCalledWith(1, "1936515175");
    expect(wrapper.text()).toContain("平台佣金：FBP 15% · realFBS 12%");
    expect(wrapper.text()).toContain("¥108.00");

    await numberInput(wrapper, "采购成本").vm.$emit("update:value", 65);
    await nextTick();
    expect(wrapper.text()).toContain("手工覆盖 · 基于 SKU 成本库");
    expect(wrapper.text()).toContain("¥468.00");
    expect(api.saveProductCost).not.toHaveBeenCalled();

    await productSelect(wrapper).vm.$emit("update:value", "OFFER-CNY");
    await nextTick();
    await flushPromises();
    expect(numberInput(wrapper, "采购成本").props("value")).toBe(400);
    expect(wrapper.findAllComponents(SelectStub).find((component) => component.attributes("aria-label") === "采购币种")!.props("value")).toBe("CNY");
    expect(numberInput(wrapper, "重量克数").props("value")).toBe(100);
    expect(numberInput(wrapper, "包装成本 CNY").props("value")).toBe(0);
    expect(numberInput(wrapper, "其他成本 CNY").props("value")).toBe(0);
    expect(wrapper.text()).toContain("SKU 成本库");
    expect(api.listProductCostHistory).not.toHaveBeenCalled();
  });

  it("uses one fetched commission response for FBP and realFBS and never lets API price replace the simulation price", async () => {
    const wrapper = await mountProfit();
    await search(wrapper, "美元商品");
    await productSelect(wrapper).vm.$emit("update:value", "OFFER-USD");
    await nextTick();
    await flushPromises();
    await numberInput(wrapper, "平台售价").vm.$emit("update:value", 100);
    await nextTick();
    expect(wrapper.text()).toContain("¥108.00");
    expect(commissionApi.getProductCommission).toHaveBeenCalledTimes(1);

    await selectInput(wrapper, "履约模式").vm.$emit("update:value", "realFBS");
    await nextTick();
    expect(wrapper.text()).toContain("¥86.40");
    expect(commissionApi.getProductCommission).toHaveBeenCalledTimes(1);

    await selectInput(wrapper, "realFBS 发货渠道").vm.$emit("update:value", "shenzhen");
    await nextTick();
    expect(wrapper.text()).toContain("¥86.40");
    expect(commissionApi.getProductCommission).toHaveBeenCalledTimes(1);

    await numberInput(wrapper, "平台售价").vm.$emit("update:value", 92);
    await nextTick();
    expect(numberInput(wrapper, "平台售价").props("value")).toBe(92);
    expect(wrapper.text()).toContain("¥79.49");
    expect(commissionApi.getProductCommission).toHaveBeenCalledTimes(1);
  });

  it("requires an explicit Ozon SKU for multiple current-shop listings and uses shop plus SKU for the request", async () => {
    const wrapper = await mountProfit();
    await search(wrapper, "多SKU商品");
    await productSelect(wrapper).vm.$emit("update:value", "OFFER-MULTI");
    await nextTick();
    expect(wrapper.text()).toContain("当前店铺存在多个 Ozon SKU，请选择平台商品");
    const platformOptions = selectInput(wrapper, "平台商品 Ozon SKU").props("options") as Array<{ label: string }>;
    expect(platformOptions.map((option) => option.label)).toEqual([
      "1936515180 · WGMFR265C46M1",
      "1936515181 · WGMFR265C46M2",
    ]);
    expect(commissionApi.getProductCommission).not.toHaveBeenCalled();

    await selectInput(wrapper, "平台商品 Ozon SKU").vm.$emit("update:value", "1936515181");
    await nextTick();
    await flushPromises();
    expect(commissionApi.getProductCommission).toHaveBeenCalledWith(1, "1936515181");
    expect(wrapper.text()).toContain("1936515181 · WGMFR265C46M2");
  });

  it("switches listing and commission when the shop changes, then hits the session cache when switching back", async () => {
    const wrapper = await mountProfit();
    await search(wrapper, "美元商品");
    await productSelect(wrapper).vm.$emit("update:value", "OFFER-USD");
    await nextTick();
    await flushPromises();
    expect(commissionApi.getProductCommission).toHaveBeenLastCalledWith(1, "1936515175");

    await selectInput(wrapper, "利润测算店铺").vm.$emit("update:value", 2);
    await nextTick();
    await flushPromises();
    expect(wrapper.findAllComponents(SelectStub).some((component) => component.attributes("aria-label") === "平台商品 Ozon SKU")).toBe(false);
    expect(commissionApi.getProductCommission).toHaveBeenLastCalledWith(2, "3017433550");
    expect(commissionApi.getProductCommission).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("平台商品：3017433550 · WGMFR265C46BL");

    await selectInput(wrapper, "利润测算店铺").vm.$emit("update:value", 1);
    await nextTick();
    await flushPromises();
    expect(commissionApi.getProductCommission).toHaveBeenCalledTimes(2);
    expect(commissionApi.getProductCommission).toHaveBeenLastCalledWith(2, "3017433550");
    expect(wrapper.text()).toContain("平台商品：1936515175 · WGMFR265C46BL");
  });

  it("allows a selected product without a current-shop listing and does not request another shop's commission", async () => {
    const rowWithoutShopListing: ProductCostRow = {
      ...usdRow,
      product_identity: "OFFER-NO-LISTING",
      display_name: "无当前店铺 listing",
      listings: [{ shop_id: 2, sku: "3017433551", offer_id: "WGMFR265C46XX" }],
    };
    api.listProductCosts.mockResolvedValueOnce({ items: [rowWithoutShopListing], total: 1, page: 1, size: 50 });
    const wrapper = await mountProfit();
    await search(wrapper, "无当前店铺 listing");
    await productSelect(wrapper).vm.$emit("update:value", "OFFER-NO-LISTING");
    await nextTick();
    await flushPromises();
    expect(wrapper.text()).toContain("当前店铺未找到该商品的 Ozon listing，无法自动获取平台佣金");
    expect(commissionApi.getProductCommission).not.toHaveBeenCalled();
  });

  it("keeps the page usable but blocks a complete result when Ozon commission fetching fails", async () => {
    commissionApi.getProductCommission.mockRejectedValueOnce(new Error("timeout"));
    const wrapper = await mountProfit();
    await search(wrapper, "美元商品");
    await productSelect(wrapper).vm.$emit("update:value", "OFFER-USD");
    await nextTick();
    await flushPromises();
    await numberInput(wrapper, "平台售价").vm.$emit("update:value", 100);
    await numberInput(wrapper, "采购成本").vm.$emit("update:value", 60);
    await nextTick();
    expect(wrapper.text()).toContain("Ozon 平台佣金获取失败");
    expect(wrapper.text()).toContain("timeout");
    expect(wrapper.text()).toContain("数据不可用");
    expect(wrapper.text()).toContain("无法计算完整预计利润");
    expect(wrapper.text()).not.toContain("¥0.00");
    expect(numberInput(wrapper, "平台售价").props("value")).toBe(100);
  });

  it("ignores an invalid commission response", async () => {
    commissionApi.getProductCommission.mockResolvedValueOnce({
      shop_id: 1,
      sku: "1936515175",
      offer_id: "WGMFR265C46BL",
      product_id: 123,
      sales_percent_fbp: Number.NaN,
      sales_percent_rfbs: 12,
      fetched_at: "2026-08-31T08:00:00Z",
    });
    const wrapper = await mountProfit();
    await search(wrapper, "美元商品");
    await productSelect(wrapper).vm.$emit("update:value", "OFFER-USD");
    await nextTick();
    await flushPromises();
    expect(wrapper.text()).toContain("数据不可用");
  });

  it("ignores a late response for a previous product", async () => {
    let resolveUsd: ((value: unknown) => void) | undefined;
    let resolveCny: ((value: unknown) => void) | undefined;
    commissionApi.getProductCommission.mockImplementationOnce(() => new Promise((resolve) => { resolveUsd = resolve; }));
    commissionApi.getProductCommission.mockImplementationOnce(() => new Promise((resolve) => { resolveCny = resolve; }));
    const wrapper = await mountProfit();
    await search(wrapper, "商品");
    await productSelect(wrapper).vm.$emit("update:value", "OFFER-USD");
    await nextTick();
    await productSelect(wrapper).vm.$emit("update:value", "OFFER-CNY");
    await nextTick();
    resolveCny?.({
      shop_id: 1, sku: "1936515176", offer_id: "WGMFR265C46GR", product_id: 124,
      sales_percent_fbp: 9, sales_percent_rfbs: 8, fetched_at: "2026-08-31T08:00:00Z",
    });
    await flushPromises();
    expect(wrapper.text()).toContain("平台商品：1936515176 · WGMFR265C46GR");
    expect(wrapper.text()).toContain("平台佣金：FBP 9% · realFBS 8%");
    resolveUsd?.({
      shop_id: 1, sku: "1936515175", offer_id: "WGMFR265C46BL", product_id: 123,
      sales_percent_fbp: 15, sales_percent_rfbs: 12, fetched_at: "2026-08-31T08:00:00Z",
    });
    await flushPromises();
    expect(wrapper.text()).toContain("平台商品：1936515176 · WGMFR265C46GR");
    expect(wrapper.text()).toContain("平台佣金：FBP 9% · realFBS 8%");
  });

  it("preserves a valid zero commission as implemented zero cost", async () => {
    commissionApi.getProductCommission.mockResolvedValueOnce({
      shop_id: 1,
      sku: "1936515175",
      offer_id: "WGMFR265C46BL",
      product_id: 123,
      sales_percent_fbp: 0,
      sales_percent_rfbs: 0,
      fetched_at: "2026-08-31T08:00:00Z",
    });
    const wrapper = await mountProfit();
    await search(wrapper, "美元商品");
    await productSelect(wrapper).vm.$emit("update:value", "OFFER-USD");
    await nextTick();
    await flushPromises();
    await numberInput(wrapper, "平台售价").vm.$emit("update:value", 100);
    await nextTick();
    expect(wrapper.text()).toContain("平台佣金：FBP 0% · realFBS 0%");
    expect(wrapper.text()).toContain("平台佣金已接入");
    expect(wrapper.text()).toContain("¥0.00");
  });

  it("allows unconfigured manual mode, blocks conflict auto-load, and preserves unrelated inputs when cleared", async () => {
    const wrapper = await mountProfit();
    await search(wrapper, "商品");
    await productSelect(wrapper).vm.$emit("update:value", "OFFER-EMPTY");
    await nextTick();
    expect(wrapper.text()).toContain("尚未配置 SKU 预测成本");
    expect(wrapper.text()).toContain("前往 SKU 成本");
    expect(numberInput(wrapper, "采购成本").props("value")).toBe(null);

    await numberInput(wrapper, "平台售价").vm.$emit("update:value", 700);
    await numberInput(wrapper, "采购成本").vm.$emit("update:value", 400);
    await nextTick();
    const commissionRequestsBeforeConflict = commissionApi.getProductCommission.mock.calls.length;
    await productSelect(wrapper).vm.$emit("update:value", "conflict:1936515178:WGMFR265C46BK");
    await nextTick();
    expect(wrapper.text()).toContain("商品匹配规则存在冲突，请先处理商品匹配规则");
    expect(numberInput(wrapper, "采购成本").props("value")).toBe(null);
    expect(commissionApi.getProductCommission).toHaveBeenCalledTimes(commissionRequestsBeforeConflict);

    await productSelect(wrapper).vm.$emit("clear");
    await nextTick();
    expect(wrapper.text()).toContain("预测参数：纯手工测算");
    expect(numberInput(wrapper, "采购成本").props("value")).toBe(null);
    expect(numberInput(wrapper, "平台售价").props("value")).toBe(700);
  });

  it("keeps manual calculation available after search failure and rejects invalid forecast data", async () => {
    const invalidRow = { ...usdRow, product_identity: "OFFER-BAD", display_name: "异常商品", forecast_cost: { ...usdCost, purchase_cost: Number.NaN } } as ProductCostRow;
    api.listProductCosts.mockResolvedValueOnce({ items: [invalidRow], total: 1, page: 1, size: 50 });
    const wrapper = await mountProfit();
    await search(wrapper, "异常商品");
    await productSelect(wrapper).vm.$emit("update:value", "OFFER-BAD");
    await nextTick();
    expect(wrapper.text()).toContain("SKU 成本数据异常");
    expect(numberInput(wrapper, "采购成本").props("value")).toBe(null);

    api.listProductCosts.mockRejectedValueOnce(new Error("网络失败"));
    await search(wrapper, "网络失败");
    expect(wrapper.text()).toContain("仍可继续手工测算");
    await numberInput(wrapper, "平台售价").vm.$emit("update:value", 700);
    await numberInput(wrapper, "采购成本").vm.$emit("update:value", 400);
    await nextTick();
    expect(wrapper.text()).toContain("预计利润");
    expect(api.saveProductCost).not.toHaveBeenCalled();
    expect(api.listProductCostHistory).not.toHaveBeenCalled();
  });
});
