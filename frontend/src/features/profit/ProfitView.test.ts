import { defineComponent, h, nextTick, type Component, type PropType } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { flushPromises, shallowMount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useShop } from "../../shared/composables/useShop";
import ProfitView from "./ProfitView.vue";
import type { ActualProfitOrder, ActualProfitResponse } from "./types";

const api = vi.hoisted(() => ({ listActualOrderProfits: vi.fn() }));
vi.mock("./api", () => api);

type TestColumn = {
  key: string;
  render?: (row: ActualProfitOrder, index: number) => unknown;
};

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
  emits: ["update:value", "clear", "keydown"],
  setup(props, { attrs, emit }) {
    return () => h("input", {
      ...attrs,
      value: props.value,
      onInput: (event: Event) => emit("update:value", (event.target as HTMLInputElement).value),
      onKeydown: (event: KeyboardEvent) => emit("keydown", event),
    });
  },
});
const DatePresetPillsStub = defineComponent({
  inheritAttrs: false,
  props: { options: { type: Array, default: () => [] }, activeKey: { type: String, default: "" } },
  emits: ["select"],
  setup(props, { attrs, emit }) {
    return () => h("div", attrs, (props.options as Array<{ key: string; label: string }>).map((option) => h("button", {
      type: "button",
      "aria-pressed": props.activeKey === option.key,
      onClick: () => emit("select", option.key),
    }, option.label)));
  },
});
const DatePickerStub = defineComponent({
  inheritAttrs: false,
  props: { formattedValue: { type: Array as PropType<string[]>, default: () => [] } },
  setup(props, { attrs }) {
    return () => h("input", { ...attrs, value: props.formattedValue.join("至"), readonly: true });
  },
});
const PaginationStub = defineComponent({
  inheritAttrs: false,
  props: { page: { type: Number, default: 1 }, pageCount: { type: Number, default: 1 }, pageSize: { type: Number, default: 50 }, disabled: Boolean },
  emits: ["update:page"],
  setup(props, { attrs }) {
    return () => h("button", { ...attrs, type: "button", disabled: props.disabled, "data-page": props.page }, `第 ${props.page} / ${props.pageCount} 页`);
  },
});
const ChannelTagStub = defineComponent({
  inheritAttrs: false,
  props: { channel: { type: String, default: "" } },
  setup(props, { attrs, slots }) {
    return () => h("span", { ...attrs, class: "opanel-channel-tag" }, slots.default?.() ?? props.channel);
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
    data: { type: Array as PropType<ActualProfitOrder[]>, default: () => [] },
    loading: Boolean,
  },
  setup(props, { attrs, slots }) {
    return () => h("div", { ...attrs, "data-testid": "actual-profit-table" }, props.loading
      ? h("span", "加载中…")
      : props.data.length
        ? props.data.map((row, index) => h("div", { class: "actual-profit-test-row" }, props.columns.map((column) => h(
            "div",
            { class: `actual-profit-test-cell actual-profit-test-cell--${column.key}` },
            column.render ? h("span", undefined, column.render(row, index) as any) : undefined,
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
  NDatePicker: DatePickerStub,
  DatePicker: DatePickerStub,
  NPagination: PaginationStub,
  Pagination: PaginationStub,
  NTag: TagStub,
  Tag: TagStub,
  ChannelTag: ChannelTagStub,
  DatePresetPills: DatePresetPillsStub,
  EmptyState: EmptyStateStub,
  MorphIcon: SlotStub,
  SearchField: SearchFieldStub,
};

function makeOrder(overrides: Partial<ActualProfitOrder> = {}): ActualProfitOrder {
  return {
    shop_id: 2,
    shop_name: "店铺 2",
    posting_number: "ORDER-1",
    channel: "FBP",
    created_at: "2026-08-31T08:00:00Z",
    status_raw: "已签收",
    finance: {
      status: "available",
      operation_count: 2,
      currency: "CNY",
      net_amount: "675.00",
      net_cny: "675.00",
    },
    erp_cost: {
      status: "complete",
      item_count: 1,
      matched_items: 1,
      missing_items: 0,
      quantity_mismatch_items: 0,
      offer_id_mismatch_items: 0,
      exchange_rate_original: "1",
      total_cost_cny: "50.00",
    },
    actual_profit_cny: "625.00",
    profit_status: "ready",
    incomplete_reasons: [],
    ...overrides,
  };
}

function makeResponse(items: ActualProfitOrder[], total = items.length, page = 1, size = 50): ActualProfitResponse {
  return { items, total, page, size };
}

let mounted: VueWrapper[] = [];
const { selectedShopId } = useShop();

async function mountProfit(query: Record<string, string> = {}): Promise<{ wrapper: VueWrapper; router: ReturnType<typeof createRouter> }> {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/profit", component: ProfitView }] });
  await router.push({ path: "/profit", query });
  await router.isReady();
  const wrapper = shallowMount(ProfitView, { global: { plugins: [router], stubs } });
  mounted.push(wrapper);
  await flushPromises();
  return { wrapper, router };
}

beforeEach(() => {
  selectedShopId.value = 0;
  vi.clearAllMocks();
  api.listActualOrderProfits.mockResolvedValue(makeResponse([]));
});

afterEach(() => {
  mounted.forEach((wrapper) => wrapper.unmount());
  mounted = [];
});

describe("ProfitView actual profit orders", () => {
  it("renders Finance CNY, ERP cost, actual profit, channel, and ready status", async () => {
    const order = makeOrder();
    api.listActualOrderProfits.mockResolvedValue(makeResponse([order]));
    const { wrapper } = await mountProfit();

    expect(wrapper.find(".actual-profit-test-cell--posting_number").text()).toContain("ORDER-1");
    expect(wrapper.find(".actual-profit-finance-cell").text()).toContain("¥675.00");
    expect(wrapper.find(".actual-profit-erp-cell").text()).toContain("¥50.00");
    expect(wrapper.find(".actual-profit-profit").text()).toBe("¥625.00");
    expect(wrapper.find(".actual-profit-status-cell").text()).toContain("完整");
    expect(wrapper.text()).toContain("FBP");
    expect(wrapper.text()).not.toContain("预测利润");
    expect(api.listActualOrderProfits).toHaveBeenCalledWith(expect.objectContaining({ shopId: 0, page: 1, size: 50 }));
  });

  it("shows an incomplete ERP order without calculating a profit in the browser", async () => {
    const order = makeOrder({
      posting_number: "NO-ERP",
      erp_cost: {
        status: "incomplete",
        item_count: 2,
        matched_items: 0,
        missing_items: 2,
        quantity_mismatch_items: 0,
        offer_id_mismatch_items: 0,
        exchange_rate_original: null,
        total_cost_cny: null,
      },
      actual_profit_cny: null,
      profit_status: "incomplete",
      incomplete_reasons: ["missing_erp_cost"],
    });
    api.listActualOrderProfits.mockResolvedValue(makeResponse([order]));
    const { wrapper } = await mountProfit();

    expect(wrapper.find(".actual-profit-profit").text()).toBe("—");
    expect(wrapper.find(".actual-profit-erp-cell").text()).toContain("—");
    expect(wrapper.find(".actual-profit-erp-cell").text()).toContain("0 / 2 成本匹配");
    expect(wrapper.find(".actual-profit-status-cell").text()).toContain("数据不完整");
    expect(wrapper.find(".actual-profit-status-cell").text()).toContain("缺 ERP 成本");
  });

  it("keeps Shop 1 original USD visible when the backend has no CNY amount", async () => {
    const order = makeOrder({
      shop_id: 1,
      shop_name: "店铺 1",
      posting_number: "USD-PARTIAL",
      finance: {
        status: "available",
        operation_count: 1,
        currency: "USD",
        net_amount: "100",
        net_cny: null,
      },
      erp_cost: {
        status: "incomplete",
        item_count: 2,
        matched_items: 1,
        missing_items: 1,
        quantity_mismatch_items: 0,
        offer_id_mismatch_items: 0,
        exchange_rate_original: null,
        total_cost_cny: null,
      },
      actual_profit_cny: null,
      profit_status: "incomplete",
      incomplete_reasons: ["missing_erp_cost"],
    });
    api.listActualOrderProfits.mockResolvedValue(makeResponse([order]));
    const { wrapper } = await mountProfit({ shop_id: "1" });

    const financeCell = wrapper.find(".actual-profit-finance-cell");
    expect(financeCell.text()).toContain("—");
    expect(financeCell.text()).toContain("100.00 USD");
    expect(financeCell.text()).not.toContain("¥100.00");
    expect(wrapper.find(".actual-profit-profit").text()).toBe("—");
  });

  it("resets to page 1 and requests the new global shop", async () => {
    api.listActualOrderProfits.mockImplementation((query: { page: number }) => Promise.resolve(makeResponse([], 150, query.page)));
    const { wrapper } = await mountProfit({ shop_id: "0", page: "3" });
    expect(api.listActualOrderProfits).toHaveBeenLastCalledWith(expect.objectContaining({ shopId: 0, page: 3 }));

    selectedShopId.value = 1;
    await flushPromises();

    expect(api.listActualOrderProfits).toHaveBeenLastCalledWith(expect.objectContaining({ shopId: 1, page: 1 }));
    expect(wrapper.findComponent(PaginationStub).props("page")).toBe(1);
  });

  it("submits search and server pagination parameters without client-side filtering", async () => {
    api.listActualOrderProfits.mockImplementation((query: { page: number }) => Promise.resolve(makeResponse([], 100, query.page)));
    const { wrapper } = await mountProfit();
    const search = wrapper.findComponent(SearchFieldStub);
    search.vm.$emit("update:value", "SKU-9");
    await nextTick();
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(api.listActualOrderProfits).toHaveBeenLastCalledWith(expect.objectContaining({ search: "SKU-9", page: 1 }));

    wrapper.findComponent(PaginationStub).vm.$emit("update:page", 2);
    await flushPromises();
    expect(api.listActualOrderProfits).toHaveBeenLastCalledWith(expect.objectContaining({ search: "SKU-9", page: 2, size: 50 }));
  });

  it("does not let a late response overwrite newer filters", async () => {
    let resolveFirst!: (value: ActualProfitResponse) => void;
    const oldOrder = makeOrder({ posting_number: "OLD" });
    const newOrder = makeOrder({ posting_number: "NEW" });
    api.listActualOrderProfits
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce(makeResponse([newOrder]));
    const { wrapper } = await mountProfit({ shop_id: "0", from: "2026-06-01", to: "2026-06-30" });

    const search = wrapper.findComponent(SearchFieldStub);
    search.vm.$emit("update:value", "NEW");
    await nextTick();
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    resolveFirst(makeResponse([oldOrder]));
    await flushPromises();

    expect(wrapper.find(".actual-profit-order").text()).toBe("NEW");
    expect(wrapper.text()).not.toContain("OLD");
  });
});
