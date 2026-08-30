<script setup lang="ts">
import MorphIcon from "./MorphIcon.vue";
import type { IconName } from "../icons/tabler";

withDefaults(
  defineProps<{
    icon?: IconName;
    title: string;
    hint?: string;
  }>(),
  { icon: "search", hint: undefined },
);
</script>

<template>
  <div class="opanel-empty">
    <span class="opanel-empty-badge"><MorphIcon :icon="icon" size="20" stroke-width="1.8" /></span>
    <strong>{{ title }}</strong>
    <small v-if="hint">{{ hint }}</small>
    <slot />
  </div>
</template>
