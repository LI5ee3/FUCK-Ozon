<script setup lang="ts">
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import type { BusinessSignal, SignalSeverity } from "../types";

defineProps<{ signals: BusinessSignal[] }>();
function iconFor(severity: SignalSeverity): "alertTriangle" | "alertCircle" | "check" | "activity" { return severity === "critical" || severity === "warning" ? "alertTriangle" : severity === "positive" ? "check" : "activity"; }
</script>

<template>
  <section class="sku-detail-signals" aria-labelledby="sku-detail-signals-title">
    <div class="sku-detail-section-heading"><h2 id="sku-detail-signals-title"><MorphIcon icon="alertTriangle" size="18" stroke-width="1.8" />经营诊断</h2><span>确定性规则提示，最多展示 5 条</span></div>
    <div v-if="signals.length" class="sku-detail-signal-list"><article v-for="signal in signals" :key="signal.code" class="sku-detail-signal" :class="`is-${signal.severity}`"><MorphIcon :icon="iconFor(signal.severity)" size="17" stroke-width="1.9" /><div><strong>{{ signal.title }}</strong><p>{{ signal.message }}</p></div></article></div>
    <p v-else class="sku-detail-no-signals">当前没有需要优先处理的经营提示。</p>
  </section>
</template>
