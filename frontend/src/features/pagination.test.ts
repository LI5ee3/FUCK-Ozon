import { flushPromises, shallowMount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import OrdersView from "./orders/OrdersView.vue";
import ReturnsView from "./returns/ReturnsView.vue";
import TimelinessView from "./timeliness/TimelinessView.vue";
import AnalyticsView from "./analytics/AnalyticsView.vue";
import AlertsView from "./alerts/AlertsView.vue";
import AdCampaignsView from "./advertising/AdCampaignsView.vue";
import AdSkusView from "./advertising/AdSkusView.vue";

const request = vi.hoisted(() => vi.fn());
vi.mock("../shared/api/client", async () => ({
  ...await vi.importActual<typeof import("../shared/api/client")>("../shared/api/client"), request,
}));
vi.mock("naive-ui", async () => ({
  ...await vi.importActual<typeof import("naive-ui")>("naive-ui"),
  useMessage: () => ({ error: vi.fn(), success: vi.fn() }),
  useDialog: () => ({ warning: vi.fn() }),
}));

const cases = [
  [OrdersView, "loadOrders", ""], [ReturnsView, "loadReturns", "cancel"],
  [ReturnsView, "loadRfbsReturns", "rfbs"], [TimelinessView, "loadTimeliness", ""],
  [AnalyticsView, "loadTraffic", "traffic"], [AnalyticsView, "loadProductQueryRows", "products"],
  [AlertsView, "loadEvents", ""], [AdCampaignsView, "loadCampaigns", ""], [AdSkusView, "loadSkuStats", ""],
] as const;

beforeEach(() => { request.mockReset().mockImplementation(() => new Promise(() => {})); });

describe("pagination response guards", () => {
  it.each(cases)("%# only corrects pages for current filters", async (component, loader, tab) => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component }] });
    await router.push({ path: "/", query: { shop_id: "0", from: "2026-08-01", to: "2026-08-31" } });
    await router.isReady();
    const wrapper = shallowMount(component, { global: { plugins: [router], stubs: { Pagination: { template: "<div />", inheritAttrs: false } } } });
    await flushPromises();
    const state = (wrapper.vm.$ as unknown as { setupState: Record<string, unknown> }).setupState;
    const filters = state.filters as Record<string, unknown>;
    const load = state[loader] as (query: Record<string, unknown>) => Promise<void>;
    const replace = vi.spyOn(router, "replace").mockResolvedValue(undefined);
    for (const stale of [true, false]) {
      filters.page = 99;
      if (tab) filters.tab = tab;
      const query = { ...filters };
      let resolve!: (data: unknown) => void;
      request.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
      const pending = load(query);
      if (stale) filters.shopId = filters.shopId === 1 ? 2 : 1;
      resolve({ items: [], total: 0, size: 50 });
      await pending;
      expect(replace).toHaveBeenCalledTimes(stale ? 0 : 1);
    }
  });

  it("trims order search before navigation", async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component: OrdersView }] });
    await router.push("/?shop_id=0");
    await router.isReady();
    const wrapper = shallowMount(OrdersView, { global: { plugins: [router], stubs: { Pagination: { template: "<div />", inheritAttrs: false } } } });
    await flushPromises();
    const state = (wrapper.vm.$ as unknown as { setupState: Record<string, unknown> }).setupState;
    state.searchDraft = "  ORDER-1  ";
    (state.submitSearch as () => void)();
    await flushPromises();
    expect(router.currentRoute.value.query.q).toBe("ORDER-1");
  });
});
