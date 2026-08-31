<script setup lang="ts">
import DatePresetPills from "../../shared/components/DatePresetPills.vue";
import "./advertising.css";
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import type { IconName } from "../../shared/icons/tabler";
import type { LocationQuery } from "vue-router";
import { useRoute, useRouter } from "vue-router";
import { NAlert, NButton, NCard, NDatePicker, NSkeleton, NSpin, useMessage } from "naive-ui";
import EmptyState from "../../shared/components/EmptyState.vue";
import { getAdsOverview } from "./api";
import { getErrorMessage } from "../../shared/api/client";
import AdsTrendChart from "./components/AdsTrendChart.vue";
import { useShop } from "../../shared/composables/useShop";
import type { AdsOverviewResponse, AdsShopSummary, AdsSummary } from "./types";
import type { ShopSelection } from "../../shared/types/common";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../../shared/utils/format";
import { parseValidDateRange, standardDatePresetRange, type DateRange, type StandardDatePreset } from "../../shared/utils/date";
import { queryMatches, queryValue, shopSelectionFromQuery } from "../../shared/utils/query";

type DatePreset = StandardDatePreset;
type AdsFilters = { shopId: ShopSelection; from: string; to: string };
type AdsKpi = { icon: IconName; label: string; value: string; note?: string; tone: "azure" | "lavender" | "mint" | "peach" | "butter" };
type AdsInsight = { icon: IconName; label: string; value: string; foot: string };

const route = useRoute();
const router = useRouter();
const message = useMessage();
const { selectedShopId, selectShop } = useShop();
const datePresets: ReadonlyArray<{ key: DatePreset; label: string }> = [
  { key: "today", label: "今天" },
  { key: "3days", label: "3天内" },
  { key: "7days", label: "7天内" },
  { key: "3months", label: "近三个月" },
  { key: "all", label: "全部时间" },
];
const initialFilters = parseFilters(route.query, selectedShopId.value);
const filters = reactive<AdsFilters>(initialFilters);
const overview = ref<AdsOverviewResponse | null>(null);
const loading = ref(false);
const error = ref("");
let requestId = 0;
let routeReady = false;
let ignoreNextShopChange = false;

const dateRange = computed<DateRange>(() => [filters.from, filters.to]);
const activePreset = computed<DatePreset | "">(() => {
  for (const preset of datePresets) {
    const [from, to] = standardDatePresetRange(preset.key);
    if (filters.from === from && filters.to === to) return preset.key;
  }
  return "";
});
const dataThrough = computed(() => overview.value?.data_through ?? null);
const kpis = computed<AdsKpi[]>(() => {
  const data = overview.value;
  if (!data) return [];
  const summary: AdsSummary = data.summary ?? data;
  return [
    { icon: "wallet", label: "广告花费", value: formatAdsMoney(summary.spend_rub), note: "统计期投放支出", tone: "butter" },
    { icon: "shoppingBag", label: "广告销售额", value: formatAdsMoney(summary.revenue_rub), note: "广告归因成交额", tone: "azure" },
    { icon: "orders", label: "广告订单", value: formatInteger(summary.orders), note: "广告归因订单数", tone: "mint" },
    { icon: "percent", label: "广告成本率（DRR）", value: formatAdsRate(summary.drr), note: "广告花费 ÷ 广告销售额", tone: "peach" },
    { icon: "trendingUp", label: "ROAS", value: formatAdsRatio(summary.roas), note: "广告销售额 ÷ 广告花费", tone: "lavender" },
  ];
});
const adsInsights = computed<AdsInsight[]>(() => {
  const data = overview.value;
  if (!data) return [];
  const summary: AdsSummary = data.summary ?? data;
  return [
    { icon: "barChart", label: "曝光", value: formatInteger(summary.impressions), foot: "统计期合计" },
    { icon: "activity", label: "点击", value: formatInteger(summary.clicks), foot: "统计期合计" },
    { icon: "percent", label: "点击率（CTR）", value: formatAdsRate(summary.ctr), foot: "点击 ÷ 曝光" },
    { icon: "package", label: "加购量", value: formatInteger(summary.cart_adds), foot: "统计期合计" },
    { icon: "coins", label: "平均 CPC", value: formatAdsMoney(summary.avg_cpc_rub), foot: "广告花费 ÷ 点击" },
  ];
});
const shopRows = computed(() => {
  const shops = overview.value?.shops ?? [];
  return [...shops].sort((left, right) => right.spend_rub - left.spend_rub);
});

function shopSpendShare(shop: AdsShopSummary): number {
  const total = overview.value?.summary?.spend_rub ?? 0;
  return total > 0 ? Math.max(0, Math.min(100, Math.round((shop.spend_rub / total) * 100))) : 0;
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): AdsFilters {
  const [from, to] = parseValidDateRange(queryValue(query, "from"), queryValue(query, "to"), standardDatePresetRange("7days"));
  return { shopId: shopSelectionFromQuery(query, fallbackShop), from, to };
}

function queryFor(value: AdsFilters): Record<string, string> {
  return { shop_id: String(value.shopId), from: value.from, to: value.to };
}

function applyRouteQuery(query: LocationQuery, fallbackShop: ShopSelection): AdsFilters {
  const next = parseFilters(query, fallbackShop);
  Object.assign(filters, next);
  if (selectedShopId.value !== next.shopId) {
    ignoreNextShopChange = true;
    selectShop(next.shopId);
  }
  return next;
}

function currentFilters(): AdsFilters {
  return { ...filters };
}

function loadOverview(queryFilters: AdsFilters): void {
  const currentRequest = ++requestId;
  loading.value = true;
  error.value = "";
  overview.value = null;
  void getAdsOverview(queryFilters.shopId, queryFilters.from, queryFilters.to)
    .then((data) => {
      if (currentRequest === requestId) overview.value = data;
    })
    .catch((cause: unknown) => {
      if (currentRequest !== requestId) return;
      error.value = getErrorMessage(cause);
      message.error(error.value);
    })
    .finally(() => {
      if (currentRequest === requestId) loading.value = false;
    });
}

function updateRoute(next: AdsFilters, replace = false): void {
  Object.assign(filters, next);
  if (queryMatches(route.query, queryFor(next))) {
    loadOverview(next);
    return;
  }
  const navigation = replace ? router.replace({ query: queryFor(next) }) : router.push({ query: queryFor(next) });
  void navigation;
}

function handleDateRangeChange(value: string | DateRange | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  const [from, to] = parseValidDateRange(value[0], value[1], standardDatePresetRange("7days"));
  if (from !== value[0] || to !== value[1]) return;
  updateRoute({ ...currentFilters(), from, to });
}

function selectPreset(preset: DatePreset): void {
  const [from, to] = standardDatePresetRange(preset);
  updateRoute({ ...currentFilters(), from, to });
}

function retry(): void {
  loadOverview(currentFilters());
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value);
}

function formatAdsMoney(value: number | null | undefined): string {
  return isFiniteNumber(value) ? `${formatNumber(value)} RUB` : "—";
}

function formatAdsRate(value: number | null | undefined): string {
  return isFiniteNumber(value) ? `${value.toFixed(2)}%` : "—";
}

function formatAdsRatio(value: number | null | undefined): string {
  return isFiniteNumber(value) ? value.toFixed(2) : "—";
}

watch(() => route.fullPath, () => {
  if (!routeReady) return;
  const next = applyRouteQuery(route.query, selectedShopId.value);
  loadOverview(next);
});

watch(selectedShopId, (shopId) => {
  if (ignoreNextShopChange) {
    ignoreNextShopChange = false;
    return;
  }
  if (!routeReady || filters.shopId === shopId) return;
  updateRoute({ ...currentFilters(), shopId });
});

onMounted(() => {
  const next = applyRouteQuery(route.query, selectedShopId.value);
  routeReady = true;
  if (!queryMatches(route.query, queryFor(next))) {
    void router.replace({ query: queryFor(next) });
  } else {
    loadOverview(next);
  }
});

onBeforeUnmount(() => {
  requestId += 1;
});
</script>

<template>
  <section class="ads-view">
    <div class="ads-toolbar">
      <div class="ads-date-control">
        <span>统计日期</span>
        <NDatePicker
          :formatted-value="dateRange"
          type="daterange"
          value-format="yyyy-MM-dd"
          separator="至"
          :clearable="false"
          class="ads-date-picker"
          aria-label="广告总览日期范围"
          @update:formatted-value="handleDateRangeChange"
        />
        <DatePresetPills class="ads-date-presets" aria-label="日期快捷范围" :options="datePresets" :active-key="activePreset" @select="selectPreset" />
      </div>
      <div class="ads-toolbar-foot">
        <span>Performance API 自然日；金额单位 RUB</span>
        <span class="ads-data-through"><span class="ads-data-dot" aria-hidden="true" />数据截止 <strong>{{ dataThrough ? formatBeijingDateTime(dataThrough) : "暂无" }}</strong></span>
      </div>
    </div>

    <NAlert v-if="error" type="error" title="广告总览加载失败" class="ads-error" role="alert">
      <div class="ads-error-content">
        <span>{{ error }}</span>
        <NButton text type="error" @click="retry">重试</NButton>
      </div>
    </NAlert>

    <div v-if="loading && !overview" class="ads-kpi-grid" aria-live="polite">
      <NCard v-for="i in 5" :key="i" :bordered="false" class="ads-kpi-card">
        <NSkeleton text width="55%" />
        <NSkeleton text width="72%" class="kpi-skeleton-value" />
        <NSkeleton text width="42%" />
      </NCard>
    </div>

    <div v-else-if="kpis.length" class="ads-kpi-grid">
      <NCard
        v-for="kpi in kpis"
        :key="kpi.label"
        :bordered="false"
        class="ads-kpi-card"
        :class="`tone-${kpi.tone}`"
      >
        <div class="ads-kpi-head">
          <span>{{ kpi.label }}</span>
          <span class="ads-icon-badge tone-badge"><morph-icon :icon="kpi.icon" size="18" stroke-width="1.8" /></span>
        </div>
        <strong class="ads-kpi-value tone-value">{{ kpi.value }}</strong>
        <small v-if="kpi.note">{{ kpi.note }}</small>
      </NCard>
    </div>

    <NCard :bordered="false" class="ads-trend-card">
      <template #header>
        <div class="ads-panel-heading">
          <div>
            <h2><morph-icon icon="trendingUp" size="18" stroke-width="1.8" />广告趋势</h2>
            <span>各自然日广告花费与销售额对比</span>
          </div>
          <span v-if="loading" class="ads-loading-label"><NSpin size="small" />正在加载…</span>
        </div>
      </template>
      <div v-if="loading && !overview" class="ads-loading"><NSpin size="medium" /><span>广告总览加载中…</span></div>
      <template v-else-if="overview?.trend.length">
        <AdsTrendChart :data="overview.trend" />
        <div class="ads-insights">
          <div v-for="insight in adsInsights" :key="insight.label" class="ads-insight-card">
            <div class="ads-insight-head"><morph-icon :icon="insight.icon" size="14" stroke-width="1.8" /><span>{{ insight.label }}</span></div>
            <strong class="ads-insight-value">{{ insight.value }}</strong>
            <span class="ads-insight-foot">{{ insight.foot }}</span>
          </div>
        </div>
      </template>
      <EmptyState v-else :title="error ? '广告总览加载失败' : '所选范围暂无广告日统计，请先同步。'" icon="barChart" />
    </NCard>

    <NCard v-if="shopRows.length > 1" :bordered="false" class="ads-trend-card">
      <template #header>
        <div class="ads-panel-heading">
          <div>
            <h2><morph-icon icon="store" size="18" stroke-width="1.8" />分店铺表现</h2>
            <span>所选范围内各店铺的广告花费与产出；按花费排序</span>
          </div>
        </div>
      </template>
      <div class="ads-shops-grid">
        <div v-for="shop in shopRows" :key="shop.shop_id" class="ads-shop-card">
          <div class="ads-shop-brand">
            <strong :title="shop.shop_name">{{ shop.shop_name }}</strong>
            <span>花费占比 <b>{{ shopSpendShare(shop) }}%</b></span>
          </div>
          <div class="ads-shop-track"><span :style="{ width: `${shopSpendShare(shop)}%` }" /></div>
          <div class="ads-shop-metrics">
            <div><span>花费</span><strong>{{ formatAdsMoney(shop.spend_rub) }}</strong></div>
            <div><span>销售额</span><strong>{{ formatAdsMoney(shop.revenue_rub) }}</strong></div>
            <div><span>订单</span><strong>{{ formatInteger(shop.orders) }}</strong></div>
            <div><span>ROAS</span><strong>{{ formatAdsRatio(shop.roas) }}</strong></div>
          </div>
        </div>
      </div>
    </NCard>

    <p class="ads-data-note">页面只读取本地 SQLite；请在“数据同步中心”先同步广告日统计。</p>
  </section>
</template>
