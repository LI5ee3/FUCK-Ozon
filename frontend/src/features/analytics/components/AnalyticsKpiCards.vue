<script setup lang="ts">
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import type { IconName } from "../../../shared/icons/tabler";
import { NCard } from "naive-ui";

type AnalyticsKpi = {
  icon: IconName;
  label: string;
  value?: string;
  lines?: string[];
  note?: string;
  tone: "azure" | "lavender" | "mint" | "peach" | "blue";
};

defineProps<{
  items: ReadonlyArray<AnalyticsKpi>;
}>();
</script>

<template>
  <div class="analytics-kpi-grid">
    <NCard
      v-for="kpi in items"
      :key="kpi.label"
      :bordered="false"
      class="analytics-kpi-card"
      :class="`analytics-tone-${kpi.tone}`"
    >
      <div class="analytics-kpi-head">
        <span>{{ kpi.label }}</span>
        <span class="analytics-icon-badge"><morph-icon :icon="kpi.icon" size="18" stroke-width="1.8" /></span>
      </div>
      <strong v-if="kpi.lines" class="analytics-kpi-money">
        <span v-for="(line, index) in kpi.lines" :key="`${kpi.label}-${index}`">{{ line }}</span>
      </strong>
      <strong v-else class="analytics-kpi-value">{{ kpi.value }}</strong>
      <small v-if="kpi.note">{{ kpi.note }}</small>
    </NCard>
  </div>
</template>
