<script setup lang="ts">
import { NCard, NTag } from "naive-ui";
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../../../shared/utils/format";
import type { SkuInventory, SkuInventoryChannel } from "../types";

const props = defineProps<{ data: SkuInventory }>();
function channel(name: string): SkuInventoryChannel { return props.data.channels.find((item) => item.channel === name) ?? { channel: name as SkuInventoryChannel["channel"], source: null, present: null, reserved: null, effective_stock: null, observed_at: null }; }
function value(number: number | null): string { return number == null ? "—" : formatInteger(number); }
function number(number: number | null): string { return number == null ? "—" : formatNumber(number); }
function riskTone(code: SkuInventory["risk_code"]): string { return code === "out_of_stock" || code === "urgent_replenishment" ? "peach" : code === "replenish" || code === "overstock" ? "butter" : code === "sufficient" ? "mint" : ""; }
</script>

<template>
  <NCard :bordered="false" class="sku-detail-panel">
    <template #header><div class="sku-detail-panel-heading"><div><h2><MorphIcon icon="stock" size="18" stroke-width="1.8" />库存与备货</h2><span>需求 = FBP + realFBS；WHD 仅展示，不参与 FBP 补货</span></div><span class="sku-detail-panel-status">{{ props.data.status === "available" ? `更新至 ${formatBeijingDateTime(props.data.data_through)}` : "库存数据不可用" }}</span></div></template>
    <div class="sku-detail-stock-channels">
      <div v-for="name in ['FBP', 'realFBS', 'WHD']" :key="name" class="sku-detail-stock-channel" :class="`channel-${name.toLowerCase()}`">
        <div><strong>{{ name }}</strong><small>{{ name === "WHD" ? "展示口径" : name === "FBP" ? "补货库存" : "需求口径" }}</small></div>
        <span><b>{{ value(channel(name).present) }}</b> 可售</span><span><b>{{ value(channel(name).reserved) }}</b> 预留</span>
      </div>
    </div>
    <div class="sku-detail-stock-grid">
        <span><small>7日销量</small><b>{{ value(props.data.sales_7) }}</b></span><span><small>15日销量</small><b>{{ value(props.data.sales_15) }}</b></span><span><small>30日销量</small><b>{{ value(props.data.sales_30) }}</b></span>
      <span><small>7日均销</small><b>{{ number(props.data.daily_7) }}</b></span><span><small>15日均销</small><b>{{ number(props.data.daily_15) }}</b></span><span><small>30日均销</small><b>{{ number(props.data.daily_30) }}</b></span>
      <span><small>预测日销</small><b>{{ number(props.data.forecast_daily) }}</b></span><span><small>可售天数</small><b>{{ number(props.data.days_cover) }}</b></span><span><small>预计缺货</small><b>{{ props.data.expected_stockout_date || "—" }}</b></span>
      <span><small>采购交期</small><b>{{ formatInteger(props.data.lead_time_days) }} 天</b></span><span><small>目标覆盖</small><b>{{ formatInteger(props.data.target_cover_days) }} 天</b></span><span><small>建议补货</small><b>{{ value(props.data.recommended_replenishment) }} 件</b></span>
    </div>
    <div class="sku-detail-stock-risk"><span>趋势：{{ props.data.trend || "—" }}</span><NTag v-if="props.data.risk_status" :bordered="false" round size="small" :class="riskTone(props.data.risk_code) ? `sku-detail-risk-tag sku-detail-risk-tag--${riskTone(props.data.risk_code)}` : 'sku-detail-risk-tag'">{{ props.data.risk_status }}</NTag><span v-else>风险：—</span></div>
  </NCard>
</template>
