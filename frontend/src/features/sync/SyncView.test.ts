import { flushPromises, shallowMount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import SyncView from "./SyncView.vue";

const api = vi.hoisted(() => ({
  getAutoSyncSettings: vi.fn(),
  getExchangeRateStatus: vi.fn(),
  getSyncRuns: vi.fn(),
}));

vi.mock("./api", () => api);
vi.mock("naive-ui", async () => ({
  ...await vi.importActual<typeof import("naive-ui")>("naive-ui"),
  useDialog: () => ({ warning: vi.fn() }),
  useMessage: () => ({ error: vi.fn(), success: vi.fn() }),
}));

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
});
