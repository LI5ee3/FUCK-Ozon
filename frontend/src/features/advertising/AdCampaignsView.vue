<script setup lang="ts">
import DatePresetPills from "../../shared/components/DatePresetPills.vue";
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
  NSelect,
  NSpin,
  NTag,
  useMessage,
} from "naive-ui";
import EmptyState from "../../shared/components/EmptyState.vue";
import type { IconName } from "../../shared/icons/tabler";
import type { DataTableColumns } from "naive-ui";
import { getAdCampaignStats, type AdCampaignStatsQuery } from "./api";
import { getErrorMessage } from "../../shared/api/client";
import { useShop } from "../../shared/composables/useShop";
import type {
  AdCampaignItem,
  AdCampaignSort,
  AdCampaignState,
} from "./types";
import type { ShopSelection } from "../../shared/types/common";
import { parseValidDateRange, standardDatePresetRange, type DateRange, type StandardDatePreset } from "../../shared/utils/date";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../../shared/utils/format";
import { positiveInteger, queryMatches, queryValue, shopSelectionFromQuery } from "../../shared/utils/query";

type AdCampaignFilters = {
  shopId: ShopSelection;
  from: string;
  to: string;
  state: AdCampaignState;
  sort: AdCampaignSort;
  page: number;
};
type DatePreset = StandardDatePreset;

const PAGE_SIZE = 50;
const DEFAULT_SORT: AdCampaignSort = "spend_rub";
// One source for the state filter options and the inline tone state tags
// (DESIGN.md §3: status tags render inline, tone shells carry the color).
const campaignStateMeta: ReadonlyArray<{ value: Exclude<AdCampaignState, "">; label: string; icon: IconName; tagClass: string }> = [
  { value: "CAMPAIGN_STATE_RUNNING", label: "运行中", icon: "bolt", tagClass: "ad-campaigns-state-tag--running" },
  { value: "CAMPAIGN_STATE_INACTIVE", label: "未激活", icon: "clock", tagClass: "ad-campaigns-state-tag--inactive" },
  { value: "CAMPAIGN_STATE_ARCHIVED", label: "已归档", icon: "folder", tagClass: "ad-campaigns-state-tag--archived" },
  { value: "CAMPAIGN_STATE_STOPPED", label: "已停止", icon: "xCircle", tagClass: "ad-campaigns-state-tag--stopped" },
];
const stateOptions: Array<{ label: string; value: AdCampaignState }> = [
  { label: "全部状态", value: "" },
  ...campaignStateMeta.map(({ value, label }) => ({ value, label })),
];
const objectTypeLabels: Record<string, string> = {
  SKU: "商品推广",
  SEARCH_PROMO: "搜索推广",
};
const placementLabels: Record<string, string> = {
  PLACEMENT_SEARCH_AND_CATEGORY: "搜索与分类",
  PLACEMENT_TOP_PROMOTION: "置顶推广",
};
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
    const [from, to] = standardDatePresetRange(preset.key);
    if (filters.from === from && filters.to === to) return preset.key;
  }
  return "";
});
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / responsePageSize.value), loading.value ? filters.page : 1));

function isCampaignState(value: string): value is AdCampaignState {
  return stateOptions.some((option) => option.value === value);
}

function isCampaignSort(value: string): value is AdCampaignSort {
  return sortOptions.some((option) => option.value === value);
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): AdCampaignFilters {
  const [from, to] = parseValidDateRange(queryValue(query, "from"), queryValue(query, "to"), standardDatePresetRange("7days"));
  const state = queryValue(query, "state");
  const sort = queryValue(query, "sort");
  return {
    shopId: shopSelectionFromQuery(query, fallbackShop),
    from,
    to,
    state: isCampaignState(state) ? state : "",
    sort: isCampaignSort(sort) ? sort : DEFAULT_SORT,
    page: positiveInteger(queryValue(query, "page"), 1),
  };
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
  if (queryMatches(route.query, queryFor(next))) {
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
      if (queryMatches(queryFor(currentFilters()), queryFor(queryFilters))) {
        await router.replace({ query: queryFor({ ...queryFilters, page: nextPageCount }) });
      }
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
  const [from, to] = parseValidDateRange(value[0], value[1], standardDatePresetRange("7days"));
  if (from !== value[0] || to !== value[1]) return;
  updateFilters({ from, to, page: 1 });
}

function selectPreset(preset: DatePreset): void {
  const [from, to] = standardDatePresetRange(preset);
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
  const meta = campaignStateMeta.find((item) => item.value === row.state);
  if (!meta) return h("span", { class: "ad-campaigns-state", title: row.state || "—" }, row.state || "—");
  return h(NTag, { bordered: false, round: true, size: "small", class: `ad-campaigns-state-tag ${meta.tagClass}`, title: row.state }, {
    default: () => h("span", { class: "ad-campaigns-state-content" }, [
      h(MorphIcon, { icon: meta.icon, size: "13", strokeWidth: "2" }),
      meta.label,
    ]),
  });
}

function placementText(value: string | null): string {
  if (!value) return "—";
  try {
    const parsed: unknown = JSON.parse(value);
    if (!Array.isArray(parsed)) throw new Error("placement is not an array");
    const items = parsed.filter((item): item is string => typeof item === "string" && item !== "");
    if (!items.length) return "—";
    return items
      .map((item) => placementLabels[item] ?? item.replace(/^PLACEMENT_/, "").replace(/_/g, " ").toLowerCase())
      .join("、");
  } catch {
    return placementLabels[value] ?? value;
  }
}

function renderType(row: AdCampaignItem): VNodeChild {
  const type = row.adv_object_type ? objectTypeLabels[row.adv_object_type] ?? row.adv_object_type : "—";
  return h("div", { class: "ad-campaigns-type-cell" }, [
    h("span", type),
    h("small", { class: "ad-campaigns-subline" }, placementText(row.placement)),
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

// Fixed-layout width system (DESIGN.md §3): every column carries an explicit
// width and the sum equals the table's scroll-x, so long campaign names clip
// with ellipsis instead of pushing numeric columns out of the viewport.
function numberCell(value: string): VNodeChild {
  return h("span", { class: "ad-campaigns-number" }, value);
}

const columns: DataTableColumns<AdCampaignItem> = [
  { key: "campaign", title: "Campaign", width: 240, render: renderCampaign },
  { key: "state", title: "状态", width: 110, render: renderState },
  { key: "type", title: "类型 / 版位", width: 170, render: renderType },
  { key: "weekly_budget", title: "周预算", width: 130, align: "right", render: (row) => numberCell(money(row.weekly_budget)) },
  { key: "impressions", title: "曝光", width: 100, align: "right", render: (row) => numberCell(integer(row.impressions)) },
  { key: "clicks", title: "点击", width: 90, align: "right", render: (row) => numberCell(integer(row.clicks)) },
  { key: "ctr", title: "CTR", width: 90, align: "right", render: (row) => numberCell(rate(row.ctr)) },
  { key: "spend_rub", title: "广告花费", width: 150, align: "right", render: (row) => numberCell(money(row.spend_rub)) },
  { key: "avg_cpc_rub", title: "平均 CPC", width: 120, align: "right", render: (row) => numberCell(money(row.avg_cpc_rub)) },
  { key: "orders", title: "订单", width: 90, align: "right", render: (row) => numberCell(integer(row.orders)) },
  { key: "revenue_rub", title: "销售额", width: 150, align: "right", render: (row) => numberCell(money(row.revenue_rub)) },
  { key: "drr", title: "DRR", width: 90, align: "right", render: (row) => numberCell(rate(row.drr)) },
  { key: "roas", title: "ROAS", width: 90, align: "right", render: (row) => numberCell(ratio(row.roas)) },
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
  if (!queryMatches(route.query, queryFor(next))) {
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
        <DatePresetPills class="ads-date-presets" aria-label="日期快捷范围" :options="datePresets" :active-key="activePreset" @select="selectPreset" />
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
        <div class="ads-panel-heading">
          <div>
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
        <span v-if="loading" class="ads-loading-label"><NSpin size="small" />正在加载…</span>
      </div>

      <NDataTable
        class="ad-campaigns-table"
        :columns="columns"
        :data="rows"
        :loading="loading"
        :pagination="false"
        :remote="true"
        :scroll-x="1620"
        table-layout="fixed"
        :row-key="campaignRowKey"
      >
        <template #empty><EmptyState :title="error ? '广告活动加载失败' : '所选范围暂无 Campaign 数据'" icon="layers" /></template>
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
