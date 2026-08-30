<script setup lang="ts">
import "./advertising.css";
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch, type VNodeChild } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import type { LocationQuery } from "vue-router";
import { useRoute, useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDatePicker,
  NEmpty,
  NInput,
  NSelect,
  useMessage,
} from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { getAdSkuStats, type AdSkuStatsQuery } from "./api";
import { getErrorMessage } from "../../shared/api/client";
import { useShop } from "../../shared/composables/useShop";
import type { AdSkuItem, AdSkuSort } from "./types";
import type { ShopSelection } from "../../shared/types/common";
import { copyText } from "../../shared/utils/clipboard";
import { parseValidDateRange, standardDatePresetRange, type DateRange, type StandardDatePreset } from "../../shared/utils/date";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../../shared/utils/format";
import { positiveInteger, queryMatches, queryValue, shopSelectionFromQuery } from "../../shared/utils/query";

type AdSkuFilters = {
  shopId: ShopSelection;
  q: string;
  from: string;
  to: string;
  sort: AdSkuSort;
  page: number;
};
type DatePreset = StandardDatePreset;

const PAGE_SIZE = 50;
const DEFAULT_SORT: AdSkuSort = "spend_rub";
const sortOptions: Array<{ label: string; value: AdSkuSort }> = [
  { label: "广告花费", value: "spend_rub" },
  { label: "广告销售额", value: "revenue_rub" },
  { label: "DRR", value: "drr" },
  { label: "ROAS", value: "roas" },
  { label: "广告订单", value: "orders" },
  { label: "点击", value: "clicks" },
];
const datePresets: ReadonlyArray<{ key: DatePreset; label: string }> = [
  { key: "today", label: "今天" },
  { key: "3days", label: "3天内" },
  { key: "7days", label: "7天内" },
  { key: "3months", label: "近三个月" },
  { key: "all", label: "全部时间" },
];

const route = useRoute();
const router = useRouter();
const message = useMessage();
const { selectedShopId, selectShop } = useShop();
const filters = reactive<AdSkuFilters>(parseFilters(route.query, selectedShopId.value));
const queryDraft = ref(filters.q);
const rows = ref<AdSkuItem[]>([]);
const total = ref(0);
const responsePageSize = ref(PAGE_SIZE);
const dataThrough = ref<string | null>(null);
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
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / responsePageSize.value), loading.value ? filters.page : 1));

function isAdSkuSort(value: string): value is AdSkuSort {
  return sortOptions.some((option) => option.value === value);
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): AdSkuFilters {
  const [from, to] = parseValidDateRange(queryValue(query, "from"), queryValue(query, "to"), standardDatePresetRange("7days"));
  const sort = queryValue(query, "sort");
  return {
    shopId: shopSelectionFromQuery(query, fallbackShop),
    q: queryValue(query, "q").trim(),
    from,
    to,
    sort: isAdSkuSort(sort) ? sort : DEFAULT_SORT,
    page: positiveInteger(queryValue(query, "page"), 1),
  };
}

function queryFor(value: AdSkuFilters): Record<string, string> {
  return {
    shop_id: String(value.shopId),
    from: value.from,
    to: value.to,
    q: value.q,
    sort: value.sort,
    page: String(value.page),
  };
}

function applyRouteQuery(query: LocationQuery, fallbackShop: ShopSelection): AdSkuFilters {
  const next = parseFilters(query, fallbackShop);
  Object.assign(filters, next);
  queryDraft.value = next.q;
  if (selectedShopId.value !== next.shopId) {
    ignoreNextShopChange = true;
    selectShop(next.shopId);
  }
  return next;
}

function currentFilters(): AdSkuFilters {
  return { ...filters, q: queryDraft.value.trim() };
}

function resetDataForLoad(): void {
  loading.value = true;
  error.value = "";
  rows.value = [];
  total.value = 0;
  dataThrough.value = null;
}

function updateFilters(overrides: Partial<AdSkuFilters>): void {
  const next = { ...currentFilters(), ...overrides };
  next.q = next.q.trim();
  Object.assign(filters, next);
  queryDraft.value = next.q;
  if (queryMatches(route.query, queryFor(next))) {
    void loadSkuStats(next);
    return;
  }
  requestId += 1;
  resetDataForLoad();
  void router.push({ query: queryFor(next) });
}

async function loadSkuStats(queryFilters: AdSkuFilters): Promise<void> {
  const currentRequest = ++requestId;
  resetDataForLoad();
  try {
    const query: AdSkuStatsQuery = {
      shopId: queryFilters.shopId,
      q: queryFilters.q,
      from: queryFilters.from,
      to: queryFilters.to,
      sort: queryFilters.sort,
      page: queryFilters.page,
      size: PAGE_SIZE,
    };
    const data = await getAdSkuStats(query);
    if (currentRequest !== requestId) return;
    const nextPageCount = Math.max(1, Math.ceil(data.total / (data.size || PAGE_SIZE)));
    if (queryFilters.page > nextPageCount) {
      await router.replace({ query: queryFor({ ...queryFilters, page: nextPageCount }) });
      return;
    }
    rows.value = data.items;
    total.value = data.total;
    responsePageSize.value = data.size || PAGE_SIZE;
    dataThrough.value = data.data_through;
  } catch (cause: unknown) {
    if (currentRequest !== requestId) return;
    error.value = getErrorMessage(cause);
    message.error(error.value);
  } finally {
    if (currentRequest === requestId) loading.value = false;
  }
}

function retry(): void {
  void loadSkuStats(currentFilters());
}

function submitSearch(): void {
  updateFilters({ q: queryDraft.value, page: 1 });
}

function clearSearch(): void {
  updateFilters({ q: "", page: 1 });
}

function handleDateRangeChange(value: string | DateRange | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  const [from, to] = parseValidDateRange(value[0], value[1], standardDatePresetRange("7days"));
  if (from !== value[0] || to !== value[1]) return;
  updateFilters({ from, to, page: 1 });
}

function selectPreset(preset: DatePreset): void {
  const [from, to] = standardDatePresetRange(preset);
  updateFilters({ from, to, page: 1 });
}

function handleSortChange(value: string | number | null): void {
  updateFilters({ sort: typeof value === "string" && isAdSkuSort(value) ? value : DEFAULT_SORT, page: 1 });
}

function changePage(page: number): void {
  if (page >= 1 && page <= pageCount.value && page !== filters.page) updateFilters({ page });
}

function rowKey(row: AdSkuItem): string {
  return `${row.shop_id}:${row.sku}`;
}

function finite(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value);
}

function money(value: number | null | undefined): string {
  return finite(value) ? `${formatNumber(value)} RUB` : "—";
}

function rate(value: number | null | undefined): string {
  return finite(value) ? `${value.toFixed(2)}%` : "—";
}

function ratio(value: number | null | undefined): string {
  return finite(value) ? value.toFixed(2) : "—";
}

function renderSku(row: AdSkuItem): VNodeChild {
  return h("div", { class: "ad-skus-identity-cell" }, [
    h("span", { class: "ad-skus-shop-badge" }, row.shop_name || "—"),
    h("button", {
      type: "button",
      class: "ad-skus-copy-value",
      title: "点击复制 SKU",
      "aria-label": `点击复制 SKU ${row.sku}`,
      onClick: (event: MouseEvent) => {
        event.stopPropagation();
        void copyValue(row.sku);
      },
    }, [h(MorphIcon, { icon: "copy", size: "12", strokeWidth: "2" }), `SKU ${row.sku}`]),
  ]);
}

function renderProduct(row: AdSkuItem): VNodeChild {
  return h("span", { class: "ad-skus-product-name", title: row.product_name || "—" }, row.product_name || "—");
}

function renderInteger(value: number | null | undefined): VNodeChild {
  return h("span", { class: "ad-skus-number" }, formatInteger(value));
}

async function copyValue(value: string): Promise<void> {
  try {
    await copyText(value);
    message.success(`已复制：${value}`);
  } catch {
    message.error("复制失败");
  }
}

const columns: DataTableColumns<AdSkuItem> = [
  { key: "identity", title: "店铺 / SKU", minWidth: 160, render: renderSku },
  { key: "product_name", title: "商品名称", minWidth: 280, render: renderProduct },
  { key: "campaign_count", title: "Campaign数", width: 115, align: "right", render: (row) => renderInteger(row.campaign_count) },
  { key: "impressions", title: "曝光", width: 105, align: "right", render: (row) => renderInteger(row.impressions) },
  { key: "clicks", title: "点击", width: 100, align: "right", render: (row) => renderInteger(row.clicks) },
  { key: "ctr", title: "CTR", width: 95, align: "right", render: (row) => rate(row.ctr) },
  { key: "spend_rub", title: "广告花费", width: 135, align: "right", render: (row) => money(row.spend_rub) },
  { key: "avg_cpc_rub", title: "平均 CPC", width: 135, align: "right", render: (row) => money(row.avg_cpc_rub) },
  { key: "orders", title: "广告订单", width: 105, align: "right", render: (row) => renderInteger(row.orders) },
  { key: "revenue_rub", title: "广告销售额", width: 145, align: "right", render: (row) => money(row.revenue_rub) },
  { key: "drr", title: "DRR", width: 95, align: "right", render: (row) => rate(row.drr) },
  { key: "roas", title: "ROAS", width: 95, align: "right", render: (row) => ratio(row.roas) },
];

watch(() => route.fullPath, () => {
  if (!routeReady) return;
  const next = applyRouteQuery(route.query, selectedShopId.value);
  void loadSkuStats(next);
});

watch(selectedShopId, (shopId) => {
  if (ignoreNextShopChange) {
    ignoreNextShopChange = false;
    return;
  }
  if (!routeReady || filters.shopId === shopId) return;
  updateFilters({ shopId, page: 1 });
});

onMounted(() => {
  const next = applyRouteQuery(route.query, selectedShopId.value);
  routeReady = true;
  if (!queryMatches(route.query, queryFor(next))) {
    void router.replace({ query: queryFor(next) });
  } else {
    void loadSkuStats(next);
  }
});

onBeforeUnmount(() => {
  requestId += 1;
});
</script>

<template>
  <section class="ad-skus-view">
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
          aria-label="SKU 广告分析日期范围"
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
        <span class="ads-data-through"><span class="ads-data-dot" aria-hidden="true" />数据截止 <strong>{{ formatBeijingDateTime(dataThrough) }}</strong></span>
      </div>
    </div>

    <NAlert v-if="error" type="error" class="ads-error" :title="error">
      <div class="ads-error-content">
        <span>SKU 广告数据未更新，请重试。</span>
        <NButton size="small" @click="retry">重试</NButton>
      </div>
    </NAlert>

    <NCard :bordered="false" class="ad-skus-card">
      <template #header>
        <div class="ad-skus-panel-header">
          <div class="ad-skus-panel-heading">
            <h2><morph-icon icon="tag" size="18" stroke-width="1.8" />SKU 广告分析</h2>
            <span>同店铺内按 SKU 聚合；全部店铺保留店铺维度，不跨店合并</span>
          </div>
          <div class="ad-skus-filter-inline">
            <form class="ad-skus-search-form" @submit.prevent="submitSearch">
              <NInput
                v-model:value="queryDraft"
                type="text"
                class="ad-skus-search"
                aria-label="搜索 SKU 或商品名称"
                placeholder="搜索 SKU 或商品名称…"
                @keydown.enter.prevent="submitSearch"
              >
                <template #prefix><morph-icon icon="search" size="15" stroke-width="1.8" /></template>
              </NInput>
              <NButton type="primary" attr-type="submit" :loading="loading">查询</NButton>
              <NButton attr-type="button" @click="clearSearch">清除</NButton>
            </form>
            <NSelect
              :value="filters.sort"
              :options="sortOptions"
              class="ad-skus-sort"
              aria-label="SKU 广告排序"
              @update:value="handleSortChange"
            />
          </div>
        </div>
      </template>

      <div class="ad-skus-table-meta">
        <span>共 {{ formatNumber(total, 0) }} 个 SKU</span>
        <span v-if="loading" class="ad-skus-loading-label">正在加载…</span>
      </div>

      <NDataTable
        class="ad-skus-table"
        :columns="columns"
        :data="rows"
        :loading="loading"
        :pagination="false"
        :remote="true"
        :scroll-x="1580"
        :row-key="rowKey"
      >
        <template #empty><NEmpty :description="error ? 'SKU 广告数据加载失败' : '所选范围暂无 SKU 广告数据'" /></template>
      </NDataTable>

      <div class="ad-skus-pager">
        <span>第 {{ filters.page }} / {{ pageCount }} 页 · 共 {{ formatNumber(total, 0) }} 条</span>
        <div class="ad-skus-pager-actions">
          <NButton size="small" :disabled="loading || filters.page <= 1" @click="changePage(filters.page - 1)">上一页</NButton>
          <NButton size="small" :disabled="loading || filters.page >= pageCount" @click="changePage(filters.page + 1)">下一页</NButton>
        </div>
      </div>
    </NCard>

    <p class="ads-data-note">页面只读取本地 SQLite；请在“数据同步中心”先同步 SKU 广告统计。</p>
  </section>
</template>
