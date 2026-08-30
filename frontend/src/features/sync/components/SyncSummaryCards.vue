<script setup lang="ts">
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import type { IconName } from "../../../shared/icons/tabler";
import { NCard, NSkeleton } from "naive-ui";

type SyncSummaryCard = {
  icon: IconName;
  label: string;
  value: string;
  note: string;
  tone: "azure" | "lavender" | "mint" | "peach" | "butter";
};

defineProps<{
  items: ReadonlyArray<SyncSummaryCard>;
  loading: boolean;
}>();
</script>

<template>
  <div v-if="items.length" class="analytics-kpi-grid">
    <NCard v-for="card in items" :key="card.label" :bordered="false" class="analytics-kpi-card" :class="`tone-${card.tone}`">
      <div class="analytics-kpi-head"><span>{{ card.label }}</span><span class="analytics-icon-badge tone-badge"><morph-icon :icon="card.icon" size="18" stroke-width="1.8" /></span></div>
      <strong class="analytics-kpi-value tone-value">{{ card.value }}</strong>
      <small>{{ card.note }}</small>
    </NCard>
  </div>
  <div v-else-if="loading" class="analytics-kpi-grid">
    <NCard v-for="i in 4" :key="i" :bordered="false" class="analytics-kpi-card">
      <NSkeleton text width="55%" />
      <NSkeleton text width="72%" class="kpi-skeleton-value" />
      <NSkeleton text width="42%" />
    </NCard>
  </div>
</template>
