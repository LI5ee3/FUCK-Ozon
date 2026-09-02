import { defineComponent, h, nextTick, type Component, type PropType } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { flushPromises, shallowMount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useShop } from "../../shared/composables/useShop";
import PricingView from "./PricingView.vue";
import type { PricingItem, PricingResponse } from "./types";

const api = vi.hoisted(() => ({ listPricing: vi.fn() }));
vi.mock("./api", () => api);

type TestColumn = { key: string; render?: (row: PricingItem, index: number) => unknown };

const SlotStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h("div", attrs, [slots.header?.(), slots.default?.()]);
  },
});
const ButtonStub = defineComponent({
  inheritAttrs: false,
  props: { attrType: { type: String, default: "button" }, disabled: Boolean },
  setup(props, { attrs, slots }) {
    return () => h("button", { ...attrs, type: props.attrType, disabled: props.disabled }, [slots.icon?.(), slots.default?.()]);
  },
});
const TagStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h("span", attrs, slots.default?.());
  },
});
const SearchFieldStub = defineComponent({
  inheritAttrs: false,
  props: { value: { type: String, default: "" } },
  emits: ["update:value", "clear", "keydown", "debounced-change"],
  setup(props, { attrs, emit }) {
    return () => h("input", {
      ...attrs,
      value: props.value,
      onInput: (event: Event) => emit("update:value", (event.target as HTMLInputElement).value),
      onKeydown: (event: KeyboardEvent) => emit("keydown", event),
    });
  },
});
const SelectStub = defineComponent({
  inheritAttrs: false,
  props: { value: { type: [String, Number], default: "" }, options: { type: Array, default: () => [] } },
  emits: ["update:value"],
  setup(props, { attrs, emit }) {
    return () => h("select", {
      ...attrs,
      value: props.value,
      onChange: (event: Event) => emit("update:value", (event.target as HTMLSelectElement).value),
    });
  },
});
const InputNumberStub = defineComponent({
  inheritAttrs: false,
  props: { value: { type: Number, default: 20 } },
  emits: ["update:value"],
  setup(props, { attrs, emit }) {
    return () => h("input", {
      ...attrs,
      type: "number",
      value: props.value,
      onInput: (event: Event) => emit("update:value", Number((event.target as HTMLInputElement).value)),
    });
  },
});
const PaginationStub = defineComponent({
  inheritAttrs: false,
  props: { page: { type: Number, default: 1 }, disabled: Boolean },
  setup(props, { attrs }) {
    return () => h("button", { ...attrs, type: "button", disabled: props.disabled }, `第 ${props.page} 页`);
  },
});
const EmptyStateStub = defineComponent({
  inheritAttrs: false,
  props: { title: { type: String, default: "" }, hint: { type: String, default: "" } },
  setup(props, { attrs }) {
    return () => h("div", { ...attrs, class: "opanel-empty" }, [h("strong", props.title), props.hint ? h("small", props.hint) : null]);
  },
});
const DataTableStub = defineComponent({
  inheritAttrs: false,
  props: {
    columns: { type: Array as PropType<TestColumn[]>, default: () => [] },
    data: { type: Array as PropType<PricingItem[]>, default: () => [] },
    loading: Boolean,
  },
  setup(props, { attrs, slots }) {
    return () => h("div", { ...attrs, "data-testid": "pricing-table" }, props.loading
      ? h("span", "加载中…")
      : props.data.length
        ? props.data.map((row, index) => h("div", { class: "pricing-test-row" }, props.columns.map((column) => h(
            "div",
            { class: `pricing-test-cell--${column.key}` },
            column.render ? column.render(row, index) as any : undefined,
          ))))
        : slots.empty?.());
  },
});

const stubs: Record<string, Component> = {
  NAlert: SlotStub,
  Alert: SlotStub,
  NButton: ButtonStub,
  Button: ButtonStub,
  NCard: SlotStub,
  Card: SlotStub,
  NDataTable: DataTableStub,
  DataTable: DataTableStub,
  NInputNumber: InputNumberStub,
  InputNumber: InputNumberStub,
  NPagination: PaginationStub,
  Pagination: PaginationStub,
  NSelect: SelectStub,
  Select: SelectStub,
  NTag: TagStub,
  Tag: TagStub,
  EmptyState: EmptyStateStub,
  MorphIcon: SlotStub,
  SearchField: SearchFieldStub,
};

function makeItem(overrides: Partial<PricingItem> = {}): PricingItem {
  return {
    row_key: "2:product_id:1",
    shop_id: 2,
    shop_name: "店铺 2",
    product: {
      product_identity: "offer:O-1",
      product_id: "1",
      offer_id: "O-1",
      sku: "SKU-1",
      display_name: "测试商品",
      group_id: null,
      primary_offer_id: "O-1",
    },
    price: {
      observed_at: "2026-09-01T00:00:00Z",
      currency: "CNY",
      base_price: "100",
      marketing_seller_price: "90",
      effective_price: "90",
      old_price: null,
      min_price: "80",
      auto_action_enabled: null,
    },
    sales_30: {
      units: 4,
      revenue: "700",
      currency: "CNY",
      weighted_avg_price: "175",
      sold_price_status: "available",
      price_vs_30d_pct: -48.6,
    },
    cost_basis: { status: "available", sku: "SKU-1", unit_cost_cny: "20", source_order: "P-1", updated_at: "2026-08-31T00:00:00Z" },
    economics: {
      status: "complete",
      currency: "CNY",
      current_effective_price: "90",
      unit_cost: "20",
      sales_commission_pct: 10,
      sales_commission_field: "sales_percent_fbp",
      acquiring_amount: "3",
      acquiring_rate: 0.0333,
      projected_base_profit: "58",
      projected_base_margin_pct: 64.4,
      break_even_price: "22.03",
      target_margin_price: "31.25",
      incomplete_reasons: [],
      acquiring_rate_assumption: "保本价和目标毛利价测算假设收单手续费比例保持当前水平",
    },
    competitiveness: {
      color_index: "GREEN",
      ozon: { min_price: "80", min_price_currency: "CNY", index: "1" },
      external: { min_price: null, min_price_currency: null, index: null },
      self_marketplace: { min_price: null, min_price_currency: null, index: null },
    },
    stock: { present: 8, reserved: 2, effective_stock: 6, observed_at: "2026-09-01T00:00:00Z" },
    health_flags: ["healthy"],
    primary_health: "healthy",
    ...overrides,
  };
}

function makeResponse(items: PricingItem[], overrides: Partial<PricingResponse> = {}): PricingResponse {
  return {
    as_of: "2026-09-02T04:00:00Z",
    sales_window: { from: "2026-08-03", to: "2026-09-01", days: 30 },
    reference_channel: "FBP",
    target_margin_pct: 20,
    freshness: {
      prices: { status: items.length ? "available" : "missing", data_through: items.length ? "2026-09-01T00:00:00Z" : null, shops: {} },
      orders: { status: "available", data_through: "2026-09-01T00:00:00Z" },
      stock: { status: "available", observed_at: "2026-09-01T00:00:00Z" },
      erp_cost: { status: "available", updated_at: "2026-09-01T00:00:00Z" },
      exchange_rate: { status: "available", currencies: ["CNY"], sales_exchange_rates: { CNY: "2" } },
    },
    summary: { products: items.length, economics_ready: items.length, loss: 0, low_margin: 0, price_red: 0, price_yellow: 0, incomplete: 0, no_price_index: 0 },
    items,
    total: items.length,
    page: 1,
    size: 50,
    ...overrides,
  };
}

let mounted: VueWrapper[] = [];
const { selectedShopId } = useShop();

async function mountPricing(query: Record<string, string> = {}): Promise<{ wrapper: VueWrapper; router: ReturnType<typeof createRouter> }> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/pricing", component: PricingView },
      { path: "/sku/:sku", name: "sku-detail", component: { template: "<div />" } },
    ],
  });
  await router.push({ path: "/pricing", query });
  await router.isReady();
  const wrapper = shallowMount(PricingView, { global: { plugins: [router], stubs } });
  mounted.push(wrapper);
  await flushPromises();
  return { wrapper, router };
}

beforeEach(() => {
  selectedShopId.value = 0;
  vi.clearAllMocks();
  api.listPricing.mockResolvedValue(makeResponse([]));
});

afterEach(() => {
  mounted.forEach((wrapper) => wrapper.unmount());
  mounted = [];
});

describe("PricingView", () => {
  it("renders summary, table, and a SKU 360 link only for a known SKU", async () => {
    api.listPricing.mockResolvedValue(makeResponse([makeItem()]));
    const { wrapper } = await mountPricing();

    expect(wrapper.text()).toContain("价格商品");
    expect(wrapper.text()).toContain("价格分析中心");
    expect(wrapper.find("[data-testid=pricing-table]").exists()).toBe(true);
    expect(wrapper.find(".pricing-sku-link").exists()).toBe(true);
    expect(api.listPricing).toHaveBeenLastCalledWith(expect.objectContaining({ targetMarginPct: 20 }));
    expect(wrapper.text()).not.toMatch(/自动改价|建议涨价|建议降价/);
  });

  it("shows the sync instruction when no price snapshot exists", async () => {
    api.listPricing.mockResolvedValue(makeResponse([], { freshness: {
      prices: { status: "missing", data_through: null, shops: {} },
      orders: { status: "missing", data_through: null },
      stock: { status: "missing", observed_at: null },
      erp_cost: { status: "missing", updated_at: null },
      exchange_rate: { status: "missing", currencies: [], sales_exchange_rates: {} },
    } }));
    const { wrapper } = await mountPricing();
    expect(wrapper.text()).toContain("暂无价格快照，请先在「数据同步中心」同步商品价格。");
  });

  it("sends target margin and reference channel changes to the API", async () => {
    api.listPricing.mockResolvedValue(makeResponse([makeItem()]));
    const { wrapper } = await mountPricing();

    wrapper.findComponent(InputNumberStub).vm.$emit("update:value", 35);
    await flushPromises();
    expect(api.listPricing).toHaveBeenLastCalledWith(expect.objectContaining({ targetMarginPct: 35 }));

    wrapper.findComponent(SelectStub).vm.$emit("update:value", "realFBS");
    await nextTick();
    await flushPromises();
    expect(api.listPricing).toHaveBeenLastCalledWith(expect.objectContaining({ channel: "realFBS" }));
  });

  it("does not create a SKU link when the SKU is ambiguous", async () => {
    api.listPricing.mockResolvedValue(makeResponse([makeItem({ product: { ...makeItem().product, sku: null }, health_flags: ["incomplete"], primary_health: "incomplete" })]));
    const { wrapper } = await mountPricing();
    expect(wrapper.find(".pricing-sku-link").exists()).toBe(false);
    expect(wrapper.text()).toContain("SKU 未明确");
  });
});
