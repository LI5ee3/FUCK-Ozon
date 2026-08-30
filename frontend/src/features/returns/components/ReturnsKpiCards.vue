<script setup lang="ts">
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import type { IconName } from "../../../shared/icons/tabler";
import { NCard, NTag } from "naive-ui";

type ReturnsKpi = {
  icon: IconName;
  label: string;
  value: string;
  badge: string;
  note: string;
  tone: "azure" | "lavender" | "mint" | "peach" | "butter";
};

defineProps<{
  items: ReadonlyArray<ReturnsKpi>;
}>();
</script>

<template>
  <div v-if="items.length" class="analytics-kpi-grid returns-summary">
    <NCard
      v-for="kpi in items"
      :key="kpi.label"
      :bordered="false"
      class="analytics-kpi-card returns-kpi-card"
      :class="`tone-${kpi.tone}`"
    >
      <div class="analytics-kpi-head">
        <span>{{ kpi.label }}<NTag size="small" round :bordered="false" type="default">{{ kpi.badge }}</NTag></span>
        <span class="analytics-icon-badge tone-badge"><morph-icon :icon="kpi.icon" size="18" stroke-width="1.8" /></span>
      </div>
      <strong class="analytics-kpi-value tone-value">{{ kpi.value }}</strong>
      <small>{{ kpi.note }}</small>
    </NCard>
  </div>
</template>
