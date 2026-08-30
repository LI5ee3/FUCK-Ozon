<script setup lang="ts">
import "./dashboard.css";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import type { IconName } from "../../shared/icons/tabler";
import {
  NAlert,
  NButton,
  NCard,
  NDatePicker,
  NEmpty,
  NSpin,
  NStatistic,
  NTag,
  useMessage,
} from "naive-ui";
import { getErrorMessage } from "../../shared/api/client";
import { getDashboardSummary, getOrderTrend } from "./api";
import { useShop } from "../../shared/composables/useShop";
import type {
  DashboardSummary,
  Granularity,
  OrderTrend,
  OverviewChannel,
  TopProduct,
  TrendBucket,
} from "./types";
import {
  formatBeijingDateTime,
  formatHours,
  formatInteger,
  formatPercent,
} from "../../shared/utils/format";
import { formatGmvAmount } from "./format";
import OrderTrendChart from "./components/OrderTrendChart.vue";
import { beijingThreeMonthRange, standardDatePresetRange, type DateRange, type StandardDatePreset } from "../../shared/utils/date";

type DatePreset = StandardDatePreset | "";
type Insight = {
  icon: IconName;
  label: string;
  value: string;
  suffix?: string;
  secondary?: string;
  foot: string;
  sub?: string;
  trend?: "up" | "down";
};

const { selectedShopId } = useShop();
const message = useMessage();
const granularity = ref<Granularity>("week");
const summary = ref<DashboardSummary | null>(null);
const trend = ref<OrderTrend | null>(null);
const loading = ref(false);
const error = ref("");
let requestId = 0;

const dateRange = ref<DateRange>(beijingThreeMonthRange());
const activePreset = ref<DatePreset>("3months");
const presets: ReadonlyArray<{ key: Exclude<DatePreset, "">; label: string }> = [
  { key: "today", label: "今天" },
  { key: "3days", label: "3天内" },
  { key: "7days", label: "7天内" },
  { key: "3months", label: "近三个月" },
  { key: "all", label: "全部时间" },
];
const granularities: ReadonlyArray<{ key: Granularity; label: string }> = [
  { key: "day", label: "日" },
  { key: "week", label: "周" },
  { key: "month", label: "月" },
];

async function loadDashboard(): Promise<void> {
  if (activePreset.value) dateRange.value = standardDatePresetRange(activePreset.value);
  const currentRequest = ++requestId;
  loading.value = true;
  error.value = "";
  summary.value = null;
  trend.value = null;

  const [summaryResult, trendResult] = await Promise.allSettled([
    getDashboardSummary(selectedShopId.value, dateRange.value[0], dateRange.value[1]),
    getOrderTrend(selectedShopId.value, granularity.value),
  ]);

  if (currentRequest !== requestId) return;
  loading.value = false;
  if (summaryResult.status === "rejected" || trendResult.status === "rejected") {
    const cause = summaryResult.status === "rejected"
      ? summaryResult.reason
      : trendResult.status === "rejected"
        ? trendResult.reason
        : new Error("总览加载失败");
    error.value = getErrorMessage(cause);
    message.error(error.value);
    return;
  }
  summary.value = summaryResult.value;
  trend.value = trendResult.value;
}

function retry(): void {
  void loadDashboard();
}

function updateDateRange(value: string | [string, string] | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  dateRange.value = [value[0], value[1]];
  activePreset.value = "";
  void loadDashboard();
}

function selectPreset(preset: Exclude<DatePreset, "">): void {
  dateRange.value = standardDatePresetRange(preset);
  activePreset.value = preset;
  void loadDashboard();
}

function selectGranularity(value: Granularity): void {
  if (granularity.value === value) return;
  granularity.value = value;
  void loadDashboard();
}

function channelClass(channel: OverviewChannel["channel"]): string {
  return channel === "FBP" ? "fbp" : channel === "realFBS" ? "fbs" : "whd";
}

function channelShare(channel: OverviewChannel): number {
  const totalOrders = Math.max(1, summary.value?.totals.orders ?? 0);
  return Math.min(100, Math.round((channel.orders / totalOrders) * 100));
}

function channelCancelRate(channel: OverviewChannel): number {
  return channel.pieces > 0 ? channel.cancelled_pieces / channel.pieces : 0;
}

function timingValue(value: number | null, insufficient: boolean): string {
  return insufficient ? "数据不足" : formatHours(value);
}

function productBarWidth(product: TopProduct): number {
  const maxPieces = Math.max(1, ...(summary.value?.top_products ?? []).map((item) => item.pieces));
  return Math.max(4, Math.round((product.pieces / maxPieces) * 100));
}

function trendDate(bucket: TrendBucket, granularityValue: Granularity): string {
  return granularityValue === "day" ? bucket.from.slice(5) : `${bucket.from.slice(5)} ~ ${bucket.to.slice(5)}`;
}

const kpis = computed<Array<{ label: string; value: string; note: string; icon: IconName; tone: string }>>(() => {
  if (!summary.value) return [];
  const data = summary.value;
  return [
    { label: "成交金额 (GMV)", value: formatGmvAmount(data.gmv), note: data.gmv.missing_rate_orders ? `可折算GMV · 缺汇率 ${formatInteger(data.gmv.missing_rate_orders)} 单` : "有效订单总成交额", icon: "shoppingBag", tone: "azure" },
    { label: "有效订单数", value: formatInteger(data.totals.orders), note: "不同订单号", icon: "orders", tone: "peach" },
    { label: "有效货件数", value: formatInteger(data.totals.pieces), note: "商品数量合计", icon: "package", tone: "mint" },
    { label: "发货后取消订单", value: formatInteger(data.totals.cancelled_orders), note: "产生物流成本后取消", icon: "alertTriangle", tone: "lavender" },
    { label: "发货后取消率", value: formatPercent(data.totals.cancel_rate), note: "按有效货件数折算", icon: "percent", tone: "blue" },
  ];
});

const trendInsights = computed<Insight[]>(() => {
  const data = trend.value;
  const buckets = data?.buckets ?? [];
  if (!data || buckets.length === 0) return [];
  const maxBucket = buckets.reduce((max, bucket) => (bucket.orders > max.orders ? bucket : max), buckets[0]);
  const nonZeroBuckets = buckets.filter((bucket) => bucket.orders > 0);
  const totalOrders = buckets.reduce((total, bucket) => total + bucket.orders, 0);
  const averageOrders = Math.round(totalOrders / (nonZeroBuckets.length || buckets.length || 1));
  const averageLabel = data.granularity === "day" ? "日均" : data.granularity === "week" ? "周均" : "月均";
  const latestBucket = buckets[buckets.length - 1];
  const previousBucket = buckets.length > 1 ? buckets[buckets.length - 2] : null;
  const latestOrders = latestBucket.orders;
  let displayOrders = latestOrders;
  let cardTitle = "最新单量";
  let growthText = "最新一期";
  let trendDirection: Insight["trend"];
  let sub = "";
  if (latestOrders === 0 && previousBucket && previousBucket.orders > 0) {
    const previousPreviousBucket = buckets.length > 2 ? buckets[buckets.length - 3] : null;
    const comparison = previousPreviousBucket && previousPreviousBucket.orders > 0
      ? Math.round(((previousBucket.orders - previousPreviousBucket.orders) / previousPreviousBucket.orders) * 100)
      : null;
    displayOrders = previousBucket.orders;
    cardTitle = data.granularity === "week" ? "上周单量" : data.granularity === "month" ? "上月单量" : "昨日单量";
    growthText = comparison === null ? "完整周期" : comparison >= 0 ? `+${comparison}% 环比` : `${comparison}% 环比`;
    trendDirection = comparison === null ? undefined : comparison >= 0 ? "up" : "down";
    sub = `本期(${latestBucket.from.slice(5)}) 进行中`;
  } else if (previousBucket && previousBucket.orders > 0) {
    const growth = Math.round(((latestOrders - previousBucket.orders) / previousBucket.orders) * 100);
    growthText = growth >= 0 ? `+${growth}% 环比` : `${growth}% 环比`;
    trendDirection = growth >= 0 ? "up" : "down";
    sub = data.granularity === "day" ? "较前一日" : data.granularity === "week" ? "较前一周" : "较前一月";
  }
  return [
    { icon: "flame", label: "最高峰值", value: formatInteger(maxBucket.orders), suffix: "单", foot: trendDate(maxBucket, data.granularity) },
    { icon: "barChart", label: "周期均值", value: formatInteger(averageOrders), suffix: `单/${averageLabel}`, foot: `共 ${nonZeroBuckets.length} 个有单${averageLabel.slice(0, 1)}` },
    { icon: "trendingUp", label: cardTitle, value: formatInteger(displayOrders), suffix: "单", foot: growthText, sub, trend: trendDirection },
  ];
});

const channelInsights = computed<Insight[]>(() => {
  const data = summary.value;
  if (!data) return [];
  const channels = data.channels;
  const totalOrders = Math.max(1, data.totals.orders);
  const totalPieces = data.totals.pieces;
  const topChannel = [...channels].sort((left, right) => right.orders - left.orders)[0];
  const activeChannels = channels.filter((channel) => channel.orders > 0);
  const bestChannel = [...activeChannels].sort((left, right) => channelCancelRate(left) - channelCancelRate(right))[0];
  const bestRate = bestChannel ? channelCancelRate(bestChannel) : 0;
  return [
    { icon: "award", label: "主力履约渠道", value: topChannel?.channel ?? "—", secondary: `占比 ${topChannel ? Math.min(100, Math.round((topChannel.orders / totalOrders) * 100)) : 0}%`, foot: `${formatInteger(topChannel?.orders)}单 · ${formatInteger(topChannel?.pieces)}件` },
    { icon: "package", label: "综合货单比", value: data.totals.orders > 0 ? (totalPieces / data.totals.orders).toFixed(2) : "1.00", suffix: "件/单", foot: `共 ${formatInteger(totalPieces)}件 · ${formatInteger(data.totals.orders)}单` },
    { icon: "shieldCheck", label: "最优履约质量", value: bestChannel?.channel ?? "—", secondary: `取消 ${formatPercent(bestRate)}`, foot: `发货后取消 ${formatInteger(bestChannel?.cancelled_pieces)}件`, trend: bestRate === 0 ? "up" : undefined },
  ];
});

const timelinessInsights = computed<Insight[]>(() => {
  const rows = summary.value?.timeliness ?? [];
  const validShip = rows.filter((row) => !row.ship_sample_insufficient && row.p50_ship_hours !== null);
  const fastestShip = [...validShip].sort((left, right) => (left.p50_ship_hours ?? 0) - (right.p50_ship_hours ?? 0))[0];
  const totalShipSamples = rows.reduce((total, row) => total + row.ship_samples, 0);
  const totalDeliverySamples = rows.reduce((total, row) => total + row.delivery_samples, 0);
  return [
    { icon: "bolt", label: "发货最快渠道", value: fastestShip?.channel ?? "—", secondary: fastestShip ? formatHours(fastestShip.p50_ship_hours) : "样本积累中", foot: fastestShip ? `约 ${((fastestShip.p50_ship_hours ?? 0) / 24).toFixed(1)} 天内完成出库` : "各渠道正在积累发货数据" },
    { icon: "clock", label: "配送时效追踪", value: totalDeliverySamples > 0 ? `${formatInteger(totalDeliverySamples)}单` : "P50 / P90", secondary: totalDeliverySamples > 0 ? "已交付样本" : "时效监控", foot: totalDeliverySamples > 0 ? "持续监控末端签收周期" : "监控全链路最后一公里交付" },
    { icon: "checkCircle", label: "履约时效样本", value: formatInteger(totalShipSamples), suffix: "单有效样本", foot: "已纳入 P50 / P90 建模" },
  ];
});

const topProductsInsights = computed<Insight[]>(() => {
  const products = summary.value?.top_products ?? [];
  const totalPieces = summary.value?.totals.pieces ?? 0;
  const top5Pieces = products.reduce((total, product) => total + product.pieces, 0);
  const top5CancelPieces = products.reduce((total, product) => total + Math.round(product.pieces * product.cancel_rate), 0);
  const top5CancelRate = top5Pieces > 0 ? top5CancelPieces / top5Pieces : 0;
  const top1 = products[0];
  return [
    { icon: "flame", label: "Top 5 销量集中度", value: formatInteger(top5Pieces), suffix: "件", secondary: `占比 ${totalPieces > 0 ? Math.min(100, Math.round((top5Pieces / totalPieces) * 100)) : 0}%`, foot: "前 5 款核心爆品合计销量" },
    { icon: "award", label: "榜首爆品销量", value: formatInteger(top1?.pieces), suffix: "件", secondary: `${formatInteger(top1?.orders)}单`, foot: "领跑全店单品销售表现" },
    { icon: "shieldCheck", label: "Top 5 综合取消率", value: formatPercent(top5CancelRate), secondary: top5CancelRate <= 0.05 ? "履约健康" : "需关注", foot: top5CancelRate <= 0.05 ? "爆品退订率处于健康水平" : "部分爆品取消率偏高", trend: top5CancelRate <= 0.05 ? "up" : "down" },
  ];
});

function insightClass(insight: Insight): string {
  return insight.trend === "up" ? "dashboard-insight-foot--up" : insight.trend === "down" ? "dashboard-insight-foot--down" : "";
}

watch(selectedShopId, () => {
  void loadDashboard();
});

onMounted(() => {
  void loadDashboard();
});

onBeforeUnmount(() => {
  requestId += 1;
});
</script>

<template>
  <section class="dashboard-view">
    <div class="dashboard-controls">
      <div class="dashboard-date-control">
        <span class="dashboard-control-label">统计日期</span>
        <NDatePicker
          :formatted-value="dateRange"
          type="daterange"
          value-format="yyyy-MM-dd"
          separator="至"
          :clearable="false"
          class="dashboard-date-picker"
          aria-label="总览日期范围"
          @update:formatted-value="updateDateRange"
        />
        <div class="dashboard-presets" aria-label="日期快捷范围">
          <NButton
            v-for="preset in presets"
            :key="preset.key"
            size="small"
            :type="activePreset === preset.key ? 'primary' : 'default'"
            :secondary="activePreset !== preset.key"
            @click="selectPreset(preset.key)"
          >
            {{ preset.label }}
          </NButton>
        </div>
      </div>
      <div class="dashboard-data-through">
        <span class="dashboard-data-dot" aria-hidden="true" />
        <span>数据截止</span>
        <strong>{{ summary ? formatBeijingDateTime(summary.data_through) : "暂无" }}</strong>
      </div>
    </div>

    <section v-if="loading" class="dashboard-state" aria-live="polite">
      <NSpin size="large" />
      <span>正在加载总览…</span>
    </section>

    <NAlert v-else-if="error" type="error" title="总览加载失败" class="dashboard-error" role="alert">
      <div class="dashboard-error-content">
        <span>{{ error }}</span>
        <NButton text type="error" @click="retry">重试</NButton>
      </div>
    </NAlert>

    <template v-else-if="summary && trend">
      <div class="dashboard-kpi-grid">
        <NCard
          v-for="kpi in kpis"
          :key="kpi.label"
          :bordered="false"
          class="dashboard-kpi-card"
          :class="`dashboard-tone-${kpi.tone}`"
        >
          <div class="dashboard-kpi-head">
            <span>{{ kpi.label }}</span>
            <span class="dashboard-icon-badge"><morph-icon :icon="kpi.icon" size="18" stroke-width="1.8" /></span>
          </div>
          <NStatistic :value="kpi.value" class="dashboard-kpi-value" />
          <small>{{ kpi.note }}</small>
        </NCard>
      </div>

      <div class="dashboard-grid-two">
        <NCard :bordered="false" class="dashboard-panel">
          <template #header>
            <div class="dashboard-panel-heading">
              <div>
                <h2><morph-icon icon="trendingUp" size="18" stroke-width="1.8" />订单量趋势</h2>
                <span>柱高表示有效订单数；按北京时间归组</span>
              </div>
              <div class="dashboard-granularity" role="group" aria-label="趋势粒度">
                <NButton
                  v-for="item in granularities"
                  :key="item.key"
                  size="small"
                  :type="granularity === item.key ? 'primary' : 'default'"
                  :secondary="granularity !== item.key"
                  @click="selectGranularity(item.key)"
                >
                  {{ item.label }}
                </NButton>
              </div>
            </div>
          </template>
          <OrderTrendChart v-if="trend.buckets.length" :data="trend" />
          <NEmpty v-else description="暂无趋势数据" class="dashboard-empty" />
          <div v-if="trendInsights.length" class="dashboard-insights">
            <div v-for="insight in trendInsights" :key="insight.label" class="dashboard-insight-card">
              <div class="dashboard-insight-head"><morph-icon :icon="insight.icon" size="14" stroke-width="1.8" /><span>{{ insight.label }}</span></div>
              <strong class="dashboard-insight-value">{{ insight.value }}<small v-if="insight.suffix">{{ insight.suffix }}</small><small v-if="insight.secondary">{{ insight.secondary }}</small></strong>
              <span class="dashboard-insight-foot" :class="insightClass(insight)">{{ insight.foot }}<small v-if="insight.sub">{{ insight.sub }}</small></span>
            </div>
          </div>
        </NCard>

        <NCard :bordered="false" class="dashboard-panel">
          <template #header>
            <div class="dashboard-panel-heading">
              <div>
                <h2><morph-icon icon="layers" size="18" stroke-width="1.8" />渠道概览</h2>
                <span>各履约渠道订单与取消结构</span>
              </div>
            </div>
          </template>
          <div v-if="summary.channels.length" class="dashboard-channel-list">
            <div v-for="channel in summary.channels" :key="channel.channel" class="dashboard-channel-card">
              <div class="dashboard-channel-top">
                <div class="dashboard-channel-brand">
                  <NTag round :bordered="false" :class="`dashboard-channel-tag dashboard-channel-tag--${channelClass(channel.channel)}`">{{ channel.channel }}</NTag>
                  <span>订单占比 <b>{{ channelShare(channel) }}%</b></span>
                </div>
                <div class="dashboard-channel-track"><span :class="`dashboard-channel-fill dashboard-channel-fill--${channelClass(channel.channel)}`" :style="{ width: `${channelShare(channel)}%` }" /></div>
              </div>
              <div class="dashboard-channel-metrics">
                <div><span>有效订单</span><strong>{{ formatInteger(channel.orders) }}<small>单</small></strong></div>
                <div><span>有效货件</span><strong>{{ formatInteger(channel.pieces) }}<small>件</small></strong></div>
                <div><span>发货后取消</span><strong :class="{ 'is-danger': channel.cancelled_pieces > 0 }">{{ formatInteger(channel.cancelled_pieces) }}<small>件</small></strong></div>
                <div><span>发货取消率</span><strong :class="{ 'is-danger': channelCancelRate(channel) > 0.05 }">{{ formatPercent(channelCancelRate(channel)) }}</strong></div>
              </div>
            </div>
          </div>
          <NEmpty v-else description="暂无渠道数据" class="dashboard-empty dashboard-empty--compact" />
          <div v-if="channelInsights.length" class="dashboard-insights">
            <div v-for="insight in channelInsights" :key="insight.label" class="dashboard-insight-card">
              <div class="dashboard-insight-head"><morph-icon :icon="insight.icon" size="14" stroke-width="1.8" /><span>{{ insight.label }}</span></div>
              <strong class="dashboard-insight-value">{{ insight.value }}<small v-if="insight.suffix">{{ insight.suffix }}</small><small v-if="insight.secondary">{{ insight.secondary }}</small></strong>
              <span class="dashboard-insight-foot" :class="insightClass(insight)">{{ insight.foot }}<small v-if="insight.sub">{{ insight.sub }}</small></span>
            </div>
          </div>
        </NCard>
      </div>

      <div class="dashboard-grid-two">
        <NCard :bordered="false" class="dashboard-panel">
          <template #header>
            <div class="dashboard-panel-heading"><div><h2><morph-icon icon="delivery" size="18" stroke-width="1.8" />时效概览</h2><span>各渠道履约中位数与高分位时效</span></div></div>
          </template>
          <div v-if="summary.timeliness.length" class="dashboard-timing-list">
            <div v-for="row in summary.timeliness" :key="row.channel" class="dashboard-timing-card">
              <div class="dashboard-timing-brand">
                <NTag round :bordered="false" :class="`dashboard-channel-tag dashboard-channel-tag--${channelClass(row.channel)}`">{{ row.channel }}</NTag>
                <span>出库样本 <b>{{ formatInteger(row.ship_samples) }}</b> 单 · 交付 <b>{{ formatInteger(row.delivery_samples) }}</b> 单</span>
              </div>
              <div class="dashboard-timing-metrics">
                <div><span>发货 P50</span><strong>{{ timingValue(row.p50_ship_hours, row.ship_sample_insufficient) }}</strong></div>
                <div><span>配送 P50</span><strong>{{ timingValue(row.p50_delivery_hours, row.delivery_sample_insufficient) }}</strong></div>
                <div><span>配送 P90</span><strong>{{ timingValue(row.p90_delivery_hours, row.delivery_sample_insufficient) }}</strong></div>
              </div>
            </div>
          </div>
          <NEmpty v-else description="暂无时效数据" class="dashboard-empty dashboard-empty--compact" />
          <div v-if="timelinessInsights.length" class="dashboard-insights">
            <div v-for="insight in timelinessInsights" :key="insight.label" class="dashboard-insight-card">
              <div class="dashboard-insight-head"><morph-icon :icon="insight.icon" size="14" stroke-width="1.8" /><span>{{ insight.label }}</span></div>
              <strong class="dashboard-insight-value">{{ insight.value }}<small v-if="insight.suffix">{{ insight.suffix }}</small><small v-if="insight.secondary">{{ insight.secondary }}</small></strong>
              <span class="dashboard-insight-foot" :class="insightClass(insight)">{{ insight.foot }}<small v-if="insight.sub">{{ insight.sub }}</small></span>
            </div>
          </div>
        </NCard>

        <NCard :bordered="false" class="dashboard-panel">
          <template #header>
            <div class="dashboard-panel-heading"><div><h2><morph-icon icon="flame" size="18" stroke-width="1.8" />热销商品 Top 5</h2><span>有效货件销量排行</span></div></div>
          </template>
          <div v-if="summary.top_products.length" class="dashboard-products">
            <div v-for="(product, index) in summary.top_products" :key="`${product.name}-${index}`" class="dashboard-product-row">
              <div class="dashboard-product-main">
                <span class="dashboard-rank" :class="`dashboard-rank--${index < 3 ? index + 1 : 'normal'}`">{{ index + 1 }}</span>
                <div class="dashboard-product-info"><strong :title="product.name">{{ product.name }}</strong><div class="dashboard-product-track"><span :style="{ width: `${productBarWidth(product)}%` }" /></div></div>
              </div>
              <div class="dashboard-product-stats"><span><b>{{ formatInteger(product.pieces) }}</b>件</span><span>{{ formatInteger(product.orders) }}单</span><span :class="{ 'is-danger': product.cancel_rate > 0.05 }">取消 {{ formatPercent(product.cancel_rate) }}</span></div>
            </div>
          </div>
          <NEmpty v-else description="所选范围暂无商品数据" class="dashboard-empty dashboard-empty--compact" />
          <div v-if="topProductsInsights.length" class="dashboard-insights">
            <div v-for="insight in topProductsInsights" :key="insight.label" class="dashboard-insight-card">
              <div class="dashboard-insight-head"><morph-icon :icon="insight.icon" size="14" stroke-width="1.8" /><span>{{ insight.label }}</span></div>
              <strong class="dashboard-insight-value">{{ insight.value }}<small v-if="insight.suffix">{{ insight.suffix }}</small><small v-if="insight.secondary">{{ insight.secondary }}</small></strong>
              <span class="dashboard-insight-foot" :class="insightClass(insight)">{{ insight.foot }}<small v-if="insight.sub">{{ insight.sub }}</small></span>
            </div>
          </div>
        </NCard>
      </div>
    </template>
  </section>
</template>
