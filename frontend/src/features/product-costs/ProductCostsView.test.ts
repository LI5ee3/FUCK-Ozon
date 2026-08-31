import { defineComponent, h, type Component, type VNodeChild } from "vue";
import { flushPromises, shallowMount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ProductCostsView from "./ProductCostsView.vue";
import type { ProductCostHistoryResponse, ProductCostRow, ProductCostsResponse } from "./types";

const api = vi.hoisted(() => ({
  listProductCosts: vi.fn(),
  listProductCostHistory: vi.fn(),
  saveProductCost: vi.fn(),
}));
const messages = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));

vi.mock("./api", () => api);
vi.mock("naive-ui", async () => ({
  ...await vi.importActual<typeof import("naive-ui")>("naive-ui"),
  useMessage: () => messages,
}));

const row: ProductCostRow = {
  product_identity: "OFFER-1",
  display_name: "蓝牙追踪器",
  ozon_skus: ["1936515175", "1936515176"],
  offer_ids: ["WGMFR265C46BL", "WGMFR265C46GR"],
  sku: "1936515175",
  offer_id: "WGMFR265C46BL",
  forecast_cost: {
    id: 1,
    product_identity: "OFFER-1",
    purchase_cost: 10,
    purchase_currency: "USD",
    weight_grams: 100,
    length_cm: 10,
    width_cm: 5,
    height_cm: 3,
    packing_cost_cny: 2,
    other_cost_cny: 1,
    note: "当前备注",
    created_at: "2026-08-30T00:00:00Z",
    updated_at: "2026-08-30T00:00:00Z",
  },
  configured: true,
  updated_at: "2026-08-30T00:00:00Z",
  conflict: false,
  conflict_message: null,
};

const response: ProductCostsResponse = { items: [row], total: 1, page: 1, size: 50 };
const unconfiguredRow: ProductCostRow = {
  ...row,
  product_identity: "SKU-2",
  display_name: "未配置商品",
  ozon_skus: ["1936515177"],
  offer_ids: ["WGMFR265C46RD"],
  sku: "1936515177",
  offer_id: "WGMFR265C46RD",
  forecast_cost: null,
  configured: false,
  updated_at: null,
};
response.items.push(unconfiguredRow);
response.total = response.items.length;
const history: ProductCostHistoryResponse = {
  product_identity: "OFFER-1",
  total: 2,
  limit: 100,
  items: [
    { ...row.forecast_cost!, id: 2, change_note: "供应商涨价", recorded_at: "2026-08-31T00:00:00Z" },
    { ...row.forecast_cost!, id: 1, change_note: "新报价", recorded_at: "2026-08-30T00:00:00Z" },
  ],
};

const SlotStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h("div", attrs, [slots.header?.(), slots.icon?.(), slots.default?.(), slots.empty?.()]);
  },
});
const ButtonStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h("button", attrs, [slots.icon?.(), slots.default?.()]);
  },
});
const InputStub = defineComponent({
  inheritAttrs: false,
  props: { value: { type: [String, Number], default: "" }, type: { type: String, default: "text" } },
  emits: ["update:value"],
  setup(props, { attrs, emit }) {
    return () => h(props.type === "textarea" ? "textarea" : "input", {
      ...attrs,
      value: props.value,
      onInput: (event: Event) => emit("update:value", (event.target as HTMLInputElement).value),
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
    }, (props.options as Array<{ label: string; value: string | number }>).map((option) => h("option", { value: option.value }, option.label)));
  },
});
const ModalStub = defineComponent({
  inheritAttrs: false,
  props: { show: { type: Boolean, default: false } },
  setup(props, { attrs, slots }) {
    return () => props.show ? h("div", { ...attrs, class: "modal-stub" }, [slots.default?.()]) : null;
  },
});
const DataTableStub = defineComponent({
  props: { columns: { type: Array, required: true }, data: { type: Array, required: true } },
  setup(props) {
    return () => {
      const columns = props.columns as Array<{ title?: unknown; render?: (row: unknown) => VNodeChild }>;
      return h("div", { class: "data-table-stub" }, [
        ...columns.map((column) => typeof column.title === "string" ? column.title : ""),
        ...(props.data as unknown[]).flatMap((value) => columns.map((column) => column.render?.(value))),
      ]);
    };
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
  NInput: InputStub,
  Input: InputStub,
  NInputNumber: InputStub,
  InputNumber: InputStub,
  NModal: ModalStub,
  Modal: ModalStub,
  NPagination: SlotStub,
  Pagination: SlotStub,
  NSelect: SelectStub,
  Select: SelectStub,
  NSpin: SlotStub,
  Spin: SlotStub,
  NTag: SlotStub,
  Tag: SlotStub,
  SearchField: InputStub,
  EmptyState: SlotStub,
};

describe("ProductCostsView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listProductCosts.mockResolvedValue(response);
    api.listProductCostHistory.mockResolvedValue(history);
    api.saveProductCost.mockResolvedValue({ ok: true, created: false, changed: true, product_identity: "OFFER-1", forecast_cost: row.forecast_cost });
  });

  it("loads configured and unconfigured products with distinct Ozon SKU and offer_id labels", async () => {
    const wrapper = shallowMount(ProductCostsView, { global: { stubs } });
    await flushPromises();
    expect(api.listProductCosts).toHaveBeenCalledWith({ search: "", page: 1, size: 50 });
    expect(wrapper.text()).toContain("Ozon SKU");
    expect(wrapper.text()).toContain("货号 / offer_id");
    expect(wrapper.text()).toContain("1936515175、1936515176");
    expect(wrapper.text()).toContain("WGMFR265C46BL、WGMFR265C46GR");
    expect(wrapper.text()).toContain("未配置");
  });

  it("saves the editor and immediately reloads current data, then opens read-only history", async () => {
    const wrapper = shallowMount(ProductCostsView, { global: { stubs } });
    await flushPromises();
    const buttons = wrapper.findAll("button");
    const edit = buttons.find((button) => button.text().includes("编辑"));
    if (!edit) throw new Error("missing edit button");
    await edit.trigger("click");
    await wrapper.findAll("form")[1]!.trigger("submit");
    await flushPromises();
    expect(api.saveProductCost).toHaveBeenCalledWith(expect.objectContaining({
      sku: "1936515175", offer_id: "WGMFR265C46BL", purchase_cost: 10,
    }));
    expect(api.listProductCosts).toHaveBeenCalledTimes(2);

    const historyButton = wrapper.findAll("button").find((button) => button.text().includes("历史记录"));
    if (!historyButton) throw new Error("missing history button");
    await historyButton.trigger("click");
    await flushPromises();
    expect(api.listProductCostHistory).toHaveBeenCalledWith("1936515175", "WGMFR265C46BL");
    expect(wrapper.text()).toContain("供应商涨价");
    expect(wrapper.text()).toContain("历史记录仅表示预测参数的修改记录");
  });
});
