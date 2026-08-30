<script setup lang="ts">
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import type { IconName } from "../../../shared/icons/tabler";
import { NCard } from "naive-ui";

type RiskKpi = {
  icon: IconName;
  label: string;
  value: string;
  badge?: string;
  note: string;
  tone: "azure" | "lavender" | "mint" | "peach" | "butter";
};

defineProps<{
  items: ReadonlyArray<RiskKpi>;
}>();
</script>

<template>
  <div class="analytics-kpi-grid risk-kpi-grid">
    <NCard
      v-for="kpi in items"
      :key="kpi.label"
      :bordered="false"
      class="analytics-kpi-card"
      :class="kpi.tone"
    >
      <div class="analytics-kpi-head">
        <span>{{ kpi.label }}</span>
        <span class="analytics-icon-badge tone-badge"><morph-icon :icon="kpi.icon" size="18" stroke-width="1.8" /></span>
      </div>
      <strong class="analytics-kpi-value tone-value">{{ kpi.value }}</strong>
      <small v-if="kpi.badge" class="risk-kpi-badge">{{ kpi.badge }}</small>
      <small>{{ kpi.note }}</small>
    </NCard>
  </div>
</template>
