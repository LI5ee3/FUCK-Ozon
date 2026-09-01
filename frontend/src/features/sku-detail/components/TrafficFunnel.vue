<script setup lang="ts">
import { computed } from "vue";
import { formatInteger, formatMoney, formatNumber } from "../../../shared/utils/format";
import type { AnalyticsTraffic } from "../types";

const props = defineProps<{ data: AnalyticsTraffic }>();
const stages = computed(() => [
  { label: "曝光", value: props.data.impressions, rate: null },
  { label: "商品浏览", value: props.data.product_views, rate: props.data.view_rate },
  { label: "加购", value: props.data.cart_adds, rate: props.data.cart_rate },
  { label: "下单", value: props.data.ordered_units, rate: props.data.order_rate },
]);
function rate(value: number | null): string { return value == null ? "—" : `${formatNumber(value * 100, 1)}%`; }
</script>

<template>
  <div class="sku-detail-funnel">
    <div class="sku-detail-funnel-stages">
      <div v-for="(stage, index) in stages" :key="stage.label" class="sku-detail-funnel-stage">
        <div class="sku-detail-funnel-value"><strong>{{ formatInteger(stage.value) }}</strong><span>{{ stage.label }}</span></div>
        <span v-if="index" class="sku-detail-funnel-rate">{{ rate(stage.rate) }}</span>
        <span v-if="index < stages.length - 1" class="sku-detail-funnel-arrow" aria-hidden="true">→</span>
      </div>
    </div>
    <div class="sku-detail-traffic-facts">
      <span><small>独立访客</small><b>{{ formatInteger(props.data.unique_visitors) }}</b></span>
      <span><small>成交金额</small><b>{{ formatMoney(props.data.revenue, props.data.currency) }}</b></span>
      <span><small>币种</small><b>{{ props.data.currency || "—" }}</b></span>
    </div>
  </div>
</template>
