<script setup lang="ts" generic="T extends string">
defineProps<{
  options: ReadonlyArray<{ key: T; label: string }>;
  activeKey: T | "";
  disabled?: boolean;
}>();
defineEmits<{ select: [key: T] }>();
</script>

<template>
  <div class="opanel-date-presets" role="group">
    <button
      v-for="option in options"
      :key="option.key"
      type="button"
      :aria-pressed="activeKey === option.key"
      :disabled="disabled"
      @click="$emit('select', option.key)"
    >{{ option.label }}</button>
  </div>
</template>
