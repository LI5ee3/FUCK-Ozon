<script setup lang="ts">
import { computed } from "vue";
import { NCard } from "naive-ui";
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import EmptyState from "../../../shared/components/EmptyState.vue";
import AdsTrendChart from "../../advertising/components/AdsTrendChart.vue";
import { formatInteger, formatNumber } from "../../../shared/utils/format";
import type { SkuAdvertising } from "../types";

const props = defineProps<{ data: SkuAdvertising }>();
const summary = computed(() => props.data.summary);
function money(value: number | null): string { return value == null || !Number.isFinite(value) ? "—" : `${formatNumber(value)} RUB`; }
function percent(value: number | null): string { return value == null ? "—" : `${formatNumber(value)}%`; }
</script>

<template>
  <NCard :bordered="false" class="sku-detail-panel sku-detail-ad-panel">
    <template #header><div class="sku-detail-panel-heading"><div><h2><MorphIcon icon="tag" size="18" stroke-width="1.8" />广告表现</h2><span>直接读取 ad_sku_daily；金额单位 RUB</span></div><span class="sku-detail-panel-status">{{ props.data.status === "empty" ? "暂无广告数据" : `更新至 ${props.data.data_through || "—"}` }}</span></div></template>
    <EmptyState v-if="props.data.status === 'empty'" title="当前周期暂无广告数据" icon="tag" />
    <template v-else>
    <div class="sku-detail-ad-summary">
      <span><small>曝光</small><b>{{ formatInteger(summary.impressions) }}</b></span>
      <span><small>点击</small><b>{{ formatInteger(summary.clicks) }}</b></span>
      <span><small>加购</small><b>{{ formatInteger(summary.cart_adds) }}</b></span>
      <span><small>广告花费</small><b>{{ money(summary.spend_rub) }}</b></span>
      <span><small>广告订单</small><b>{{ formatInteger(summary.orders) }}</b></span>
      <span><small>广告销售额</small><b>{{ money(summary.revenue_rub) }}</b></span>
      <span><small>CTR</small><b>{{ percent(summary.ctr) }}</b></span>
      <span><small>平均 CPC</small><b>{{ money(summary.avg_cpc_rub) }}</b></span>
      <span><small>DRR</small><b>{{ percent(summary.drr) }}</b></span>
      <span><small>ROAS</small><b>{{ summary.roas == null ? "—" : formatNumber(summary.roas) }}</b></span>
      <span><small>Campaign</small><b>{{ formatInteger(summary.campaign_count) }}</b></span>
    </div>
    <div v-if="props.data.trend.length" class="sku-detail-ad-chart"><AdsTrendChart :data="props.data.trend" /></div>
    </template>
    <p class="sku-detail-disclaimer">广告订单与订单数据库统计口径可能存在差异，该指标仅用于经营趋势分析，不作为财务结算依据。</p>
  </NCard>
</template>
