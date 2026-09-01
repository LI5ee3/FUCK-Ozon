<script setup lang="ts">
import { NCard, NTag } from "naive-ui";
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import { formatInteger, formatMoney } from "../../../shared/utils/format";
import type { SkuProfit } from "../types";

const props = defineProps<{ data: SkuProfit }>();
const reasonLabels: Record<string, string> = { multi_sku_order: "多 SKU 待分摊", missing_finance: "缺 Finance", missing_erp_cost: "缺 ERP 成本", quantity_mismatch: "数量不一致", missing_exchange_rate: "缺汇率", exchange_rate_mismatch: "汇率不一致", finance_currency_mismatch: "Finance 币种异常", invalid_profit_data: "利润数据无效" };
function money(value: string | null): string { const number = value == null ? NaN : Number(value); return Number.isFinite(number) ? formatMoney(number, "CNY") : "—"; }
function statusLabel(status: SkuProfit["status"]): string { return status === "complete" ? "完整" : status === "incomplete" ? "不完整" : "暂无可归因利润"; }
</script>

<template>
  <NCard :bordered="false" class="sku-detail-panel">
    <template #header><div class="sku-detail-panel-heading"><div><h2><MorphIcon icon="trendingUp" size="18" stroke-width="1.8" />实际利润</h2><span>仅纳入可准确归因的单 SKU 订单；金额单位 CNY</span></div><NTag :bordered="false" round size="small" :class="`sku-detail-profit-tag sku-detail-profit-tag--${props.data.status}`">{{ statusLabel(props.data.status) }}</NTag></div></template>
    <div class="sku-detail-profit-main"><strong>{{ money(props.data.actual_profit_cny) }}</strong><span>准确归因订单 {{ formatInteger(props.data.attributed_orders) }}</span></div>
    <div class="sku-detail-profit-facts"><span>多 SKU 待分摊 <b>{{ formatInteger(props.data.unattributed_multi_sku_orders) }}</b></span><span>数据不完整订单 <b>{{ formatInteger(props.data.incomplete_orders) }}</b></span><span>归因商品件数 <b>{{ formatInteger(props.data.units) }}</b></span><span>每件实际利润 <b>{{ money(props.data.avg_profit_per_unit_cny) }}</b></span></div>
    <div v-if="Object.keys(props.data.incomplete_reasons).length" class="sku-detail-profit-reasons"><span v-for="(count, reason) in props.data.incomplete_reasons" :key="reason">{{ reasonLabels[reason] || reason }} {{ count }}</span></div>
  </NCard>
</template>
