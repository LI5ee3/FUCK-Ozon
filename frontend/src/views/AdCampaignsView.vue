<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch, type VNodeChild } from "vue";
import type { LocationQuery } from "vue-router";
import { useRoute, useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDatePicker,
  NEmpty,
  NSelect,
  useMessage,
} from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { getAdCampaignStats, type AdCampaignStatsQuery } from "../api/ads";
import { getErrorMessage } from "../api/client";
import { useShop } from "../composables/useShop";
import type {
  AdCampaignItem,
  AdCampaignSort,
  AdCampaignState,
  ShopSelection,
} from "../types/api";
import { beijingToday, parseValidDateRange, shiftDays, subtractMonths, type DateRange } from "../utils/date";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../utils/format";
import { isShopSelection, positiveInteger, queryValue } from "../utils/query";

type AdCampaignFilters = {
  shopId: ShopSelection;
  from: string;
  to: string;
  state: AdCampaignState;
  sort: AdCampaignSort;
  page: number;
};
type DatePreset = "today" | "3days" | "7days" | "3months" | "all";

const PAGE_SIZE = 50;
const DEFAULT_SORT: AdCampaignSort = "spend_rub";
const stateOptions: Array<{ label: string; value: AdCampaignState }> = [
  { label: "全部状态", value: "" },
  { label: "运行中", value: "CAMPAIGN_STATE_RUNNING" },
  { label: "未激活", value: "CAMPAIGN_STATE_INACTIVE" },
  { label: "已归档", value: "CAMPAIGN_STATE_ARCHIVED" },
  { label: "已停止", value: "CAMPAIGN_STATE_STOPPED" },
];
const sortOptions: Array<{ label: string; value: AdCampaignSort }> = [
  { label: "广告花费", value: "spend_rub" },
  { label: "广告销售额", value: "revenue_rub" },
  { label: "广告订单", value: "orders" },
  { label: "DRR", value: "drr" },
  { label: "ROAS", value: "roas" },
  { label: "曝光", value: "impressions" },
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
const filters = reactive<AdCampaignFilters>(parseFilters(route.query, selectedShopId.value));
const rows = ref<AdCampaignItem[]>([]);
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
    const [from, to] = presetRange(preset.key);
    if (filters.from === from && filters.to === to) return preset.key;
  }
  return "";
});
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / responsePageSize.value), loading.value ? filters.page : 1));

function defaultDateRange(): DateRange {
  const today = beijingToday();
  return [shiftDays(today, -6), today];
}

function isCampaignState(value: string): value is AdCampaignState {
  return stateOptions.some((option) => option.value === value);
}

function isCampaignSort(value: string): value is AdCampaignSort {
  return sortOptions.some((option) => option.value === value);
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): AdCampaignFilters {
  const [from, to] = parseValidDateRange(queryValue(query, "from"), queryValue(query, "to"), defaultDateRange());
  const shop = queryValue(query, "shop_id");
  const state = queryValue(query, "state");
  const sort = queryValue(query, "sort");
  return {
    shopId: isShopSelection(shop) ? Number(shop) as ShopSelection : fallbackShop,
    from,
    to,
    state: isCampaignState(state) ? state : "",
    sort: isCampaignSort(sort) ? sort : DEFAULT_SORT,
    page: positiveInteger(queryValue(query, "page"), 1),
  };
}

function presetRange(preset: DatePreset): DateRange {
  const today = beijingToday();
  if (preset === "today") return [today, today];
  if (preset === "3days") return [shiftDays(today, -2), today];
  if (preset === "7days") return [shiftDays(today, -6), today];
  if (preset === "3months") return [subtractMonths(today, 3), today];
  return ["2020-01-01", today];
}

function queryFor(value: AdCampaignFilters): Record<string, string> {
  return {
    shop_id: String(value.shopId),
    from: value.from,
    to: value.to,
    state: value.state,
    sort: value.sort,
    page: String(value.page),
  };
}

function queryMatches(query: LocationQuery, value: AdCampaignFilters): boolean {
  const expected = queryFor(value);
  const keys = new Set([...Object.keys(query), ...Object.keys(expected)]);
  return [...keys].every((key) => queryValue(query, key) === (expected[key] ?? ""));
}

function applyRouteQuery(query: LocationQuery, fallbackShop: ShopSelection): AdCampaignFilters {
  const next = parseFilters(query, fallbackShop);
  Object.assign(filters, next);
  if (selectedShopId.value !== next.shopId) {
    ignoreNextShopChange = true;
    selectShop(next.shopId);
  }
  return next;
}

function currentFilters(): AdCampaignFilters {
  return { ...filters };
}

function resetDataForLoad(): void {
  loading.value = true;
  error.value = "";
  rows.value = [];
  total.value = 0;
  dataThrough.value = null;
}

function updateFilters(overrides: Partial<AdCampaignFilters>): void {
  const next = { ...currentFilters(), ...overrides };
  Object.assign(filters, next);
  if (queryMatches(route.query, next)) {
    void loadCampaigns(next);
    return;
  }
  requestId += 1;
  resetDataForLoad();
  void router.push({ query: queryFor(next) });
}

async function loadCampaigns(queryFilters: AdCampaignFilters): Promise<void> {
  const currentRequest = ++requestId;
  resetDataForLoad();
  try {
    const query: AdCampaignStatsQuery = {
      shopId: queryFilters.shopId,
      from: queryFilters.from,
      to: queryFilters.to,
      state: queryFilters.state,
      sort: queryFilters.sort,
      page: queryFilters.page,
      size: PAGE_SIZE,
    };
    const data = await getAdCampaignStats(query);
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
  void loadCampaigns(currentFilters());
}

function handleDateRangeChange(value: string | DateRange | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  const [from, to] = parseValidDateRange(value[0], value[1], defaultDateRange());
  if (from !== value[0] || to !== value[1]) return;
  updateFilters({ from, to, page: 1 });
}

function selectPreset(preset: DatePreset): void {
  const [from, to] = presetRange(preset);
  updateFilters({ from, to, page: 1 });
}

function handleStateChange(value: string | number | null): void {
  updateFilters({ state: typeof value === "string" && isCampaignState(value) ? value : "", page: 1 });
}

function handleSortChange(value: string | number | null): void {
  updateFilters({ sort: typeof value === "string" && isCampaignSort(value) ? value : DEFAULT_SORT, page: 1 });
}

function changePage(page: number): void {
  if (page >= 1 && page <= pageCount.value && page !== filters.page) updateFilters({ page });
}

function campaignRowKey(row: AdCampaignItem): string {
  return `${row.shop_id}:${row.campaign_id}`;
}

function display(value: string | null | undefined): string {
  return value || "—";
}

function renderCampaign(row: AdCampaignItem): VNodeChild {
  return h("div", { class: "ad-campaigns-campaign-cell" }, [
    h("strong", { title: row.name || row.campaign_id }, row.name || row.campaign_id),
    h("small", { class: "ad-campaigns-subline" }, `${display(row.shop_name)} · ${row.campaign_id}`),
  ]);
}

function renderState(row: AdCampaignItem): VNodeChild {
  const label = row.state ? stateOptions.find((option) => option.value === row.state)?.label ?? row.state : "—";
  return h("span", { class: "ad-campaigns-state", title: row.state || "—" }, label);
}

function renderType(row: AdCampaignItem): VNodeChild {
  return h("div", { class: "ad-campaigns-type-cell" }, [
    h("span", row.adv_object_type || "—"),
    h("small", { class: "ad-campaigns-subline" }, row.placement || "—"),
  ]);
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

function integer(value: number): string {
  return formatInteger(value);
}

const columns: DataTableColumns<AdCampaignItem> = [
  { key: "campaign", title: "Campaign", minWidth: 230, render: renderCampaign },
  { key: "state", title: "状态", width: 110, render: renderState },
  { key: "type", title: "类型 / Placement", width: 170, render: renderType },
  { key: "weekly_budget", title: "周预算", width: 130, align: "right", render: (row) => money(row.weekly_budget) },
  { key: "impressions", title: "曝光", width: 105, align: "right", render: (row) => integer(row.impressions) },
  { key: "clicks", title: "点击", width: 100, align: "right", render: (row) => integer(row.clicks) },
  { key: "ctr", title: "CTR", width: 95, align: "right", render: (row) => rate(row.ctr) },
  { key: "spend_rub", title: "广告花费", width: 135, align: "right", render: (row) => money(row.spend_rub) },
  { key: "avg_cpc_rub", title: "平均 CPC", width: 135, align: "right", render: (row) => money(row.avg_cpc_rub) },
  { key: "orders", title: "订单", width: 95, align: "right", render: (row) => integer(row.orders) },
  { key: "revenue_rub", title: "销售额", width: 135, align: "right", render: (row) => money(row.revenue_rub) },
  { key: "drr", title: "DRR", width: 95, align: "right", render: (row) => rate(row.drr) },
  { key: "roas", title: "ROAS", width: 95, align: "right", render: (row) => ratio(row.roas) },
];

watch(() => route.fullPath, () => {
  if (!routeReady) return;
  const next = applyRouteQuery(route.query, selectedShopId.value);
  void loadCampaigns(next);
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
  if (!queryMatches(route.query, next)) {
    void router.replace({ query: queryFor(next) });
  } else {
    void loadCampaigns(next);
  }
});

onBeforeUnmount(() => {
  requestId += 1;
});
</script>

<template>
  <section class="ad-campaigns-view">
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
          aria-label="广告活动日期范围"
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
        <span>广告活动数据未更新，请重试。</span>
        <NButton size="small" @click="retry">重试</NButton>
      </div>
    </NAlert>

    <NCard :bordered="false" class="ad-campaigns-card">
      <template #header>
        <div class="ad-campaigns-panel-header">
          <div class="ad-campaigns-panel-heading">
            <h2><morph-icon icon="layers" size="18" stroke-width="1.8" />广告活动</h2>
            <span>Campaign 元数据与本地广告日统计区间汇总</span>
          </div>
          <div class="ad-campaigns-filter-inline">
            <NSelect
              :value="filters.state"
              :options="stateOptions"
              class="ad-campaigns-filter ad-campaigns-filter--state"
              aria-label="Campaign 状态"
              @update:value="handleStateChange"
            />
            <NSelect
              :value="filters.sort"
              :options="sortOptions"
              class="ad-campaigns-filter ad-campaigns-filter--sort"
              aria-label="Campaign 排序"
              @update:value="handleSortChange"
            />
          </div>
        </div>
      </template>

      <div class="ad-campaigns-table-meta">
        <span>共 {{ formatNumber(total, 0) }} 个 Campaign</span>
        <span v-if="loading" class="ad-campaigns-loading-label">正在加载…</span>
      </div>

      <NDataTable
        class="ad-campaigns-table"
        :columns="columns"
        :data="rows"
        :loading="loading"
        :pagination="false"
        :remote="true"
        :scroll-x="1650"
        :row-key="campaignRowKey"
      >
        <template #empty><NEmpty :description="error ? '广告活动加载失败' : '所选范围暂无 Campaign 数据'" /></template>
      </NDataTable>

      <div class="ad-campaigns-pager">
        <span>第 {{ filters.page }} / {{ pageCount }} 页 · 共 {{ formatNumber(total, 0) }} 条</span>
        <div class="ad-campaigns-pager-actions">
          <NButton size="small" :disabled="loading || filters.page <= 1" @click="changePage(filters.page - 1)">上一页</NButton>
          <NButton size="small" :disabled="loading || filters.page >= pageCount" @click="changePage(filters.page + 1)">下一页</NButton>
        </div>
      </div>
    </NCard>

    <p class="ads-data-note">页面只读取本地 SQLite；请在“数据同步中心”先同步广告 Campaign 与广告日统计。</p>
  </section>
</template>
