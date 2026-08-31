<script setup lang="ts" generic="T extends string | number">
import { useId } from "vue";

defineProps<{
  options: ReadonlyArray<{ key: T; label: string }>;
  modelValue: T;
  disabled?: boolean;
}>();
defineEmits<{ "update:modelValue": [value: T] }>();
const name = useId();
</script>

<template>
  <div class="opanel-segmented" role="radiogroup" :aria-disabled="disabled || undefined">
    <label v-for="option in options" :key="option.key">
      <input
        type="radio"
        :name="name"
        :value="option.key"
        :checked="modelValue === option.key"
        :disabled="disabled"
        @change="$emit('update:modelValue', option.key)"
      >
      <span>{{ option.label }}</span>
    </label>
  </div>
</template>
