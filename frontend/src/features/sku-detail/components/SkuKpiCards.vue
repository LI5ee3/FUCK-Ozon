<script setup lang="ts">
import { computed } from "vue";
import { NCard } from "naive-ui";
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import { formatInteger, formatMoney, formatNumber } from "../../../shared/utils/format";
import type { SkuAfterSales, SkuAdvertising, SkuInventory, SkuSales, SkuProfit } from "../types";

const props = defineProps<{
  sales: SkuSales;
  inventory: SkuInventory;
  advertising: SkuAdvertising;
  afterSales: SkuAfterSales;
  profit: SkuProfit;
}>();

function percent(value: number | null): string {
  return value == null ? "—" : `${formatNumber(value * 100, 1)}%`;
}

function money(value: number | null, currency: string): string {
  return value == null || !Number.isFinite(value) ? "—" : formatMoney(value, currency);
}

const cards = computed(() => [
  { icon: "orders" as const, label: "周期销量", value: `${formatInteger(props.sales.summary.units)} 件`, note: `${formatInteger(props.sales.summary.orders)} 个订单`, tone: "azure" },
  { icon: "activity" as const, label: "预测日销", value: props.inventory.forecast_daily == null ? "—" : `${formatNumber(props.inventory.forecast_daily)} 件`, note: "沿用库存预测口径", tone: "mint" },
  { icon: "box" as const, label: "FBP 可售", value: props.inventory.fbp_present == null ? "—" : `${formatInteger(props.inventory.fbp_present)} 件`, note: `可售 ${props.inventory.days_cover == null ? "—" : `${formatNumber(props.inventory.days_cover, 1)} 天`}`, tone: "mint" },
  { icon: "shoppingBag" as const, label: "建议补货", value: props.inventory.recommended_replenishment == null ? "—" : `${formatInteger(props.inventory.recommended_replenishment)} 件`, note: "FBP 库存基准", tone: "butter" },
  { icon: "wallet" as const, label: "广告花费", value: money(props.advertising.summary.spend_rub, "RUB"), note: `DRR ${props.advertising.summary.drr == null ? "—" : `${formatNumber(props.advertising.summary.drr)}%`}`, tone: "butter" },
  { icon: "percent" as const, label: "取消率", value: percent(props.afterSales.cancel_rate), note: `${formatInteger(props.afterSales.cancelled_before_ship)} 个发货前取消`, tone: props.afterSales.cancel_rate ? "peach" : "mint" },
  { icon: "trendingUp" as const, label: "实际利润", value: money(props.profit.actual_profit_cny == null ? null : Number(props.profit.actual_profit_cny), "CNY"), note: `${formatInteger(props.profit.attributed_orders)} 个准确归因订单`, tone: "lavender" },
  { icon: "search" as const, label: "广告订单占比", value: percent(props.advertising.ad_order_share), note: "仅用于经营趋势分析", tone: "azure" },
]);
</script>

<template>
  <div class="sku-detail-kpi-grid">
    <NCard v-for="card in cards" :key="card.label" :bordered="false" class="sku-detail-kpi-card" :class="`tone-${card.tone}`">
      <div class="sku-detail-kpi-head">
        <span>{{ card.label }}</span>
        <span class="sku-detail-icon-badge tone-badge"><MorphIcon :icon="card.icon" size="17" stroke-width="1.8" /></span>
      </div>
      <strong class="sku-detail-kpi-value tone-value">{{ card.value }}</strong>
      <small>{{ card.note }}</small>
    </NCard>
  </div>
</template>
