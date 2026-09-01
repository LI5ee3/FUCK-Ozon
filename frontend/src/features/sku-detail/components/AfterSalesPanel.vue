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
    <template #header><div class="sku-detail-panel-heading"><div><h2><MorphIcon icon="returns" size="18" stroke-width="1.8" />售后健康</h2><span>比率分母：当前周期内包含该 SKU 的订单数</span></div></div></template>
    <div class="sku-detail-after-sales-grid"><span><small>订单</small><b>{{ formatInteger(props.data.orders) }}</b></span><span><small>发货前取消</small><b>{{ formatInteger(props.data.cancelled_before_ship) }} · {{ percent(props.data.cancel_rate) }}</b></span><span><small>退货订单</small><b>{{ formatInteger(props.data.return_orders) }} · {{ percent(props.data.return_rate) }}</b></span><span><small>投诉订单</small><b>{{ formatInteger(props.data.complaint_orders) }} · {{ percent(props.data.complaint_rate) }}</b></span></div>
    <div v-if="props.data.cancel_reasons.length" class="sku-detail-cancel-reasons"><span v-for="item in props.data.cancel_reasons" :key="item.reason">{{ item.reason }} <b>{{ formatInteger(item.count) }}</b></span></div>
    <p class="sku-detail-completeness">退货与投诉均按可精确关联 SKU 的记录统计；重复 posting / complaint 已去重。</p>
  </NCard>
</template>
