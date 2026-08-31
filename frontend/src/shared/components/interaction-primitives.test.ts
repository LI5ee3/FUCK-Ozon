import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NInput } from "naive-ui";
import DatePresetPills from "./DatePresetPills.vue";
import SegmentedControl from "./SegmentedControl.vue";
import SearchField from "./SearchField.vue";
import ChannelTag from "./ChannelTag.vue";

const options = [{ key: "day", label: "日" }, { key: "week", label: "周" }];
afterEach(() => { vi.useRealTimers(); });

describe("shared interaction primitives", () => {
  it("presets expose active selection and emit the original key", async () => {
    const wrapper = mount(DatePresetPills, { props: { options, activeKey: "day" } });
    expect(wrapper.findAll("button")[0]!.attributes("aria-pressed")).toBe("true");
    await wrapper.findAll("button")[1]!.trigger("click");
    expect(wrapper.emitted("select")).toEqual([["week"]]);
    await wrapper.setProps({ disabled: true });
    await wrapper.findAll("button")[1]!.trigger("click");
    expect(wrapper.emitted("select")).toHaveLength(1);
  });

  it("segmented radios keep numeric values and native keyboard semantics", async () => {
    const wrapper = mount(SegmentedControl, { props: { options: [{ key: 1, label: "一" }, { key: 2, label: "二" }], modelValue: 1 } });
    const radios = wrapper.findAll("input");
    expect((radios[0]!.element as HTMLInputElement).checked).toBe(true);
    expect(radios[0]!.attributes("name")).toBe(radios[1]!.attributes("name"));
    await radios[1]!.setValue(true);
    expect(wrapper.emitted("update:modelValue")).toEqual([[2]]);
    await wrapper.setProps({ modelValue: 2, disabled: true });
    expect((radios[1]!.element as HTMLInputElement).checked).toBe(true);
    expect((radios[1]!.element as HTMLInputElement).disabled).toBe(true);
  });

  it("search updates the draft immediately, debounces live changes, and clears", async () => {
    vi.useFakeTimers();
    const wrapper = mount(SearchField, { props: { value: "", "onUpdate:value": (value: string) => wrapper.setProps({ value }) } });
    const input = wrapper.findComponent(NInput);
    input.vm.$emit("update:value", "SKU");
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("update:value")).toEqual([["SKU"]]);
    await vi.advanceTimersByTimeAsync(299);
    expect(wrapper.emitted("debounced-change")).toBeUndefined();
    input.vm.$emit("update:value", "SKU-2");
    await vi.advanceTimersByTimeAsync(300);
    expect(wrapper.emitted("debounced-change")).toEqual([["SKU-2"]]);
    input.vm.$emit("update:value", "");
    input.vm.$emit("clear");
    await vi.advanceTimersByTimeAsync(300);
    expect(wrapper.emitted("clear")).toHaveLength(1);
    expect(wrapper.emitted("debounced-change")!.at(-1)).toEqual([""]);
  });

  it("Enter, route restoration, disable and unmount cancel pending live searches", async () => {
    vi.useFakeTimers();
    const wrapper = mount(SearchField, { props: { value: "" } });
    const input = wrapper.findComponent(NInput);
    input.vm.$emit("update:value", "first");
    await wrapper.find("input").trigger("keydown", { key: "Enter" });
    await vi.advanceTimersByTimeAsync(300);
    expect(wrapper.emitted("keydown")).toHaveLength(1);
    expect(wrapper.emitted("debounced-change")).toBeUndefined();
    input.vm.$emit("update:value", "stale");
    await wrapper.setProps({ value: "restored" });
    await vi.advanceTimersByTimeAsync(300);
    input.vm.$emit("update:value", "disabled");
    await wrapper.setProps({ disabled: true });
    await vi.advanceTimersByTimeAsync(300);
    expect(wrapper.emitted("debounced-change")).toBeUndefined();
    input.vm.$emit("update:value", "unmounted");
    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(300);
    expect(wrapper.emitted("debounced-change")).toBeUndefined();
  });

  it.each([['FBP', 'azure'], ['realFBS', 'mint'], ['WHD', 'butter']] as const)("maps %s to %s", (channel, tone) => {
    const wrapper = mount(ChannelTag, { props: { channel } });
    expect(wrapper.text()).toBe(channel);
    expect(wrapper.classes()).toContain(`tone-${tone}`);
  });
});
