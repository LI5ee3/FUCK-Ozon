<script setup lang="ts">
import "./advertising.css";
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import type { IconName } from "../../shared/icons/tabler";
import type { LocationQuery } from "vue-router";
import { useRoute, useRouter } from "vue-router";
import { NAlert, NButton, NCard, NDatePicker, NEmpty, NSpin, useMessage } from "naive-ui";
import { getAdsOverview } from "./api";
import { getErrorMessage } from "../../shared/api/client";
import AdsTrendChart from "./components/AdsTrendChart.vue";
import { useShop } from "../../shared/composables/useShop";
import type { AdsOverviewResponse, AdsSummary } from "./types";
import type { ShopSelection } from "../../shared/types/common";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../../shared/utils/format";
import { parseValidDateRange, standardDatePresetRange, type DateRange, type StandardDatePreset } from "../../shared/utils/date";
import { queryMatches, queryValue, shopSelectionFromQuery } from "../../shared/utils/query";

type DatePreset = StandardDatePreset;
type AdsFilters = { shopId: ShopSelection; from: string; to: string };
type AdsKpi = { icon: IconName; label: string; value: string; note?: string; tone: "azure" | "lavender" | "mint" | "peach" | "butter" };

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
    { icon: "wallet", label: "广告花费", value: formatAdsMoney(summary.spend_rub), tone: "peach" },
    { icon: "shoppingBag", label: "广告销售额", value: formatAdsMoney(summary.revenue_rub), tone: "azure" },
    { icon: "orders", label: "广告订单", value: formatInteger(summary.orders), tone: "mint" },
    { icon: "barChart", label: "曝光", value: formatInteger(summary.impressions), tone: "lavender" },
    { icon: "activity", label: "点击", value: formatInteger(summary.clicks), tone: "butter" },
    { icon: "percent", label: "CTR", value: formatAdsRate(summary.ctr), tone: "lavender" },
    { icon: "coins", label: "平均 CPC", value: formatAdsMoney(summary.avg_cpc_rub), tone: "mint" },
    { icon: "percent", label: "广告成本率（DRR）", value: formatAdsRate(summary.drr), note: "广告花费 ÷ 广告销售额", tone: "peach" },
    { icon: "trendingUp", label: "ROAS", value: formatAdsRatio(summary.roas), note: "广告销售额 ÷ 广告花费", tone: "azure" },
  ];
});

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
        <div class="ads-date-presets" aria-label="日期快捷范围">
          <NButton
            v-for="preset in datePresets"
            :key="preset.key"
            size="small"
            attr-type="button"
            :type="activePreset === preset.key ? 'primary' : 'default'"
            :secondary="activePreset !== preset.key"
            @click="selectPreset(preset.key)"
          >
            {{ preset.label }}
          </NButton>
        </div>
      </div>
      <div class="ads-toolbar-foot">
        <span>Performance API 自然日；金额单位 RUB</span>
        <span class="ads-data-through"><span class="ads-data-dot" aria-hidden="true" />数据截止 <strong>{{ dataThrough ? formatBeijingDateTime(dataThrough) : "暂无" }}</strong></span>
      </div>
    </div>

    <NAlert v-if="error" type="error" class="ads-error" :title="error">
      <div class="ads-error-content">
        <span>广告总览数据未更新，请重试。</span>
        <NButton size="small" @click="retry">重试</NButton>
      </div>
    </NAlert>

    <div v-if="kpis.length" class="ads-kpi-grid">
      <NCard
        v-for="kpi in kpis"
        :key="kpi.label"
        :bordered="false"
        class="ads-kpi-card"
        :class="kpi.tone"
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
            <span>Performance API 自然日；金额单位 RUB</span>
          </div>
          <span v-if="loading" class="ads-loading-label"><NSpin size="small" />正在加载…</span>
        </div>
      </template>
      <div v-if="loading && !overview" class="ads-loading"><NSpin size="medium" /><span>广告总览加载中…</span></div>
      <AdsTrendChart v-else-if="overview?.trend.length" :data="overview.trend" />
      <NEmpty v-else :description="error ? '广告总览加载失败' : '所选范围暂无广告日统计，请先同步。'" />
    </NCard>

    <p class="ads-data-note">页面只读取本地 SQLite；请在“数据同步中心”先同步广告日统计。</p>
  </section>
</template>
