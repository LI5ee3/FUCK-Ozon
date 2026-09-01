import { defineComponent, h, type Component } from "vue";
import { flushPromises, shallowMount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useShop } from "../../shared/composables/useShop";
import TransferView from "./TransferView.vue";
import type { ErpCostImportHistoryItem, ErpCostImportResult } from "./api";

const api = vi.hoisted(() => ({
  buildExportUrl: vi.fn(() => "/api/export/orders?shop_id=0"),
  getImportHistory: vi.fn(),
  importCsv: vi.fn(),
  getErpCostImportHistory: vi.fn(),
  importErpCosts: vi.fn(),
}));

vi.mock("./api", () => api);

const SlotStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h("div", attrs, [slots.header?.(), slots.default?.(), slots.empty?.()]);
  },
});

const ButtonStub = defineComponent({
  inheritAttrs: false,
  props: {
    attrType: { type: String, default: "button" },
    disabled: Boolean,
    loading: Boolean,
  },
  setup(props, { attrs, slots }) {
    return () => h("button", { ...attrs, type: props.attrType, disabled: props.disabled }, [slots.icon?.(), slots.default?.()]);
  },
});

const SelectStub = defineComponent({
  inheritAttrs: false,
  props: {
    value: { type: [String, Number], default: null },
    options: { type: Array, default: () => [] },
    disabled: Boolean,
  },
  emits: ["update:value"],
  setup(props, { attrs, emit }) {
    return () => h("select", {
      ...attrs,
      value: props.value ?? "",
      disabled: props.disabled,
      onChange: (event: Event) => emit("update:value", (event.target as HTMLSelectElement).value),
    }, (props.options as Array<{ label: string; value: string | number }>).map((option) =>
      h("option", { value: option.value }, option.label),
    ));
  },
});

const EmptyStateStub = defineComponent({
  inheritAttrs: false,
  props: { title: { type: String, default: "" }, hint: { type: String, default: "" } },
  setup(props, { attrs }) {
    return () => h("div", { ...attrs, class: "empty-state-stub" }, [h("strong", props.title), props.hint ? h("small", props.hint) : null]);
  },
});

const stubs: Record<string, Component> = {
  NButton: ButtonStub,
  Button: ButtonStub,
  NCard: SlotStub,
  Card: SlotStub,
  NDatePicker: SlotStub,
  DatePicker: SlotStub,
  NSelect: SelectStub,
  Select: SelectStub,
  NSpin: SlotStub,
  Spin: SlotStub,
  ChannelTag: SlotStub,
  DatePresetPills: SlotStub,
  EmptyState: EmptyStateStub,
  Empty: EmptyStateStub,
  MorphIcon: SlotStub,
};

const { shops, selectedShopId } = useShop();
let mounted: VueWrapper[] = [];

const erpResult: ErpCostImportResult = {
  batch_id: 10,
  rows: 100,
  parsed: 95,
  inserted: 20,
  updated: 5,
  unchanged: 70,
};

const erpHistoryItem: ErpCostImportHistoryItem = {
  id: 10,
  shop_id: 2,
  filename: "mabang-2026-08.xlsx",
  row_count: 3251,
  parsed_count: 3251,
  inserted_count: 120,
  updated_count: 15,
  unchanged_count: 3116,
  imported_at: "2026-09-01T10:30:00Z",
  shop_name: "店铺 2",
};

async function mountTransfer(): Promise<VueWrapper> {
  const wrapper = shallowMount(TransferView, { global: { stubs } });
  mounted.push(wrapper);
  await flushPromises();
  return wrapper;
}

async function setFile(input: ReturnType<VueWrapper["find"]>, file: File): Promise<void> {
  Object.defineProperty(input.element, "files", { configurable: true, value: [file] });
  await input.trigger("change");
}

beforeEach(() => {
  shops.value = [{ id: 1, name: "店铺 1" }, { id: 2, name: "店铺 2" }];
  selectedShopId.value = 0;
  vi.clearAllMocks();
  api.getImportHistory.mockResolvedValue([]);
  api.getErpCostImportHistory.mockResolvedValue([]);
  api.importCsv.mockResolvedValue({ batch_id: 1, rows: 1 });
  api.importErpCosts.mockResolvedValue(erpResult);
});

afterEach(() => {
  mounted.forEach((wrapper) => wrapper.unmount());
  mounted = [];
});

describe("TransferView ERP cost import", () => {
  it("accepts only XLSX files", async () => {
    const wrapper = await mountTransfer();
    const input = wrapper.find(".transfer-erp-file-panel input[type=file]");

    await setFile(input, new File(["csv"], "costs.csv", { type: "text/csv" }));
    expect(wrapper.find(".transfer-erp-import-status").text()).toContain("仅允许 .xlsx 文件");
    expect(wrapper.find(".transfer-erp-import-form button[type=submit]").attributes("disabled")).toBeDefined();

    await setFile(input, new File(["xlsx"], "costs.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
    expect(wrapper.find(".transfer-erp-file-panel").text()).toContain("XLSX 格式验证通过");
  });

  it("requires an explicit ERP shop before submitting", async () => {
    const wrapper = await mountTransfer();
    const file = new File(["xlsx"], "costs.xlsx");
    await setFile(wrapper.find(".transfer-erp-file-panel input[type=file]"), file);

    const submit = wrapper.find(".transfer-erp-import-form button[type=submit]");
    expect(submit.attributes("disabled")).toBeDefined();

    await wrapper.find('select[aria-label="ERP 导入店铺"]').setValue("1");
    expect(submit.attributes("disabled")).toBeUndefined();
    expect(api.importErpCosts).not.toHaveBeenCalled();
  });

  it("renders the backend result and refreshes only ERP history after success", async () => {
    const wrapper = await mountTransfer();
    const file = new File(["xlsx"], "costs.xlsx");
    await wrapper.find('select[aria-label="ERP 导入店铺"]').setValue("1");
    await setFile(wrapper.find(".transfer-erp-file-panel input[type=file]"), file);
    await wrapper.find(".transfer-erp-import-form").trigger("submit");
    await flushPromises();

    expect(api.importErpCosts).toHaveBeenCalledWith(1, file);
    expect(wrapper.find(".transfer-erp-import-status").text()).toContain("扫描 100 行");
    expect(wrapper.find(".transfer-erp-import-status").text()).toContain("解析 95 条");
    expect(wrapper.find(".transfer-erp-import-status").text()).toContain("新增 20");
    expect(wrapper.find(".transfer-erp-import-status").text()).toContain("更新 5");
    expect(wrapper.find(".transfer-erp-import-status").text()).toContain("未变化 70");
    expect(api.getErpCostImportHistory).toHaveBeenCalledTimes(2);
    expect(api.getImportHistory).toHaveBeenCalledTimes(1);
  });

  it("keeps ERP history visible when CSV history fails", async () => {
    api.getImportHistory.mockRejectedValue(new Error("CSV history unavailable"));
    api.getErpCostImportHistory.mockResolvedValue([erpHistoryItem]);
    const wrapper = await mountTransfer();

    expect(wrapper.text()).toContain("导入记录加载失败：CSV history unavailable");
    expect(wrapper.text()).toContain("mabang-2026-08.xlsx");
    expect(wrapper.text()).toContain("店铺 2");
    expect(wrapper.text()).toContain("3,251");
    expect(wrapper.text()).toContain("3,116");
  });

  it("keeps the existing CSV import contract", async () => {
    const wrapper = await mountTransfer();
    const file = new File(["csv"], "orders.csv", { type: "text/csv" });
    await wrapper.find('select[aria-label="导入店铺"]').setValue("1");
    await wrapper.find('select[aria-label="导入渠道"]').setValue("FBP");
    await setFile(wrapper.find(".transfer-import-card input[type=file]"), file);
    await wrapper.find(".transfer-import-card form").trigger("submit");
    await flushPromises();

    expect(api.importCsv).toHaveBeenCalledWith("FBP", 1, file);
  });
});
