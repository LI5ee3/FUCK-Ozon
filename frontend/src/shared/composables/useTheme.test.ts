import { afterEach, describe, expect, it, vi } from "vitest";
import { useTheme } from "./useTheme";

afterEach(() => { vi.unstubAllGlobals(); });

describe("theme storage failures", () => {
  it("still switches the current document when storage is disabled", () => {
    const theme = useTheme();
    vi.stubGlobal("localStorage", { setItem: () => { throw new Error("disabled"); } });
    expect(() => theme.setMode("dark")).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(() => theme.toggle()).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("handles removeItem failure in system mode", () => {
    const theme = useTheme();
    const removeItem = vi.fn(() => { throw new Error("disabled"); });
    vi.stubGlobal("localStorage", { setItem: vi.fn(), removeItem });
    expect(() => theme.setMode("system")).not.toThrow();
    expect(removeItem).toHaveBeenCalledWith("theme");
    expect(document.documentElement.dataset.theme).toBe(theme.isDark.value ? "dark" : "light");
  });
});
