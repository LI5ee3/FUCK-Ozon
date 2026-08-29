<script setup lang="ts">
import MorphIcon from "./MorphIcon.vue";
import type { IconName } from "../icons/tabler";
import { NCard, NSpin } from "naive-ui";

type SummaryCard = {
  icon: IconName;
  label: string;
  value: string;
  note: string;
  tone: "warning" | "danger" | "peach" | "lavender" | "safe";
};

defineProps<{
  items: ReadonlyArray<SummaryCard>;
  loading: boolean;
}>();
</script>

<template>
  <div v-if="items.length" class="alerts-summary">
    <NCard v-for="card in items" :key="card.label" :bordered="false" class="alerts-summary-card" :class="`alerts-tone-${card.tone}`">
      <div class="alerts-summary-head"><span>{{ card.label }}</span><span class="alerts-summary-icon"><morph-icon :icon="card.icon" size="18" stroke-width="1.8" /></span></div>
      <strong>{{ card.value }}</strong>
      <small>{{ card.note }}</small>
    </NCard>
  </div>
  <div v-else-if="loading" class="alerts-summary-loading"><NSpin size="small" /> <span>预警汇总加载中…</span></div>
</template>
