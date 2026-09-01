<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch, type VNodeChild } from "vue";
import type { DataTableColumns } from "naive-ui";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDatePicker,
  NPagination,
  NSkeleton,
} from "naive-ui";
import { useRoute, useRouter } from "vue-router";
import EmptyState from "../../shared/components/EmptyState.vue";
import DatePresetPills from "../../shared/components/DatePresetPills.vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import { getErrorMessage } from "../../shared/api/client";
import { beijingToday, parseValidDateRange, shiftDays, type DateRange } from "../../shared/utils/date";
import { formatBeijingDateTime, formatInteger, formatMoney, formatNumber } from "../../shared/utils/format";
import { queryMatches, queryValue } from "../../shared/utils/query";
import { getSkuDetail, getSkuQueryDetails, getSkuTraffic, type SkuDetailQuery } from "./api";
import type {
  AnalyticsDataResponse,
  AnalyticsProductQueryDetailResponse,
  AnalyticsProductQueryDetailRow,
} from "../analytics/types";
import AfterSalesPanel from "./components/AfterSalesPanel.vue";
import AdvertisingPanel from "./components/AdvertisingPanel.vue";
import BusinessSignals from "./components/BusinessSignals.vue";
import InventoryPanel from "./components/InventoryPanel.vue";
import ProfitPanel from "./components/ProfitPanel.vue";
import SalesTrendChart from "./components/SalesTrendChart.vue";
import SkuHeader from "./components/SkuHeader.vue";
import SkuKpiCards from "./components/SkuKpiCards.vue";
import TrafficFunnel from "./components/TrafficFunnel.vue";
import type { SkuDetailResponse } from "./types";
import "./sku-detail.css";

type SkuDatePreset = "7" | "15" | "30";
type SkuRouteState = { shopId: 1 | 2; from: string; to: string };

const PAGE_SIZE = 20;
const datePresets: ReadonlyArray<{ key: SkuDatePreset; label: string }> = [
  { key: "7", label: "近 7 天" },
  { key: "15", label: "近 15 天" },
  { key: "30", label: "近 30 天" },
];

const route = useRoute();
const router = useRouter();
const core = ref<SkuDetailResponse | null>(null);
const coreLoading = ref(false);
const coreError = ref("");
const traffic = ref<AnalyticsDataResponse | null>(null);
const trafficLoading = ref(false);
const trafficError = ref("");
const queryDetails = ref<AnalyticsProductQueryDetailResponse | null>(null);
const queryLoading = ref(false);
const queryError = ref("");
const queryPage = ref(1);
let coreRequestId = 0;
let trafficRequestId = 0;
let queryRequestId = 0;
let routeReady = false;

function defaultDateRange(): DateRange {
  const to = shiftDays(beijingToday(), -1);
  return [shiftDays(to, -29), to];
}

function shopIdFromQuery(): 1 | 2 {
  const value = queryValue(route.query, "shop_id");
  if (value === "1") return 1;
  if (value === "2") return 2;
  return 1;
}

function skuFromRoute(): string {
  const value = route.params.sku;
  return typeof value === "string" ? value : "";
}

function routeState(): SkuRouteState {
  const [from, to] = parseValidDateRange(
    queryValue(route.query, "from"),
    queryValue(route.query, "to"),
    defaultDateRange(),
  );
  return { shopId: shopIdFromQuery(), from, to };
}

function queryFor(value: SkuRouteState): Record<string, string> {
  return { shop_id: String(value.shopId), from: value.from, to: value.to };
}

function requestFor(value: SkuRouteState): SkuDetailQuery {
  return { shopId: value.shopId, sku: skuFromRoute(), from: value.from, to: value.to };
}

const state = computed(routeState);
const dateRange = computed<DateRange>(() => [state.value.from, state.value.to]);
const activePreset = computed<SkuDatePreset | "">(() => {
  for (const key of ["7", "15", "30"] as const) {
    if (state.value.from === shiftDays(state.value.to, -Number(key) + 1)) return key;
  }
  return "";
});
const trafficRow = computed(() => traffic.value?.items[0] ?? null);
const queryPageCount = computed(() => Math.max(1, Math.ceil((queryDetails.value?.total ?? 0) / PAGE_SIZE)));

function money(value: number | null, currency: string | null): string {
  return value == null || !currency ? "—" : formatMoney(value, currency);
}

function percentage(value: number | null): string {
  return value == null ? "—" : `${formatNumber(value, 1)}%`;
}

function dateValue(value: string | null | undefined): string {
  return value ? formatBeijingDateTime(value) : "暂无";
}

const queryColumns: DataTableColumns<AnalyticsProductQueryDetailRow> = [
  { key: "query", title: "关键词", minWidth: 220, render: (row): VNodeChild => row.query || "—" },
  { key: "position", title: "位置", width: 90, align: "right", render: (row): VNodeChild => row.position == null ? "—" : formatInteger(row.position) },
  { key: "unique_search_users", title: "搜索用户", width: 110, align: "right", render: (row): VNodeChild => formatInteger(row.unique_search_users) },
  { key: "unique_view_users", title: "浏览用户", width: 110, align: "right", render: (row): VNodeChild => formatInteger(row.unique_view_users) },
  { key: "view_conversion", title: "浏览转化", width: 110, align: "right", render: (row): VNodeChild => percentage(row.view_conversion) },
  { key: "order_count", title: "订单数", width: 100, align: "right", render: (row): VNodeChild => formatInteger(row.order_count) },
  { key: "gmv", title: "GMV", width: 140, align: "right", render: (row): VNodeChild => money(row.gmv, row.currency) },
  { key: "currency", title: "币种", width: 80, render: (row): VNodeChild => row.currency || "—" },
];

function goBack(): void {
  if (window.history.length > 1) router.back();
  else void router.push({ name: "inventory" });
}

function updateRoute(next: Partial<SkuRouteState>): void {
  void router.push({ query: queryFor({ ...state.value, ...next }) });
}

function handleDateRangeChange(value: string | DateRange | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  const [from, to] = parseValidDateRange(value[0], value[1], dateRange.value);
  if (from !== value[0] || to !== value[1]) return;
  updateRoute({ from, to });
}

function selectPreset(preset: SkuDatePreset): void {
  const to = shiftDays(beijingToday(), -1);
  updateRoute({ from: shiftDays(to, -Number(preset) + 1), to });
}

async function loadCore(): Promise<void> {
  const requestId = ++coreRequestId;
  coreLoading.value = true;
  coreError.value = "";
  core.value = null;
  try {
    const result = await getSkuDetail(requestFor(state.value));
    if (requestId === coreRequestId) core.value = result;
  } catch (error) {
    if (requestId === coreRequestId) coreError.value = getErrorMessage(error);
  } finally {
    if (requestId === coreRequestId) coreLoading.value = false;
  }
}

async function loadTraffic(): Promise<void> {
  const requestId = ++trafficRequestId;
  trafficLoading.value = true;
  trafficError.value = "";
  traffic.value = null;
  try {
    const result = await getSkuTraffic(requestFor(state.value));
    if (requestId === trafficRequestId) traffic.value = result;
  } catch (error) {
    if (requestId === trafficRequestId) trafficError.value = getErrorMessage(error);
  } finally {
    if (requestId === trafficRequestId) trafficLoading.value = false;
  }
}

async function loadQueryDetails(page = 1): Promise<void> {
  const requestId = ++queryRequestId;
  queryPage.value = page;
  queryLoading.value = true;
  queryError.value = "";
  queryDetails.value = null;
  try {
    const result = await getSkuQueryDetails(requestFor(state.value), page, PAGE_SIZE);
    if (requestId === queryRequestId) queryDetails.value = result;
  } catch (error) {
    if (requestId === queryRequestId) queryError.value = getErrorMessage(error);
  } finally {
    if (requestId === queryRequestId) queryLoading.value = false;
  }
}

function loadAll(): void {
  queryPage.value = 1;
  void loadCore();
  void loadTraffic();
  void loadQueryDetails(1);
}

function retryCore(): void { void loadCore(); }
function retryTraffic(): void { void loadTraffic(); }
function retryQueries(): void { void loadQueryDetails(queryPage.value); }
function changeQueryPage(page: number): void {
  if (page !== queryPage.value) void loadQueryDetails(page);
}

watch(() => route.fullPath, () => {
  if (routeReady) loadAll();
});

onMounted(() => {
  routeReady = true;
  const current = routeState();
  if (!queryMatches(route.query, queryFor(current))) void router.replace({ query: queryFor(current) });
  else loadAll();
});

onBeforeUnmount(() => {
  coreRequestId += 1;
  trafficRequestId += 1;
  queryRequestId += 1;
});
</script>

<template>
  <section class="sku-detail-view">
    <div class="sku-detail-toolbar">
      <div class="sku-detail-date-control">
        <span>经营周期</span>
        <NDatePicker
          :formatted-value="dateRange"
          type="daterange"
          value-format="yyyy-MM-dd"
          separator="至"
          :clearable="false"
          class="sku-detail-date-picker"
          aria-label="SKU 经营详情日期范围"
          @update:formatted-value="handleDateRangeChange"
        />
        <DatePresetPills :options="datePresets" :active-key="activePreset" aria-label="SKU 详情日期快捷范围" @select="selectPreset" />
      </div>
      <span class="sku-detail-toolbar-through">Core 周期 {{ state.from }} 至 {{ state.to }}</span>
    </div>

    <div v-if="coreLoading" class="sku-detail-loading" aria-live="polite">
      <NCard v-for="i in 3" :key="i" :bordered="false" class="sku-detail-loading-card"><NSkeleton text :repeat="3" /><NSkeleton text width="68%" /></NCard>
    </div>
    <NAlert v-else-if="coreError" type="error" title="SKU 经营详情加载失败" class="sku-detail-error">
      <div class="sku-detail-error-content"><span>{{ coreError }}</span><NButton size="small" @click="retryCore">重试</NButton></div>
    </NAlert>

    <template v-else-if="core">
      <SkuHeader :identity="core.identity" :freshness="core.freshness" @back="goBack" />
      <SkuKpiCards :sales="core.sales" :inventory="core.inventory" :advertising="core.advertising" :after-sales="core.after_sales" :profit="core.profit" />
      <BusinessSignals :signals="core.signals" />

      <NCard :bordered="false" class="sku-detail-panel sku-detail-sales-panel">
        <template #header><div class="sku-detail-panel-heading"><div><h2><MorphIcon icon="trendingUp" size="18" stroke-width="1.8" />销售表现</h2><span>实际订单商品数量；发货前取消订单不计入有效销量，WHD 保留在经营详情展示</span></div><span class="sku-detail-panel-status">{{ core.period.from }} 至 {{ core.period.to }}</span></div></template>
        <div class="sku-detail-sales-summary">
          <span><small>周期销量</small><b>{{ formatInteger(core.sales.summary.units) }} 件</b></span>
          <span><small>有效订单</small><b>{{ formatInteger(core.sales.summary.orders) }} 单</b></span>
          <span><small>日均销量</small><b>{{ core.sales.summary.avg_units_per_day == null ? "—" : `${formatNumber(core.sales.summary.avg_units_per_day)} 件` }}</b></span>
          <span><small>周期销售额</small><b>{{ money(core.sales.summary.revenue, core.sales.summary.currency) }}</b></span>
          <span><small>7 / 15 / 30 日销量</small><b>{{ formatInteger(core.sales.summary.sales_7) }} / {{ formatInteger(core.sales.summary.sales_15) }} / {{ formatInteger(core.sales.summary.sales_30) }}</b></span>
        </div>
        <SalesTrendChart v-if="core.sales.status === 'available'" :data="core.sales.trend" />
        <EmptyState v-else title="当前周期暂无有效销售数据" icon="trendingUp" />
        <p v-if="!core.sales.summary.revenue_complete" class="sku-detail-data-note">部分订单商品价格或币种缺失，销售额暂不汇总。</p>
        <div class="sku-detail-channel-table-wrap">
          <table class="sku-detail-channel-table"><thead><tr><th>渠道</th><th>订单</th><th>销量</th><th>销售额</th><th>币种</th></tr></thead><tbody><tr v-for="channel in core.sales.channels" :key="channel.channel"><th>{{ channel.channel }}</th><td>{{ formatInteger(channel.orders) }}</td><td>{{ formatInteger(channel.units) }}</td><td>{{ money(channel.revenue, channel.currency) }}</td><td>{{ channel.currency || "—" }}</td></tr></tbody></table>
        </div>
      </NCard>

      <NCard :bordered="false" class="sku-detail-panel sku-detail-analytics-panel">
        <template #header><div class="sku-detail-panel-heading"><div><h2><MorphIcon icon="activity" size="18" stroke-width="1.8" />流量与转化</h2><span>独立请求 Analytics，时效和失败状态不影响 Core 数据</span></div><span class="sku-detail-panel-status">{{ traffic?.data_through ? `数据截止 ${dateValue(traffic.data_through)}` : "Analytics T-3" }}</span></div></template>
        <div v-if="trafficLoading" class="sku-detail-module-loading"><NSkeleton text :repeat="4" /></div>
        <NAlert v-else-if="trafficError" type="error" title="流量数据加载失败"><div class="sku-detail-error-content"><span>{{ trafficError }}</span><NButton size="small" @click="retryTraffic">重试</NButton></div></NAlert>
        <TrafficFunnel v-else-if="trafficRow" :data="trafficRow" />
        <EmptyState v-else title="当前周期暂无流量数据" icon="activity" />
      </NCard>

      <NCard :bordered="false" class="sku-detail-panel sku-detail-query-panel">
        <template #header><div class="sku-detail-panel-heading"><div><h2><MorphIcon icon="search" size="18" stroke-width="1.8" />搜索关键词</h2><span>复用 product query details；不进入 SKU Core API</span></div></div></template>
        <div v-if="queryLoading" class="sku-detail-module-loading"><NSkeleton text :repeat="5" /></div>
        <NAlert v-else-if="queryError" type="error" title="搜索关键词加载失败"><div class="sku-detail-error-content"><span>{{ queryError }}</span><NButton size="small" @click="retryQueries">重试</NButton></div></NAlert>
        <template v-else-if="queryDetails?.items.length">
          <NDataTable :columns="queryColumns" :data="queryDetails.items" :pagination="false" :remote="true" :scroll-x="1040" table-layout="fixed" class="sku-detail-query-table" />
          <div class="sku-detail-pager"><span>第 {{ queryPage }} / {{ queryPageCount }} 页，共 {{ formatInteger(queryDetails.total) }} 条关键词</span><NPagination :page="queryPage" :page-count="queryPageCount" :page-size="PAGE_SIZE" :disabled="queryLoading" @update:page="changeQueryPage" /></div>
        </template>
        <EmptyState v-else title="当前周期暂无关键词明细" icon="search" />
      </NCard>

      <AdvertisingPanel :data="core.advertising" />
      <InventoryPanel :data="core.inventory" />
      <ProfitPanel :data="core.profit" />
      <AfterSalesPanel :data="core.after_sales" />

      <div class="sku-detail-freshness-foot"><span>各源数据时效</span><span>订单 {{ dateValue(core.freshness.orders) }}</span><span>库存 {{ dateValue(core.freshness.inventory) }}</span><span>广告 {{ dateValue(core.freshness.advertising) }}</span><span>Finance {{ dateValue(core.freshness.finance) }}</span><span>ERP 成本 {{ dateValue(core.freshness.erp_cost) }}</span></div>
    </template>
  </section>
</template>
