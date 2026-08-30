<script setup lang="ts">
import "../../styles/analytics.css";
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch, type VNodeChild } from "vue";
import AnalyticsKpiCards from "./components/AnalyticsKpiCards.vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import type { IconName } from "../../shared/icons/tabler";
import type { LocationQuery } from "vue-router";
import { useRoute, useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDatePicker,
  NInput,
  NPagination,
  useMessage,
} from "naive-ui";
import EmptyState from "../../shared/components/EmptyState.vue";
import type { DataTableColumns } from "naive-ui";
import { getErrorMessage } from "../../shared/api/client";
import { getAnalyticsData, getProductQueries, getProductQueryDetails } from "./api";
import { useShop } from "../../shared/composables/useShop";
import type {
  AnalyticsDataResponse,
  AnalyticsPagedResponse,
  AnalyticsProductQueryDetailResponse,
  AnalyticsProductQueryDetailRow,
  AnalyticsProductQueryResponse,
  AnalyticsProductQueryRow,
  AnalyticsTrafficRow,
  AnalyticsTrafficShopSummary,
} from "./types";
import type { ShopSelection } from "../../shared/types/common";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../../shared/utils/format";
import { beijingToday, parseValidDateRange, shiftDays, standardDatePresetRange, type DateRange, type StandardDatePreset } from "../../shared/utils/date";
import { positiveInteger, queryMatches, queryValue, shopSelectionFromQuery } from "../../shared/utils/query";

type DatePreset = StandardDatePreset;
type AnalyticsTab = "traffic" | "queries";
type AnalyticsFilters = {
  shopId: ShopSelection;
  sku: string;
  from: string;
  to: string;
  page: number;
  tab: AnalyticsTab;
};
type TrafficMetric = Exclude<keyof AnalyticsTrafficShopSummary, "shop_id" | "shop_name" | "currency">;
type AnalyticsKpi = {
  icon: IconName;
  label: string;
  value?: string;
  lines?: string[];
  note?: string;
  tone: "azure" | "lavender" | "mint" | "peach" | "butter";
};
type AnalyticsIdentity = Pick<AnalyticsTrafficRow, "shop_name" | "sku">;

const PAGE_SIZE = 50;
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
const filters = reactive<AnalyticsFilters>(initialFilters);
const tabPages = reactive<Record<AnalyticsTab, number>>({ traffic: 1, queries: 1 });
tabPages[initialFilters.tab] = initialFilters.page;
const skuDraft = ref(initialFilters.sku);
const traffic = ref<AnalyticsDataResponse | null>(null);
const productQueries = ref<AnalyticsProductQueryResponse | null>(null);
const details = ref<AnalyticsProductQueryDetailResponse | null>(null);
const selectedDetail = ref<AnalyticsProductQueryRow | null>(null);
const detailPage = ref(1);
const trafficLoading = ref(false);
const productQueriesLoading = ref(false);
const detailLoading = ref(false);
const trafficError = ref("");
const productQueriesError = ref("");
const detailError = ref("");
let requestId = 0;
let detailRequestId = 0;
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
const trafficPageCount = computed(() => pageCountFor(traffic.value));
const productQueryPageCount = computed(() => pageCountFor(productQueries.value));
const detailPageCount = computed(() => pageCountFor(details.value));
const activeError = computed(() => filters.tab === "traffic" ? trafficError.value : productQueriesError.value);
const activeLoading = computed(() => filters.tab === "traffic" ? trafficLoading.value : productQueriesLoading.value);
const currentDataThrough = computed(() => filters.tab === "traffic"
  ? traffic.value?.data_through ?? null
  : productQueries.value?.data_through ?? null);
const trafficKpis = computed<AnalyticsKpi[]>(() => {
  const data = traffic.value;
  if (!data) return [];
  const total = (metric: TrafficMetric): number => data.shops.reduce((sum, row) => sum + Number(row[metric] ?? 0), 0);
  const impressions = total("impressions");
  const productViews = total("product_views");
  const cartAdds = total("cart_adds");
  const orderedUnits = total("ordered_units");
  return [
    { icon: "search", label: "曝光量", value: formatInteger(impressions), tone: "azure" },
    { icon: "package", label: "商品详情浏览量", value: formatInteger(productViews), tone: "lavender" },
    { icon: "activity", label: "独立访客", value: formatInteger(total("unique_visitors")), tone: "mint" },
    { icon: "shoppingBag", label: "加购量", value: formatInteger(cartAdds), tone: "butter" },
    { icon: "orders", label: "下单件数", value: formatInteger(orderedUnits), tone: "mint" },
    {
      icon: "wallet",
      label: "成交金额",
      lines: data.shops.length
        ? data.shops.map((row) => `${row.shop_name}：${formatAnalyticsMoney(row.revenue, row.currency)}`)
        : ["—"],
      note: "按店铺／币种分开展示",
      tone: "azure",
    },
    { icon: "trendingUp", label: "曝光→浏览", value: formatFunnelRate(productViews, impressions), tone: "lavender" },
    {
      icon: "percent",
      label: "浏览→加购 ／ 加购→下单",
      value: `${formatFunnelRate(cartAdds, productViews)} ／ ${formatFunnelRate(orderedUnits, cartAdds)}`,
      tone: "mint",
    },
  ];
});

function analyticsDefaultRange(): DateRange {
  const end = shiftDays(beijingToday(), -3);
  return [shiftDays(end, -29), end];
}

function isAnalyticsTab(value: string): value is AnalyticsTab {
  return value === "traffic" || value === "queries";
}

function parseDateRange(from: string, to: string): DateRange {
  return parseValidDateRange(from, to, analyticsDefaultRange());
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): AnalyticsFilters {
  const tab = queryValue(query, "tab");
  const [from, to] = parseDateRange(queryValue(query, "from"), queryValue(query, "to"));
  return {
    shopId: shopSelectionFromQuery(query, fallbackShop),
    sku: queryValue(query, "sku").trim(),
    from,
    to,
    page: positiveInteger(queryValue(query, "page"), 1),
    tab: isAnalyticsTab(tab) ? tab : "traffic",
  };
}

function queryFor(value: AnalyticsFilters): Record<string, string> {
  const defaultRange = analyticsDefaultRange();
  const query: Record<string, string> = { shop_id: String(value.shopId) };
  const sku = value.sku.trim();
  if (value.tab === "queries") query.tab = value.tab;
  if (sku) query.sku = sku;
  if (value.page !== 1) query.page = String(value.page);
  if (value.from !== defaultRange[0] || value.to !== defaultRange[1]) {
    query.from = value.from;
    query.to = value.to;
  }
  return query;
}

function applyRouteQuery(query: LocationQuery, fallbackShop: ShopSelection): AnalyticsFilters {
  const next = parseFilters(query, fallbackShop);
  Object.assign(filters, next);
  tabPages[next.tab] = next.page;
  skuDraft.value = next.sku;
  if (selectedShopId.value !== next.shopId) {
    ignoreNextShopChange = true;
    selectShop(next.shopId);
  }
  return next;
}

function updateRoute(next: AnalyticsFilters, replace = false): void {
  const normalized = { ...next, sku: next.sku.trim() };
  Object.assign(filters, normalized);
  skuDraft.value = normalized.sku;
  if (queryMatches(route.query, queryFor(normalized))) {
    void loadActiveTab(normalized);
    return;
  }
  const navigation = replace
    ? router.replace({ query: queryFor(normalized) })
    : router.push({ query: queryFor(normalized) });
  void navigation;
}

function currentFilters(): AnalyticsFilters {
  const next = { ...filters, sku: skuDraft.value };
  if (!queryValue(route.query, "from") && !queryValue(route.query, "to")) {
    [next.from, next.to] = analyticsDefaultRange();
  }
  return next;
}

function updateFilters(overrides: Partial<AnalyticsFilters>, replace = false): void {
  updateRoute({ ...currentFilters(), ...overrides }, replace);
}

function clearDetails(): void {
  detailRequestId += 1;
  selectedDetail.value = null;
  details.value = null;
  detailError.value = "";
  detailLoading.value = false;
  detailPage.value = 1;
}

function resetTablePages(): void {
  tabPages.traffic = 1;
  tabPages.queries = 1;
}

function pageCountFor<T>(data: AnalyticsPagedResponse<T> | null): number {
  return Math.max(1, Math.ceil((data?.total ?? 0) / (data?.size || PAGE_SIZE)));
}

async function loadTraffic(queryFilters: AnalyticsFilters): Promise<void> {
  const currentRequest = ++requestId;
  clearDetails();
  trafficLoading.value = true;
  trafficError.value = "";
  traffic.value = null;
  try {
    const data = await getAnalyticsData({
      shopId: queryFilters.shopId,
      sku: queryFilters.sku || undefined,
      page: queryFilters.page,
      size: PAGE_SIZE,
      from: queryFilters.from,
      to: queryFilters.to,
    });
    if (currentRequest !== requestId) return;
    const pages = pageCountFor(data);
    if (queryFilters.page > pages) {
      await router.replace({ query: queryFor({ ...queryFilters, page: pages }) });
      return;
    }
    traffic.value = data;
  } catch (cause) {
    if (currentRequest !== requestId) return;
    trafficError.value = getErrorMessage(cause);
    message.error(trafficError.value);
  } finally {
    if (currentRequest === requestId) trafficLoading.value = false;
  }
}

async function loadProductQueryRows(queryFilters: AnalyticsFilters): Promise<void> {
  const currentRequest = ++requestId;
  clearDetails();
  productQueriesLoading.value = true;
  productQueriesError.value = "";
  productQueries.value = null;
  try {
    const data = await getProductQueries({
      shopId: queryFilters.shopId,
      sku: queryFilters.sku || undefined,
      page: queryFilters.page,
      size: PAGE_SIZE,
      from: queryFilters.from,
      to: queryFilters.to,
    });
    if (currentRequest !== requestId) return;
    const pages = pageCountFor(data);
    if (queryFilters.page > pages) {
      await router.replace({ query: queryFor({ ...queryFilters, page: pages }) });
      return;
    }
    productQueries.value = data;
  } catch (cause) {
    if (currentRequest !== requestId) return;
    productQueriesError.value = getErrorMessage(cause);
    message.error(productQueriesError.value);
  } finally {
    if (currentRequest === requestId) productQueriesLoading.value = false;
  }
}

function loadActiveTab(queryFilters: AnalyticsFilters): Promise<void> {
  return queryFilters.tab === "traffic" ? loadTraffic(queryFilters) : loadProductQueryRows(queryFilters);
}

async function loadDetails(row: AnalyticsProductQueryRow, page = 1): Promise<void> {
  const currentRequest = ++detailRequestId;
  selectedDetail.value = row;
  details.value = null;
  detailError.value = "";
  detailPage.value = page;
  detailLoading.value = true;
  try {
    const data = await getProductQueryDetails({
      shopId: row.shop_id,
      sku: row.sku,
      page,
      size: PAGE_SIZE,
      from: filters.from,
      to: filters.to,
    });
    if (currentRequest !== detailRequestId) return;
    const pages = pageCountFor(data);
    if (page > pages) {
      void loadDetails(row, pages);
      return;
    }
    details.value = data;
  } catch (cause) {
    if (currentRequest !== detailRequestId) return;
    detailError.value = getErrorMessage(cause);
    message.error(detailError.value);
  } finally {
    if (currentRequest === detailRequestId) detailLoading.value = false;
  }
}

function retry(): void {
  const next = currentFilters();
  Object.assign(filters, next);
  void loadActiveTab(next);
}

function retryDetails(): void {
  if (selectedDetail.value) void loadDetails(selectedDetail.value, detailPage.value);
}

function submitFilters(): void {
  resetTablePages();
  updateFilters({ sku: skuDraft.value, page: 1 });
}

function resetFilters(): void {
  skuDraft.value = "";
  resetTablePages();
  updateFilters({ sku: "", page: 1 });
}

function changeTab(tab: AnalyticsTab): void {
  if (filters.tab !== tab) updateFilters({ tab, page: tabPages[tab] });
}

function handleDateRangeChange(value: string | DateRange | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  const [from, to] = parseDateRange(value[0], value[1]);
  if (from !== value[0] || to !== value[1]) return;
  resetTablePages();
  updateFilters({ from, to, page: 1 });
}

function selectPreset(preset: DatePreset): void {
  const [from, to] = standardDatePresetRange(preset);
  resetTablePages();
  updateFilters({ from, to, page: 1 });
}

function changePage(page: number): void {
  if (page === filters.page) return;
  tabPages[filters.tab] = page;
  updateFilters({ page });
}

function changeDetailPage(page: number): void {
  if (selectedDetail.value && page !== detailPage.value) void loadDetails(selectedDetail.value, page);
}

function formatFunnelRate(numerator: number, denominator: number): string {
  return denominator ? `${((numerator / denominator) * 100).toFixed(2)}%` : "—";
}

function formatApiRate(value: number | null): string {
  return value == null ? "—" : `${formatNumber(value)}%`;
}

function formatAnalyticsMoney(value: number | null | undefined, currency: string): string {
  return value == null ? "—" : `${formatNumber(value)}${currency ? ` ${currency}` : ""}`;
}

function renderShopSku(row: AnalyticsIdentity): VNodeChild {
  return h("div", { class: "analytics-identity-cell" }, [
    h("span", { class: "analytics-shop-badge" }, row.shop_name),
    h("strong", { class: "analytics-sku" }, row.sku || "—"),
  ]);
}

function renderTrafficProduct(row: AnalyticsTrafficRow): VNodeChild {
  return h("span", { class: "analytics-product-name", title: row.name || "—" }, row.name || "—");
}

function renderProductQueryProduct(row: AnalyticsProductQueryRow): VNodeChild {
  return h("div", { class: "analytics-product-cell" }, [
    h("strong", { class: "analytics-product-name", title: row.name || "—" }, row.name || "—"),
    h("small", { class: "analytics-offer" }, row.offer_id || "—"),
  ]);
}

function renderNumber(value: number | null | undefined, nullable = false): VNodeChild {
  return h("span", { class: "analytics-number" }, nullable && value == null ? "—" : formatInteger(value));
}

function renderAnalyticsMoney(value: number | null | undefined, currency: string): VNodeChild {
  return h("span", { class: "analytics-number" }, formatAnalyticsMoney(value, currency));
}

function renderRate(value: string): VNodeChild {
  return h("span", { class: "analytics-number" }, value);
}

// Fixed-layout width system (DESIGN.md §3): every column carries an explicit
// width and the sum equals the table's scroll-x, so long product names clip
// with ellipsis instead of pushing numeric columns out of the viewport.
const trafficColumns: DataTableColumns<AnalyticsTrafficRow> = [
  { key: "identity", title: "店铺／SKU", width: 160, render: renderShopSku },
  { key: "name", title: "商品", width: 260, render: renderTrafficProduct },
  { key: "impressions", title: "曝光量", width: 100, align: "right", render: (row) => renderNumber(row.impressions) },
  { key: "product_views", title: "详情浏览", width: 100, align: "right", render: (row) => renderNumber(row.product_views) },
  { key: "unique_visitors", title: "独立访客", width: 100, align: "right", render: (row) => renderNumber(row.unique_visitors) },
  { key: "cart_adds", title: "加购量", width: 90, align: "right", render: (row) => renderNumber(row.cart_adds) },
  { key: "ordered_units", title: "下单件数", width: 100, align: "right", render: (row) => renderNumber(row.ordered_units) },
  { key: "revenue", title: "成交金额", width: 150, align: "right", render: (row) => renderAnalyticsMoney(row.revenue, row.currency) },
  { key: "view_rate", title: "曝光→浏览", width: 100, align: "right", render: (row) => renderRate(formatFunnelRate(row.product_views, row.impressions)) },
  { key: "cart_rate", title: "浏览→加购", width: 100, align: "right", render: (row) => renderRate(formatFunnelRate(row.cart_adds, row.product_views)) },
  { key: "order_rate", title: "加购→下单", width: 100, align: "right", render: (row) => renderRate(formatFunnelRate(row.ordered_units, row.cart_adds)) },
];

const productQueryColumns: DataTableColumns<AnalyticsProductQueryRow> = [
  { key: "identity", title: "店铺／SKU", width: 160, render: renderShopSku },
  { key: "product", title: "商品／货号", width: 300, render: renderProductQueryProduct },
  { key: "position", title: "平均排名", width: 100, align: "right", render: (row) => renderNumber(row.position, true) },
  { key: "unique_search_users", title: "独立搜索人数", width: 120, align: "right", render: (row) => renderNumber(row.unique_search_users) },
  { key: "unique_view_users", title: "独立访问人数", width: 120, align: "right", render: (row) => renderNumber(row.unique_view_users) },
  { key: "view_conversion", title: "点击转化率", width: 110, align: "right", render: (row) => renderRate(formatApiRate(row.view_conversion)) },
  { key: "gmv", title: "GMV", width: 120, align: "right", render: (row) => renderAnalyticsMoney(row.gmv, row.currency) },
  {
    key: "details",
    title: "",
    width: 110,
    align: "right",
    render: (row) => h(NButton, {
      size: "small",
      text: true,
      type: "primary",
      onClick: () => { void loadDetails(row); },
    }, { default: () => "查看关键词" }),
  },
];

const detailColumns: DataTableColumns<AnalyticsProductQueryDetailRow> = [
  { key: "query", title: "搜索关键词", width: 280, render: (row) => h("span", { class: "analytics-product-name", title: row.query || "—" }, row.query || "—") },
  { key: "position", title: "平均自然排名", width: 120, align: "right", render: (row) => renderNumber(row.position, true) },
  { key: "unique_search_users", title: "独立搜索人数", width: 120, align: "right", render: (row) => renderNumber(row.unique_search_users) },
  { key: "unique_view_users", title: "独立访问人数", width: 120, align: "right", render: (row) => renderNumber(row.unique_view_users) },
  { key: "view_conversion", title: "点击转化率", width: 110, align: "right", render: (row) => renderRate(formatApiRate(row.view_conversion)) },
  { key: "order_count", title: "订单量", width: 90, align: "right", render: (row) => renderNumber(row.order_count) },
  { key: "gmv", title: "GMV／币种", width: 140, align: "right", render: (row) => renderAnalyticsMoney(row.gmv, row.currency) },
];

watch(() => route.fullPath, () => {
  if (!routeReady) return;
  const next = applyRouteQuery(route.query, 0);
  void loadActiveTab(next);
});

watch(selectedShopId, (shopId) => {
  if (ignoreNextShopChange) {
    ignoreNextShopChange = false;
    return;
  }
  if (!routeReady || filters.shopId === shopId) return;
  updateFilters({ shopId });
});

onMounted(() => {
  const next = applyRouteQuery(route.query, selectedShopId.value);
  routeReady = true;
  if (!queryMatches(route.query, queryFor(next))) {
    void router.replace({ query: queryFor(next) });
  } else {
    void loadActiveTab(next);
  }
});

onBeforeUnmount(() => {
  requestId += 1;
  detailRequestId += 1;
});
</script>

<template>
  <section class="analytics-view">
    <div class="analytics-tabs" role="tablist" aria-label="流量与搜索分析">
      <NButton
        size="small"
        attr-type="button"
        role="tab"
        :aria-selected="filters.tab === 'traffic'"
        :type="filters.tab === 'traffic' ? 'primary' : 'default'"
        :secondary="filters.tab !== 'traffic'"
        @click="changeTab('traffic')"
      >
        <template #icon><morph-icon icon="trendingUp" size="14" stroke-width="2" /></template>
        流量转化
      </NButton>
      <NButton
        size="small"
        attr-type="button"
        role="tab"
        :aria-selected="filters.tab === 'queries'"
        :type="filters.tab === 'queries' ? 'primary' : 'default'"
        :secondary="filters.tab !== 'queries'"
        @click="changeTab('queries')"
      >
        <template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>
        搜索关键词
      </NButton>
    </div>

    <form class="analytics-toolbar" @submit.prevent="submitFilters">
      <div class="analytics-filter-row">
        <NInput
          v-model:value="skuDraft"
          type="text"
          inputmode="numeric"
          class="analytics-sku-search"
          aria-label="筛选 SKU"
          placeholder="输入 SKU（可选）…"
          @keydown.enter.prevent="submitFilters"
        >
          <template #prefix><morph-icon icon="search" size="15" stroke-width="1.8" /></template>
        </NInput>
        <div class="analytics-date-control">
          <span>统计日期</span>
          <NDatePicker
            :formatted-value="dateRange"
            type="daterange"
            value-format="yyyy-MM-dd"
            separator="至"
            :clearable="false"
            class="analytics-date-picker"
            aria-label="流量与搜索分析日期范围"
            @update:formatted-value="handleDateRangeChange"
          />
          <div class="analytics-date-presets" aria-label="日期快捷范围">
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
        <div class="analytics-filter-actions">
          <NButton type="primary" attr-type="submit" :loading="activeLoading">
            <template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>
            查询
          </NButton>
          <NButton attr-type="button" @click="resetFilters">清除</NButton>
        </div>
      </div>
      <div class="analytics-toolbar-foot">
        <span>搜索分析最近 3 天由 Ozon 计算中，默认展示截至 3 天前的最近 30 天</span>
        <span class="analytics-data-through"><span class="analytics-data-dot" aria-hidden="true" />数据截止 <strong>{{ currentDataThrough ? formatBeijingDateTime(currentDataThrough) : "暂无" }}</strong></span>
      </div>
    </form>

    <NAlert v-if="activeError" type="error" class="analytics-error" :title="activeError">
      <div class="analytics-error-content">
        <span>{{ filters.tab === 'traffic' ? '流量转化数据未更新，请重试。' : '商品搜索表现未更新，请重试。' }}</span>
        <NButton size="small" @click="retry">重试</NButton>
      </div>
    </NAlert>

    <template v-if="filters.tab === 'traffic'">
      <AnalyticsKpiCards :items="trafficKpis" :loading="trafficLoading" />

      <NCard :bordered="false" class="analytics-table-card">
        <template #header>
          <div class="analytics-panel-heading">
            <div>
              <h2><morph-icon icon="package" size="18" stroke-width="1.8" />SKU 商品表现</h2>
              <span>展现 → 浏览 → 加购 → 下单转化链路</span>
            </div>
          </div>
        </template>
        <div class="analytics-table-meta">
          <span>共 {{ formatInteger(traffic?.total) }} 个 SKU</span>
          <span v-if="trafficLoading" class="analytics-loading-label">正在加载流量转化数据…</span>
        </div>
        <NDataTable
          class="analytics-table"
          :columns="trafficColumns"
          :data="traffic?.items ?? []"
          :loading="trafficLoading"
          :pagination="false"
          :remote="true"
          :scroll-x="1360"
          table-layout="fixed"
        >
          <template #empty><EmptyState :title="trafficError ? '流量转化数据加载失败' : '该条件下暂无流量数据'" icon="search" /></template>
        </NDataTable>
        <div class="analytics-pager">
          <span>第 {{ filters.page }} / {{ trafficPageCount }} 页，共 {{ formatInteger(traffic?.total) }} 个 SKU</span>
          <NPagination
            :page="filters.page"
            :page-count="trafficPageCount"
            :page-size="PAGE_SIZE"
            :disabled="trafficLoading"
            :page-slot="7"
            @update:page="changePage"
          />
        </div>
      </NCard>
    </template>

    <template v-else>
      <NCard :bordered="false" class="analytics-table-card">
        <template #header>
          <div class="analytics-panel-heading">
            <div>
              <h2><morph-icon icon="search" size="18" stroke-width="1.8" />商品搜索表现</h2>
              <span>点击查看关键词后才加载该 SKU 的详情</span>
            </div>
          </div>
        </template>
        <div class="analytics-table-meta">
          <span>共 {{ formatInteger(productQueries?.total) }} 个 SKU</span>
          <span v-if="productQueriesLoading" class="analytics-loading-label">正在加载商品搜索表现…</span>
        </div>
        <NDataTable
          class="analytics-table"
          :columns="productQueryColumns"
          :data="productQueries?.items ?? []"
          :loading="productQueriesLoading"
          :pagination="false"
          :remote="true"
          :scroll-x="1140"
          table-layout="fixed"
        >
          <template #empty><EmptyState :title="productQueriesError ? '商品搜索表现加载失败' : '该条件下暂无搜索表现数据'" icon="search" /></template>
        </NDataTable>
        <div class="analytics-pager">
          <span>第 {{ filters.page }} / {{ productQueryPageCount }} 页，共 {{ formatInteger(productQueries?.total) }} 个 SKU</span>
          <NPagination
            :page="filters.page"
            :page-count="productQueryPageCount"
            :page-size="PAGE_SIZE"
            :disabled="productQueriesLoading"
            :page-slot="7"
            @update:page="changePage"
          />
        </div>
      </NCard>

      <NCard v-if="selectedDetail" :bordered="false" class="analytics-table-card analytics-detail-card">
        <template #header>
          <div class="analytics-panel-heading">
            <div>
              <h2><morph-icon icon="fileText" size="18" stroke-width="1.8" />{{ selectedDetail.shop_name }} · {{ selectedDetail.sku }} 搜索关键词</h2>
              <span>仅显示当前点击 SKU</span>
            </div>
          </div>
        </template>
        <NAlert v-if="detailError" type="error" class="analytics-detail-error" :title="detailError">
          <NButton size="small" @click="retryDetails">重试</NButton>
        </NAlert>
        <NDataTable
          class="analytics-table"
          :columns="detailColumns"
          :data="details?.items ?? []"
          :loading="detailLoading"
          :pagination="false"
          :remote="true"
          :scroll-x="980"
          table-layout="fixed"
        >
          <template #empty><EmptyState :title="detailError ? '搜索关键词加载失败' : '该 SKU 暂无关键词明细'" icon="search" /></template>
        </NDataTable>
        <div class="analytics-pager">
          <span>第 {{ detailPage }} / {{ detailPageCount }} 页，共 {{ formatInteger(details?.total) }} 条关键词</span>
          <NPagination
            :page="detailPage"
            :page-count="detailPageCount"
            :page-size="PAGE_SIZE"
            :disabled="detailLoading"
            :page-slot="7"
            @update:page="changeDetailPage"
          />
        </div>
      </NCard>
    </template>
  </section>
</template>
