import { defineComponent, h, nextTick, type Component, type VNodeChild } from "vue";
import { flushPromises, shallowMount, type VueWrapper } from "@vue/test-utils";
import { createMemoryHistory, createRouter, type Router } from "vue-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ComplaintsView from "./ComplaintsView.vue";
import ReceivedDisputeEditor from "./components/ReceivedDisputeEditor.vue";
import ShippingComplaintEditor from "./components/ShippingComplaintEditor.vue";
import { useShop } from "../../shared/composables/useShop";
import type {
  ComplaintRecord,
  ReceivedDisputeRecord,
  ReceivedDisputesResponse,
  ShippingComplaintOrder,
  ShippingComplaintsResponse,
} from "./types";

const api = vi.hoisted(() => ({
  listReceivedDisputes: vi.fn(),
  listShippingComplaints: vi.fn(),
  saveReceivedDispute: vi.fn(),
  saveShippingComplaint: vi.fn(),
}));
const messages = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));

vi.mock("./api", () => api);
vi.mock("naive-ui", async () => ({
  ...await vi.importActual<typeof import("naive-ui")>("naive-ui"),
  useMessage: () => messages,
}));

const shippingComplaint = {
  complaint_number: "CMP-1",
  complaint_at: "2026-08-20T02:00:00Z",
  channel: "Ozon Support",
  warehouse: "本地仓",
  order_process_status: "待处理",
  complaint_status: "已受理",
  compensation_status: "待打款",
  platform_compensation_rub: null,
  platform_compensated_at: null,
  logistics_compensation_cny: null,
  logistics_compensated_at: null,
  not_received_return: 0,
  resolved: 0,
  notes: "shipping note",
} as ComplaintRecord;

function shippingRow(postingNumber = "POST-1", complaints: ComplaintRecord[] = []): ShippingComplaintOrder {
  return {
    shop_id: 1,
    shop_name: "店铺一",
    posting_number: postingNumber,
    created_at: "2026-08-01T00:00:00Z",
    shipped_at: "2026-08-02T00:00:00Z",
    tracking_number: "TRACK-1",
    status_raw: "cancelled",
    cancel_reason_raw: "reason",
    shipped: 1,
    data_anomaly: 0,
    amount_original: 100,
    amount_currency: "CNY",
    status_changed_at: "2026-08-03T00:00:00Z",
    cancelled_at: "2026-08-03T00:00:00Z",
    cancel_reason: "取消原因",
    complaint_deadline: "2026-09-02",
    complaint_deadline_status: "normal",
    items: [{
      shop_id: 1,
      posting_number: postingNumber,
      sku: "SKU-1",
      offer_id: "OFFER-1",
      product_name_raw: "商品",
      quantity: 1,
      unit_price: 100,
      price_currency: "CNY",
      product_name: "商品",
    }],
    complaints,
  };
}

function receivedRow(returnNumber = "RET-1"): ReceivedDisputeRecord {
  return {
    shop_id: 2,
    shop_name: "店铺二",
    settlement_currency: "CNY",
    return_number: returnNumber,
    created_at: "2026-08-10T00:00:00Z",
    posting_number: "POST-2",
    sku: "SKU-2",
    offer_id: "OFFER-2",
    product_name: "退货商品",
    product_amount: 80,
    product_currency: "CNY",
    reason_raw: "reason",
    reason_name: "纠纷原因",
    buyer_comment_raw: null,
    refund_type: "部分退款",
    refund_amount: 20,
    refund_currency: "CNY",
    platform_compensation_rub: null,
    platform_compensated_at: null,
    logistics_compensation_cny: null,
    logistics_compensated_at: null,
    process_status: "处理中",
    return_method: "IML",
    iml_return_number: "IML-1",
    iml_system_sn: "SN-1",
    buyer_tracking_number: "BUYER-1",
    handling_method: "退回",
    video_recorded: 1,
    outbound_order_number: "OUT-1",
    return_result: "退回国内中",
    notes: "received note",
    manual_created_at: "2026-08-11T00:00:00Z",
    updated_at: "2026-08-12T00:00:00Z",
    complaint_deadline: "2026-09-09",
    complaint_deadline_status: "due_soon",
    platform_compensation_original_currency: "RUB",
    platform_compensation_converted_amount: null,
    platform_compensation_converted_currency: "CNY",
    platform_compensation_base_rates: {},
    platform_compensation_missing_rate: false,
    platform_compensated_at_beijing: null,
    logistics_compensation_original_currency: "CNY",
    logistics_compensation_converted_amount: null,
    logistics_compensation_converted_currency: "CNY",
    logistics_compensation_base_rates: {},
    logistics_compensation_missing_rate: false,
    logistics_compensated_at_beijing: null,
  };
}

function shippingResponse(row = shippingRow(), page = 1): ShippingComplaintsResponse {
  return { items: [row], total: 200, page, size: 50, data_through: "2026-08-29T00:00:00Z" };
}

function receivedResponse(row = receivedRow(), page = 1): ReceivedDisputesResponse {
  return { items: [row], total: 200, page, size: 50, data_through: "2026-08-29T00:00:00Z" };
}

const SlotStub = defineComponent({
  setup(_, { slots }) {
    return () => h("div", [slots.header?.(), slots.default?.(), slots.empty?.()]);
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
  props: { value: { type: [String, Number], default: "" } },
  emits: ["update:value"],
  setup(props, { attrs, emit }) {
    return () => h("input", {
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
const DataTableStub = defineComponent({
  name: "NDataTable",
  props: { columns: { type: Array, required: true }, data: { type: Array, required: true } },
  setup(props) {
    return () => h("div", { class: "data-table-stub" }, props.data.flatMap((row) =>
      (props.columns as Array<{ render?: (value: unknown) => VNodeChild }>).map((column) => column.render?.(row)),
    ));
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
  NDatePicker: SlotStub,
  DatePicker: SlotStub,
  NEmpty: SlotStub,
  Empty: SlotStub,
  NInput: InputStub,
  Input: InputStub,
  NSelect: SelectStub,
  Select: SelectStub,
  NTag: SlotStub,
  Tag: SlotStub,
};

async function mountAt(path: string): Promise<{ wrapper: VueWrapper; router: Router }> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/complaints", component: ComplaintsView }],
  });
  await router.push(path);
  await router.isReady();
  const wrapper = shallowMount(ComplaintsView, { global: { plugins: [router], stubs } });
  await flushPromises();
  return { wrapper, router };
}

function button(wrapper: VueWrapper, text: string) {
  const match = wrapper.findAll("button").find((item) => item.text().includes(text));
  if (!match) throw new Error(`Missing button: ${text}`);
  return match;
}

describe("ComplaintsView behavior", () => {
  beforeEach(() => {
    useShop().selectShop(0);
    vi.clearAllMocks();
    api.listShippingComplaints.mockResolvedValue(shippingResponse());
    api.listReceivedDisputes.mockResolvedValue(receivedResponse());
  });

  it("restores query filters and keeps search, status, and page per tab", async () => {
    const { wrapper } = await mountAt("/complaints?shop_id=2&q=shipping&status=open&page=2&from=2026-08-01&to=2026-08-20");
    expect(wrapper.get('input[aria-label="搜索发货未收货投诉"]').element).toHaveProperty("value", "shipping");
    expect(wrapper.get('select[aria-label="投诉状态筛选"]').element).toHaveProperty("value", "open");
    expect(wrapper.text()).toContain("第 2 / 4 页");

    await button(wrapper, "已收货纠纷").trigger("click");
    await flushPromises();
    await wrapper.get('input[aria-label="搜索已收货纠纷"]').setValue("received");
    await wrapper.get('select[aria-label="处理状态筛选"]').setValue("closed");
    await wrapper.get('form[role="search"]').trigger("submit");
    await flushPromises();
    await button(wrapper, "下一页").trigger("click");
    await flushPromises();

    await button(wrapper, "发货未收货投诉").trigger("click");
    await flushPromises();
    expect(wrapper.get('input[aria-label="搜索发货未收货投诉"]').element).toHaveProperty("value", "shipping");
    expect(wrapper.get('select[aria-label="投诉状态筛选"]').element).toHaveProperty("value", "open");
    expect(wrapper.text()).toContain("第 2 / 4 页");

    await button(wrapper, "已收货纠纷").trigger("click");
    await flushPromises();
    expect(wrapper.get('input[aria-label="搜索已收货纠纷"]').element).toHaveProperty("value", "received");
    expect(wrapper.get('select[aria-label="处理状态筛选"]').element).toHaveProperty("value", "closed");
    expect(wrapper.text()).toContain("第 2 / 4 页");
  });

  it("keeps the latest request result when an older search resolves last", async () => {
    let resolveOld!: (value: ShippingComplaintsResponse) => void;
    let resolveNew!: (value: ShippingComplaintsResponse) => void;
    api.listShippingComplaints.mockImplementation(({ search }: { search?: string }) => {
      if (search === "old") return new Promise((resolve) => { resolveOld = resolve; });
      if (search === "new") return new Promise((resolve) => { resolveNew = resolve; });
      return Promise.resolve(shippingResponse());
    });
    const { wrapper } = await mountAt("/complaints");
    const search = wrapper.get('input[aria-label="搜索发货未收货投诉"]');

    await search.setValue("old");
    await wrapper.get('form[role="search"]').trigger("submit");
    await flushPromises();
    await search.setValue("new");
    await wrapper.get('form[role="search"]').trigger("submit");
    await flushPromises();

    resolveNew(shippingResponse(shippingRow("NEW")));
    await flushPromises();
    resolveOld(shippingResponse(shippingRow("OLD")));
    await flushPromises();
    expect((wrapper.findComponent(DataTableStub).props("data") as ShippingComplaintOrder[])[0]?.posting_number).toBe("NEW");
  });

  it("opens each editor with the selected record", async () => {
    const ship = shippingRow("POST-OPEN", [shippingComplaint]);
    const received = receivedRow("RET-OPEN");
    api.listShippingComplaints.mockResolvedValue(shippingResponse(ship));
    api.listReceivedDisputes.mockResolvedValue(receivedResponse(received));
    const { wrapper } = await mountAt("/complaints");

    await button(wrapper, "CMP-1").trigger("click");
    expect(wrapper.findComponent(ShippingComplaintEditor).props("row")).toMatchObject({ posting_number: "POST-OPEN" });
    expect(wrapper.findComponent(ShippingComplaintEditor).props("complaint")).toMatchObject({ complaint_number: "CMP-1" });

    await button(wrapper, "已收货纠纷").trigger("click");
    await flushPromises();
    await button(wrapper, "编辑").trigger("click");
    expect(wrapper.findComponent(ReceivedDisputeEditor).props("row")).toMatchObject({ return_number: "RET-OPEN" });
  });

  it("refreshes only the matching list after a successful save", async () => {
    const { wrapper } = await mountAt("/complaints");
    const shippingCalls = api.listShippingComplaints.mock.calls.length;
    const receivedCalls = api.listReceivedDisputes.mock.calls.length;

    wrapper.findComponent(ShippingComplaintEditor).vm.$emit("saved");
    await flushPromises();
    expect(api.listShippingComplaints).toHaveBeenCalledTimes(shippingCalls + 1);
    expect(api.listReceivedDisputes).toHaveBeenCalledTimes(receivedCalls);

    wrapper.findComponent(ReceivedDisputeEditor).vm.$emit("saved");
    await flushPromises();
    expect(api.listReceivedDisputes).toHaveBeenCalledTimes(receivedCalls + 1);
  });
});

describe("Complaint editors", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.saveShippingComplaint.mockResolvedValue({ ok: true });
    api.saveReceivedDispute.mockResolvedValue({ ok: true });
  });

  it("hydrates and saves the selected shipping complaint", async () => {
    const wrapper = shallowMount(ShippingComplaintEditor, {
      props: { show: true, row: shippingRow("POST-SAVE"), complaint: shippingComplaint },
      global: { stubs: { ...stubs, NModal: SlotStub, Modal: SlotStub, ComplaintCompensationFields: SlotStub } },
    });
    await nextTick();
    const inputs = wrapper.findAll("input");
    expect(inputs[0]?.element.value).toBe("CMP-1");
    expect(inputs[2]?.element.value).toBe("Ozon Support");

    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(api.saveShippingComplaint).toHaveBeenCalledWith(expect.objectContaining({
      posting_number: "POST-SAVE",
      complaint_number: "CMP-1",
      channel: "Ozon Support",
    }));
    expect(wrapper.emitted("saved")).toHaveLength(1);
  });

  it("hydrates and saves the selected received dispute", async () => {
    const row = receivedRow("RET-SAVE");
    const wrapper = shallowMount(ReceivedDisputeEditor, {
      props: { show: true, row },
      global: { stubs: { ...stubs, NModal: SlotStub, Modal: SlotStub, NInputNumber: InputStub, InputNumber: InputStub, ComplaintCompensationFields: SlotStub } },
    });
    await nextTick();
    expect(wrapper.text()).toContain("RET-SAVE · 店铺二");
    expect(wrapper.get('select').element).toHaveProperty("value", "部分退款");

    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(api.saveReceivedDispute).toHaveBeenCalledWith(expect.objectContaining({
      return_number: "RET-SAVE",
      process_status: "处理中",
      return_method: "IML",
    }));
    expect(wrapper.emitted("saved")).toHaveLength(1);
  });
});
