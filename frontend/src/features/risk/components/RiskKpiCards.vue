<script setup lang="ts">
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import type { IconName } from "../../../shared/icons/tabler";
import { NCard, NSkeleton } from "naive-ui";

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
  loading?: boolean;
}>();
</script>

<template>
  <div v-if="loading && !items.length" class="analytics-kpi-grid risk-kpi-grid">
    <NCard v-for="i in 4" :key="i" :bordered="false" class="analytics-kpi-card">
      <NSkeleton text width="55%" />
      <NSkeleton text width="72%" class="kpi-skeleton-value" />
      <NSkeleton text width="42%" />
    </NCard>
  </div>
  <div v-else-if="items.length" class="analytics-kpi-grid risk-kpi-grid">
    <NCard
      v-for="kpi in items"
      :key="kpi.label"
      :bordered="false"
      class="analytics-kpi-card"
      :class="`tone-${kpi.tone}`"
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
