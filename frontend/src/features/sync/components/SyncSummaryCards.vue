<script setup lang="ts">
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import type { IconName } from "../../../shared/icons/tabler";
import { NCard } from "naive-ui";

type SyncSummaryCard = {
  icon: IconName;
  label: string;
  value: string;
  note: string;
  tone: "azure" | "peach" | "mint" | "lavender";
};

defineProps<{
  items: ReadonlyArray<SyncSummaryCard>;
}>();
</script>

<template>
  <div class="sync-summary-grid">
    <NCard v-for="card in items" :key="card.label" :bordered="false" class="sync-summary-card" :class="`tone-${card.tone}`">
      <div class="sync-summary-icon tone-badge"><morph-icon :icon="card.icon" size="17" stroke-width="1.8" /></div>
      <span>{{ card.label }}</span>
      <strong class="tone-value">{{ card.value }}</strong>
      <small>{{ card.note }}</small>
    </NCard>
  </div>
</template>
