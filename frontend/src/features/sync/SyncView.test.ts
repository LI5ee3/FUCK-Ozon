import { flushPromises, shallowMount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { useShop } from "../../shared/composables/useShop";
import SyncView from "./SyncView.vue";

const api = vi.hoisted(() => ({
  getAutoSyncSettings: vi.fn(),
  getExchangeRateStatus: vi.fn(),
  getSyncRun: vi.fn(),
  getSyncRuns: vi.fn(),
  startSync: vi.fn(),
}));
const dialog = vi.hoisted(() => ({ warning: vi.fn() }));

vi.mock("./api", () => api);
vi.mock("naive-ui", async () => ({
  ...await vi.importActual<typeof import("naive-ui")>("naive-ui"),
  useDialog: () => dialog,
  useMessage: () => ({ error: vi.fn(), success: vi.fn() }),
}));

const { selectedShopId } = useShop();

describe("Sync exchange rate contract", () => {
  it("renders service/penalty and sales rates separately", async () => {
    api.getSyncRuns.mockResolvedValue([]);
    api.getAutoSyncSettings.mockResolvedValue([]);
    api.getExchangeRateStatus.mockResolvedValue({
      source: "ozon_xapi",
      last_success_at: null,
      data_through: null,
      as_of: "2026-08-31T08:00:00Z",
      rates: {
        USD: {
          service_penalty_exchange_rate: "90",
          sales_exchange_rate: "88",
          valid_from_utc: "2026-08-21T21:00:00Z",
          valid_to_utc: "2026-08-22T21:00:00Z",
        },
        CNY: {
          service_penalty_exchange_rate: "12",
          sales_exchange_rate: "11",
          valid_from_utc: "2026-08-21T21:00:00Z",
          valid_to_utc: "2026-08-22T21:00:00Z",
        },
      },
    });

    const wrapper = shallowMount(SyncView);
    await flushPromises();

    expect(wrapper.text()).toContain("针对服务和罚款");
    expect(wrapper.text()).toContain("用于销售");
    expect(wrapper.text()).toContain("90");
    expect(wrapper.text()).toContain("88");
    expect(wrapper.text()).toContain("12");
    expect(wrapper.text()).toContain("11");
    expect(wrapper.text()).toContain("财务流水");
    expect(wrapper.text()).toContain("商品价格");
    expect(wrapper.text()).toContain("7 个模块");
    expect(wrapper.text()).not.toContain("基础汇率");
  });

  it("renders a missing sales rate as unavailable instead of zero", async () => {
    api.getSyncRuns.mockResolvedValue([]);
    api.getAutoSyncSettings.mockResolvedValue([]);
    api.getExchangeRateStatus.mockResolvedValue({
      source: "ozon_xapi",
      last_success_at: null,
      data_through: null,
      as_of: "2026-08-31T08:00:00Z",
      rates: {
        USD: {
          service_penalty_exchange_rate: "90",
          sales_exchange_rate: null,
          valid_from_utc: "2026-08-21T21:00:00Z",
          valid_to_utc: "2026-08-22T21:00:00Z",
        },
        CNY: {
          service_penalty_exchange_rate: "12",
          sales_exchange_rate: null,
          valid_from_utc: "2026-08-21T21:00:00Z",
          valid_to_utc: "2026-08-22T21:00:00Z",
        },
      },
    });

    const wrapper = shallowMount(SyncView);
    await flushPromises();

    expect(wrapper.text()).toContain("暂无");
    expect(wrapper.text()).not.toContain("0.0000");
  });

  it("starts stock and prices directly for the all-time preset", async () => {
    api.getSyncRuns.mockResolvedValue([]);
    api.getAutoSyncSettings.mockResolvedValue([]);
    api.getExchangeRateStatus.mockResolvedValue({
      source: "ozon_xapi", last_success_at: null, data_through: null,
      as_of: "2026-08-31T08:00:00Z", rates: {},
    });
    api.startSync.mockResolvedValue({ run_id: 1, status: "running", progress_total: 1 });
    api.getSyncRun.mockResolvedValue({ status: "success", records: 1 });
    dialog.warning.mockReset();
    selectedShopId.value = 1;

    const wrapper = shallowMount(SyncView);
    await flushPromises();
    const state = (wrapper.vm.$ as unknown as { setupState: Record<string, unknown> }).setupState;
    (state.selectManualPreset as (preset: "all") => void)("all");
    await wrapper.vm.$nextTick();

    const startManualSync = state.startManualSync as (module: "stock" | "prices" | "orders") => void;
    for (const module of ["stock", "prices"] as const) {
      startManualSync(module);
      await flushPromises();
    }
    expect(dialog.warning).not.toHaveBeenCalled();
    expect(api.startSync).toHaveBeenCalledWith("stock", 1, expect.any(String), expect.any(String));
    expect(api.startSync).toHaveBeenCalledWith("prices", 1, expect.any(String), expect.any(String));

    startManualSync("orders");
    expect(dialog.warning).toHaveBeenCalledTimes(1);
    selectedShopId.value = 0;
  });
});
