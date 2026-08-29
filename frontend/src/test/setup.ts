import { afterEach } from "vitest";
import { config, enableAutoUnmount } from "@vue/test-utils";

class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

Object.defineProperty(window, "matchMedia", {
  configurable: true,
  value: () => ({
    matches: false,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }),
});
Object.defineProperty(window, "ResizeObserver", { configurable: true, value: ResizeObserverStub });
Object.defineProperty(globalThis, "ResizeObserver", { configurable: true, value: ResizeObserverStub });

config.global.renderStubDefaultSlot = true;
enableAutoUnmount(afterEach);
afterEach(() => { document.body.innerHTML = ""; });
