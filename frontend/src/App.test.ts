import { flushPromises, shallowMount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RouterView } from "vue-router";
import App from "./App.vue";
import LoginView from "./app/auth/LoginView.vue";
import { UNAUTHORIZED_EVENT } from "./shared/api/client";

const getSession = vi.hoisted(() => vi.fn());
vi.mock("./app/auth/api", () => ({
  getSession,
  login: vi.fn(),
}));
vi.mock("./shared/composables/useTheme", () => ({
  useTheme: () => ({ isDark: { value: false }, init: vi.fn() }),
}));

describe("App authentication gate", () => {
  beforeEach(() => { getSession.mockReset(); });

  it("shows LoginView when unauthenticated", async () => {
    getSession.mockResolvedValue({ authenticated: false, csrf_token: "" });
    const wrapper = shallowMount(App);
    await flushPromises();

    expect(wrapper.findComponent(LoginView).exists()).toBe(true);
    expect(wrapper.findComponent(RouterView).exists()).toBe(false);
  });

  it("restores RouterView and returns to LoginView after a 401 event", async () => {
    getSession.mockResolvedValue({ authenticated: true, csrf_token: "csrf" });
    const wrapper = shallowMount(App);
    await flushPromises();

    expect(wrapper.findComponent(RouterView).exists()).toBe(true);
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    await wrapper.vm.$nextTick();
    expect(wrapper.findComponent(LoginView).exists()).toBe(true);
  });
});
