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

vi.mock("../product-costs/api", () => api);

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
  sku: "1936515175", offer_id: "WGMFR265C46BL", forecast_cost: usdCost, configured: true,
  updated_at: usdCost.updated_at, conflict: false, conflict_message: null,
};
const cnyRow: ProductCostRow = {
  ...usdRow, product_identity: "OFFER-CNY", display_name: "人民币商品", ozon_skus: ["1936515176"], offer_ids: ["WGMFR265C46GR"],
  sku: "1936515176", offer_id: "WGMFR265C46GR", forecast_cost: cnyCost, updated_at: cnyCost.updated_at,
};
const unconfiguredRow: ProductCostRow = {
  ...usdRow, product_identity: "OFFER-EMPTY", display_name: "未配置商品", ozon_skus: ["1936515177"], offer_ids: ["WGMFR265C46RD"],
  sku: "1936515177", offer_id: "WGMFR265C46RD", forecast_cost: null, configured: false, updated_at: null,
};
const conflictRow: ProductCostRow = {
  ...unconfiguredRow, product_identity: null, display_name: "冲突商品", ozon_skus: ["1936515178"], offer_ids: ["WGMFR265C46BK"],
  sku: "1936515178", offer_id: "WGMFR265C46BK", conflict: true, conflict_message: "商品匹配规则存在冲突",
};
const products = [usdRow, cnyRow, unconfiguredRow, conflictRow];

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

    await numberInput(wrapper, "采购成本").vm.$emit("update:value", 65);
    await nextTick();
    expect(wrapper.text()).toContain("手工覆盖 · 基于 SKU 成本库");
    expect(wrapper.text()).toContain("¥468.00");
    expect(api.saveProductCost).not.toHaveBeenCalled();

    await productSelect(wrapper).vm.$emit("update:value", "OFFER-CNY");
    await nextTick();
    expect(numberInput(wrapper, "采购成本").props("value")).toBe(400);
    expect(wrapper.findAllComponents(SelectStub).find((component) => component.attributes("aria-label") === "采购币种")!.props("value")).toBe("CNY");
    expect(numberInput(wrapper, "重量克数").props("value")).toBe(100);
    expect(numberInput(wrapper, "包装成本 CNY").props("value")).toBe(0);
    expect(numberInput(wrapper, "其他成本 CNY").props("value")).toBe(0);
    expect(wrapper.text()).toContain("SKU 成本库");
    expect(api.listProductCostHistory).not.toHaveBeenCalled();
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
    await productSelect(wrapper).vm.$emit("update:value", "conflict:1936515178:WGMFR265C46BK");
    await nextTick();
    expect(wrapper.text()).toContain("商品匹配规则存在冲突，请先处理商品匹配规则");
    expect(numberInput(wrapper, "采购成本").props("value")).toBe(null);

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
