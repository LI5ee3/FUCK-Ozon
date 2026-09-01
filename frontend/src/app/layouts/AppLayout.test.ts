import { flushPromises, shallowMount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, expect, it, vi } from "vitest";
import { NLayoutSider } from "naive-ui";
import AppLayout from "./AppLayout.vue";

vi.mock("naive-ui", async () => ({
  ...await vi.importActual<typeof import("naive-ui")>("naive-ui"),
  useDialog: () => ({}),
  useLoadingBar: () => ({ start: vi.fn(), finish: vi.fn() }),
  useNotification: () => ({ error: vi.fn() }),
}));
vi.mock("../../shared/api/shops", () => ({ listShops: async () => [] }));
afterEach(() => { vi.restoreAllMocks(); });

it("tracks the 800px navigation breakpoint and removes its listener", async () => {
  const addEventListener = vi.fn();
  const removeEventListener = vi.fn();
  const media = vi.spyOn(window, "matchMedia").mockReturnValue({ matches: false, addEventListener, removeEventListener } as unknown as MediaQueryList);
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component: { template: "<div />" } }] });
  await router.push("/");
  const wrapper = shallowMount(AppLayout, { global: { plugins: [router] } });
  await flushPromises();
  expect(wrapper.get(".opanel-heading h1").text()).toContain("O3Pilot");
  expect(wrapper.get(".opanel-logo").attributes("alt")).toBe("");
  expect(wrapper.get(".opanel-brand-name").attributes("aria-label")).toBe("O3Pilot");
  expect(wrapper.get(".brand-subscript").text()).toBe("3");
  expect(wrapper.get(".opanel-eyebrow").text()).toBe("O3PILOT · MACARON EDITION");
  expect(media).toHaveBeenCalledWith("(max-width: 800px)");
  const change = addEventListener.mock.calls[0]![1] as (event: { matches: boolean }) => void;
  for (const matches of [true, false]) {
    change({ matches });
    await wrapper.vm.$nextTick();
    expect(wrapper.findComponent(NLayoutSider).props("collapsed")).toBe(matches);
  }
  wrapper.unmount();
  expect(removeEventListener).toHaveBeenCalledWith("change", change);
});
