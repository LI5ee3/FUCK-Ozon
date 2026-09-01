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
  NPagination,
  NTag,
} from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import ChannelTag from "../../shared/components/ChannelTag.vue";
import DatePresetPills from "../../shared/components/DatePresetPills.vue";
import EmptyState from "../../shared/components/EmptyState.vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import SearchField from "../../shared/components/SearchField.vue";
import "../../styles/analytics.css";
import "./actual-profit.css";
import { getErrorMessage } from "../../shared/api/client";
import { useShop } from "../../shared/composables/useShop";
import type { Channel, ShopSelection } from "../../shared/types/common";
import {
  beijingThreeMonthRange,
  parseValidDateRange,
  standardDatePresetRange,
  type DateRange,
  type StandardDatePreset,
} from "../../shared/utils/date";
import { formatBeijingDateTime } from "../../shared/utils/format";
import { positiveInteger, queryMatches, queryValue, shopSelectionFromQuery } from "../../shared/utils/query";
import { listActualOrderProfits } from "./api";
import type { ActualProfitOrder, ActualProfitResponse } from "./types";

type DatePreset = StandardDatePreset;
type ActualProfitFilters = {
  shopId: ShopSelection;
  from: string;
  to: string;
  search: string;
  page: number;
};

const PAGE_SIZE = 50;
const route = useRoute();
const router = useRouter();
const { selectedShopId, selectShop } = useShop();
const datePresets: ReadonlyArray<{ key: DatePreset; label: string }> = [
  { key: "today", label: "今天" },
  { key: "3days", label: "3天内" },
  { key: "7days", label: "7天内" },
  { key: "3months", label: "近三个月" },
  { key: "all", label: "全部时间" },
];
const initialFilters = parseFilters(route.query, selectedShopId.value);
const filters = reactive<ActualProfitFilters>(initialFilters);
const searchDraft = ref(initialFilters.search);
const response = ref<ActualProfitResponse | null>(null);
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
const items = computed(() => response.value?.items ?? []);
const total = computed(() => response.value?.total ?? 0);
const pageSize = computed(() => response.value?.size || PAGE_SIZE);
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
const currentPage = computed(() => response.value?.page ?? filters.page);

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): ActualProfitFilters {
  const [from, to] = parseValidDateRange(queryValue(query, "from"), queryValue(query, "to"), beijingThreeMonthRange());
  return {
    shopId: shopSelectionFromQuery(query, fallbackShop),
    from,
    to,
    search: queryValue(query, "q").trim(),
    page: positiveInteger(queryValue(query, "page"), 1),
  };
}

function queryFor(value: ActualProfitFilters): Record<string, string> {
  const defaultRange = beijingThreeMonthRange();
  const query: Record<string, string> = { shop_id: String(value.shopId) };
  const search = value.search.trim();
  if (search) query.q = search;
  if (value.page !== 1) query.page = String(value.page);
  if (value.from !== defaultRange[0] || value.to !== defaultRange[1]) {
    query.from = value.from;
    query.to = value.to;
  }
  return query;
}

function applyRouteQuery(query: LocationQuery, fallbackShop: ShopSelection): ActualProfitFilters {
  const next = parseFilters(query, fallbackShop);
  Object.assign(filters, next);
  searchDraft.value = next.search;
  if (selectedShopId.value !== next.shopId) {
    ignoreNextShopChange = true;
    selectShop(next.shopId);
  }
  return next;
}

function updateRoute(next: ActualProfitFilters, replace = false): void {
  const normalized = { ...next, search: next.search.trim() };
  Object.assign(filters, normalized);
  searchDraft.value = normalized.search;
  if (queryMatches(route.query, queryFor(normalized))) {
    void loadActualProfits(normalized);
    return;
  }
  void (replace ? router.replace({ query: queryFor(normalized) }) : router.push({ query: queryFor(normalized) }));
}

function currentFilters(): ActualProfitFilters {
  const next = { ...filters, search: searchDraft.value.trim() };
  if (!queryValue(route.query, "from") && !queryValue(route.query, "to")) {
    [next.from, next.to] = beijingThreeMonthRange();
  }
  return next;
}

function updateFilters(overrides: Partial<ActualProfitFilters>, replace = false): void {
  updateRoute({ ...currentFilters(), ...overrides }, replace);
}

async function loadActualProfits(queryFilters: ActualProfitFilters): Promise<void> {
  const currentRequest = ++requestId;
  loading.value = true;
  error.value = "";
  response.value = null;
  try {
    const data = await listActualOrderProfits({
      shopId: queryFilters.shopId,
      dateFrom: queryFilters.from,
      dateTo: queryFilters.to,
      search: queryFilters.search || undefined,
      page: queryFilters.page,
      size: PAGE_SIZE,
    });
    if (currentRequest !== requestId) return;
    const responsePageCount = Math.max(1, Math.ceil(data.total / (data.size || PAGE_SIZE)));
    if (queryFilters.page > responsePageCount) {
      if (queryMatches(route.query, queryFor(currentFilters()))) {
        await router.replace({ query: queryFor({ ...queryFilters, page: responsePageCount }) });
      }
      return;
    }
    response.value = data;
  } catch (cause) {
    if (currentRequest === requestId) error.value = getErrorMessage(cause);
  } finally {
    if (currentRequest === requestId) loading.value = false;
  }
}

function retry(): void {
  const next = currentFilters();
  Object.assign(filters, next);
  void loadActualProfits(next);
}

function submitSearch(): void {
  updateFilters({ search: searchDraft.value, page: 1 });
}

function clearSearch(): void {
  searchDraft.value = "";
  updateFilters({ search: "", page: 1 });
}

function handleDateRangeChange(value: string | DateRange | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  const [from, to] = parseValidDateRange(value[0], value[1], beijingThreeMonthRange());
  if (from !== value[0] || to !== value[1]) return;
  updateFilters({ from, to, page: 1 });
}

function selectPreset(preset: DatePreset): void {
  const [from, to] = standardDatePresetRange(preset);
  updateFilters({ from, to, page: 1 });
}

function changePage(page: number): void {
  if (page !== filters.page) updateFilters({ page });
}

function isChannel(value: string): value is Channel {
  return value === "FBP" || value === "realFBS" || value === "WHD";
}

const decimalFormatter = new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function displayDecimal(value: string | null): number | null {
  if (typeof value !== "string" || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatDecimal(value: string | null): string {
  const parsed = displayDecimal(value);
  return parsed === null
    ? "—"
    : decimalFormatter.format(parsed);
}

function formatCny(value: string | null): string {
  const parsed = displayDecimal(value);
  if (parsed === null) return "—";
  const absolute = decimalFormatter.format(Math.abs(parsed));
  return parsed < 0 ? `-¥${absolute}` : `¥${absolute}`;
}

function isNegative(value: string | null): boolean {
  const parsed = displayDecimal(value);
  return parsed !== null && parsed < 0;
}

const incompleteReasonLabels: Record<string, string> = {
  missing_order_items: "缺订单明细",
  missing_finance: "缺 Finance",
  missing_erp_cost: "缺 ERP 成本",
  quantity_mismatch: "数量不一致",
  missing_exchange_rate: "缺 ERP 汇率",
  exchange_rate_mismatch: "ERP 汇率不一致",
  finance_currency_mismatch: "Finance 币种异常",
};

function formatIncompleteReasons(reasons: string[]): string {
  const labels = [...new Set(reasons.map((reason) => incompleteReasonLabels[reason] ?? "数据校验异常"))];
  if (!labels.length) return "数据校验异常";
  const visible = labels.slice(0, 2).join(" · ");
  return labels.length > 2 ? `${visible} +${labels.length - 2}` : visible;
}

function renderOrderCell(row: ActualProfitOrder): VNodeChild {
  return h("strong", { class: "actual-profit-order", title: row.posting_number }, row.posting_number);
}

function renderShopChannelCell(row: ActualProfitOrder): VNodeChild {
  return h("div", { class: "actual-profit-shop-cell" }, [
    h("strong", { title: row.shop_name }, row.shop_name),
    isChannel(row.channel)
      ? h(ChannelTag, { channel: row.channel })
      : h("span", { class: "actual-profit-channel-neutral" }, row.channel || "—"),
  ]);
}

function renderCreatedAtCell(row: ActualProfitOrder): VNodeChild {
  return h("span", { class: "actual-profit-time" }, formatBeijingDateTime(row.created_at));
}

function renderFinanceCell(row: ActualProfitOrder): VNodeChild {
  const original = formatDecimal(row.finance.net_amount);
  const originalCurrency = row.finance.currency && row.finance.currency !== "CNY" && original !== "—"
    ? `${original} ${row.finance.currency}`
    : null;
  return h("div", { class: "actual-profit-money-cell actual-profit-finance-cell" }, [
    h("strong", { class: "actual-profit-money" }, formatCny(row.finance.net_cny)),
    originalCurrency ? h("small", { class: "actual-profit-money-sub" }, originalCurrency) : null,
  ]);
}

function renderErpCostCell(row: ActualProfitOrder): VNodeChild {
  const matched = row.erp_cost.item_count > 0
    ? `${row.erp_cost.matched_items} / ${row.erp_cost.item_count} 成本匹配`
    : null;
  return h("div", { class: "actual-profit-money-cell actual-profit-erp-cell" }, [
    h("strong", { class: "actual-profit-money" }, formatCny(row.erp_cost.total_cost_cny)),
    matched ? h("small", { class: "actual-profit-money-sub" }, matched) : null,
  ]);
}

function renderProfitCell(row: ActualProfitOrder): VNodeChild {
  const value = row.profit_status === "ready" ? row.actual_profit_cny : null;
  return h("strong", {
    class: ["actual-profit-money", "actual-profit-profit", { "is-negative": isNegative(value) }],
  }, formatCny(value));
}

function renderStatusCell(row: ActualProfitOrder): VNodeChild {
  const ready = row.profit_status === "ready";
  return h("div", { class: "actual-profit-status-cell" }, [
    h(NTag, {
      bordered: false,
      round: true,
      size: "small",
      type: ready ? "success" : "warning",
      class: `actual-profit-status-tag actual-profit-status-tag--${ready ? "ready" : "incomplete"}`,
    }, { default: () => ready ? "完整" : "数据不完整" }),
    !ready
      ? h("small", {
          class: "actual-profit-reasons",
          title: row.incomplete_reasons.map((reason) => incompleteReasonLabels[reason] ?? "数据校验异常").join(" · "),
        }, formatIncompleteReasons(row.incomplete_reasons))
      : null,
  ]);
}

const columns: DataTableColumns<ActualProfitOrder> = [
  { key: "posting_number", title: "订单", width: 180, render: renderOrderCell },
  { key: "shop_channel", title: "店铺 / 渠道", width: 180, render: renderShopChannelCell },
  { key: "created_at", title: "创建时间", width: 160, render: renderCreatedAtCell },
  { key: "finance", title: "Finance 实际净额", width: 180, align: "right", render: renderFinanceCell },
  { key: "erp_cost", title: "ERP 商品成本", width: 180, align: "right", render: renderErpCostCell },
  { key: "actual_profit_cny", title: "实际利润", width: 160, align: "right", render: renderProfitCell },
  { key: "profit_status", title: "数据状态", width: 220, render: renderStatusCell },
];

watch(() => route.fullPath, () => {
  if (!routeReady) return;
  const next = applyRouteQuery(route.query, 0);
  void loadActualProfits(next);
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
    void loadActualProfits(next);
  }
});

onBeforeUnmount(() => { requestId += 1; });
</script>

<template>
  <section class="actual-profit-view">
    <form class="actual-profit-toolbar" role="search" @submit.prevent="submitSearch">
      <div class="actual-profit-date-control">
        <span>订单创建日期</span>
        <NDatePicker
          :formatted-value="dateRange"
          type="daterange"
          value-format="yyyy-MM-dd"
          separator="至"
          :clearable="false"
          class="actual-profit-date-picker"
          aria-label="实际利润订单日期范围"
          @update:formatted-value="handleDateRangeChange"
        />
        <DatePresetPills
          class="actual-profit-date-presets"
          aria-label="日期快捷范围"
          :options="datePresets"
          :active-key="activePreset"
          @select="selectPreset"
        />
      </div>
      <div class="actual-profit-search">
        <SearchField
          v-model:value="searchDraft"
          type="text"
          aria-label="搜索实际利润订单"
          placeholder="搜索订单号、SKU 或货号…"
          @keydown.enter.prevent="submitSearch"
          @clear="clearSearch"
        />
        <NButton type="primary" attr-type="submit" :loading="loading">
          <template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>
          查询
        </NButton>
      </div>
    </form>

    <NAlert v-if="error" type="error" class="analytics-error" :title="error">
      <div class="analytics-error-content">
        <span>实际利润订单未更新，请重试。</span>
        <NButton size="small" @click="retry">重试</NButton>
      </div>
    </NAlert>

    <NCard :bordered="false" class="analytics-table-card actual-profit-panel">
      <template #header>
        <div class="analytics-panel-heading">
          <div>
            <h2><morph-icon icon="trendingUp" size="18" stroke-width="1.8" />实际利润订单</h2>
            <span>Ozon Finance 实际事实 + 马帮 ERP 历史实际成本；按订单创建时间查询</span>
          </div>
          <span v-if="loading" class="analytics-loading-label">实际利润订单加载中…</span>
        </div>
      </template>

      <div class="analytics-table-meta">
        <span>共 {{ total }} 个订单</span>
        <span v-if="loading" class="analytics-loading-label">正在加载…</span>
      </div>

      <NDataTable
        class="analytics-table actual-profit-table"
        :columns="columns"
        :data="items"
        :loading="loading"
        :pagination="false"
        :remote="true"
        :scroll-x="1260"
        table-layout="fixed"
        :row-key="(row: ActualProfitOrder) => `${row.shop_id}:${row.posting_number}`"
      >
        <template #empty>
          <EmptyState
            icon="trendingUp"
            :title="error ? '实际利润订单加载失败' : '当前条件下没有实际利润订单'"
            :hint="error ? '请点击上方重试。' : undefined"
          />
        </template>
      </NDataTable>

      <div class="analytics-pager actual-profit-pager">
        <span>第 {{ currentPage }} / {{ pageCount }} 页，共 {{ total }} 个订单</span>
        <NPagination
          :page="currentPage"
          :page-count="pageCount"
          :page-size="pageSize"
          :disabled="loading"
          :page-slot="7"
          @update:page="changePage"
        />
      </div>
    </NCard>
  </section>
</template>
