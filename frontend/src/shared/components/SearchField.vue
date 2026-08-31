<script setup lang="ts">
import { onBeforeUnmount, watch } from "vue";
import { NInput } from "naive-ui";
import MorphIcon from "./MorphIcon.vue";

const props = withDefaults(defineProps<{
  value: string;
  disabled?: boolean;
  debounce?: number;
}>(), { debounce: 300 });
const emit = defineEmits<{
  "update:value": [value: string];
  "debounced-change": [value: string];
  clear: [];
  keydown: [event: KeyboardEvent];
}>();
let timer: ReturnType<typeof setTimeout> | undefined;
let pendingValue: string | undefined;
function cancelPending(): void {
  clearTimeout(timer);
  pendingValue = undefined;
}
function updateValue(value: string): void {
  cancelPending();
  pendingValue = value;
  emit("update:value", value);
  timer = setTimeout(() => {
    pendingValue = undefined;
    emit("debounced-change", value);
  }, props.debounce);
}
function keydown(event: KeyboardEvent): void {
  if (event.key === "Enter") cancelPending();
  emit("keydown", event);
}
// Route restoration or disabling the field must not submit an older draft.
watch(() => props.value, (value) => { if (value !== pendingValue) cancelPending(); });
watch(() => props.disabled, (disabled) => { if (disabled) cancelPending(); });
onBeforeUnmount(cancelPending);
</script>

<template>
  <NInput
    :value="value"
    :disabled="disabled"
    clearable
    :input-props="{ 'aria-label': String($attrs['aria-label'] ?? $attrs.placeholder ?? '搜索') }"
    @update:value="updateValue"
    @clear="$emit('clear')"
    @keydown="keydown"
  >
    <template #prefix><MorphIcon icon="search" size="15" stroke-width="1.8" /></template>
  </NInput>
</template>
