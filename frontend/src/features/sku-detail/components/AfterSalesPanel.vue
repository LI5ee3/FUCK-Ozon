<script setup lang="ts">
import { NCard } from "naive-ui";
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import { formatInteger, formatNumber } from "../../../shared/utils/format";
import type { SkuAfterSales } from "../types";

const props = defineProps<{ data: SkuAfterSales }>();
function percent(value: number | null): string { return value == null ? "—" : `${formatNumber(value * 100, 1)}%`; }
</script>

<template>
  <NCard :bordered="false" class="sku-detail-panel">
    <template #header><div class="sku-detail-panel-heading"><div><h2><MorphIcon icon="returns" size="18" stroke-width="1.8" />售后健康</h2><span>退货率 / 投诉率均以当前周期创建且包含该 SKU 的订单为分母</span></div></div></template>
    <div class="sku-detail-after-sales-grid"><span><small>订单</small><b>{{ formatInteger(props.data.orders) }}</b></span><span><small>发货前取消</small><b>{{ formatInteger(props.data.cancelled_before_ship) }} · {{ percent(props.data.cancel_rate) }}</b></span><span><small>退货订单（记录 {{ formatInteger(props.data.returns) }}）</small><b>{{ formatInteger(props.data.return_orders) }} · {{ percent(props.data.return_rate) }}</b></span><span><small>投诉订单</small><b>{{ formatInteger(props.data.complaint_orders) }} · {{ percent(props.data.complaint_rate) }}</b></span></div>
    <div v-if="props.data.cancel_reasons.length" class="sku-detail-cancel-reasons"><span v-for="item in props.data.cancel_reasons" :key="item.reason">{{ item.reason }} <b>{{ formatInteger(item.count) }}</b></span></div>
    <p class="sku-detail-completeness">退货记录数按退货发生周期统计；退货率和投诉率按当前周期订单 cohort 统计，并使用截至当前已知的退货 / 投诉结果。</p>
  </NCard>
</template>
