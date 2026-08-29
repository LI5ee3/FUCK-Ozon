<script setup lang="ts">
import "./analytics.css";
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch, type VNodeChild } from "vue";
import MorphIcon from "../components/MorphIcon.vue";
import type { IconName } from "../icons/tabler";
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
  NPagination,
  NTag,
  useMessage,
} from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { getErrorMessage } from "../api/client";
import { listTimeliness } from "../api/timeliness";
import { useShop } from "../composables/useShop";
import type {
  Channel,
  ShopSelection,
  TimelinessGroup,
  TimelinessItem,
  TimelinessResponse,
} from "../types/api";
import { formatBeijingDateTime, formatHours, formatInteger, formatPercent } from "../utils/format";
import { beijingToday, parseValidDateRange, shiftDays, subtractMonths, type DateRange } from "../utils/date";
import { isShopSelection, positiveInteger, queryValue } from "../utils/query";

type DatePreset = "today" | "3days" | "7days" | "3months" | "all";
type TimelinessFilters = {
  shopId: ShopSelection;
  search: string;
  page: number;
  from: string;
  to: string;
};
type TagType = "default" | "info" | "success" | "warning" | "error";
type TimelinessKpi = {
  icon: IconName;
  label: string;
  value: string;
  badge?: string;
  note: string;
  tone: "azure" | "lavender" | "mint" | "peach" | "blue";
};

const PAGE_SIZE = 30;
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
const filters = reactive<TimelinessFilters>(initialFilters);
const searchDraft = ref(initialFilters.search);
const data = ref<TimelinessResponse | null>(null);
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
const pageCount = computed(() => Math.max(1, Math.ceil((data.value?.total ?? 0) / (data.value?.size || PAGE_SIZE))));
const summaryKpis = computed<TimelinessKpi[]>(() => {
  const summary = data.value?.summary;
  if (!summary) return [];
  const shipTone = summary.ship_samples && summary.p50_ship_hours != null
    ? summary.p50_ship_hours <= 24 ? "mint" : summary.p50_ship_hours <= 48 ? "lavender" : "peach"
    : "peach";
  return [
    {
      icon: "orders",
      label: "有效订单数",
      value: `${formatInteger(summary.orders)} 单`,
      badge: "全量统计",
      note: "当前店铺与筛选时间范围内有效订单",
      tone: "blue",
    },
    {
      icon: "box",
      label: "实际发货有效样本",
      value: `${formatInteger(summary.ship_samples)} 单`,
      badge: summary.orders ? `${formatPercent(summary.ship_samples / summary.orders)} 样本率` : undefined,
      note: "含真实且有效的实际出库时间",
      tone: "mint",
    },
    {
      icon: "clock",
      label: "发货出库时效 P50",
      value: summary.ship_samples ? formatHours(summary.p50_ship_hours) : "数据不足",
      badge: summary.ship_samples ? "中位数" : undefined,
      note: "50% 的订单在此时间内完成出库发货",
      tone: shipTone,
    },
    {
      icon: "truck",
      label: "在途配送时效 P50",
      value: summary.delivery_samples ? formatHours(summary.p50_delivery_hours) : "数据不足",
      badge: summary.delivery_samples ? "中位数" : undefined,
      note: "50% 的订单在发货后此时间内完成派送签收",
      tone: "lavender",
    },
  ];
});

function defaultDateRange(): DateRange {
  const today = beijingToday();
  return [subtractMonths(today, 3), today];
}

function parseDateRange(from: string, to: string): DateRange {
  return parseValidDateRange(from, to, defaultDateRange());
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): TimelinessFilters {
  const shop = queryValue(query, "shop_id");
  const [from, to] = parseDateRange(queryValue(query, "from"), queryValue(query, "to"));
  return {
    shopId: isShopSelection(shop) ? Number(shop) as ShopSelection : fallbackShop,
    search: queryValue(query, "q").trim(),
    page: positiveInteger(queryValue(query, "page"), 1),
    from,
    to,
  };
}

function presetRange(preset: DatePreset): DateRange {
  const today = beijingToday();
  if (preset === "today") return [today, today];
  if (preset === "3days") return [shiftDays(today, -2), today];
  if (preset === "7days") return [shiftDays(today, -6), today];
  if (preset === "all") return ["2020-01-01", today];
  return defaultDateRange();
}

function queryFor(value: TimelinessFilters): Record<string, string> {
  const defaultRange = defaultDateRange();
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

function queryMatches(query: LocationQuery, value: TimelinessFilters): boolean {
  const expected = queryFor(value);
  const keys = new Set([...Object.keys(query), ...Object.keys(expected)]);
  return [...keys].every((key) => queryValue(query, key) === (expected[key] ?? ""));
}

function applyRouteQuery(query: LocationQuery, fallbackShop: ShopSelection): TimelinessFilters {
  const next = parseFilters(query, fallbackShop);
  Object.assign(filters, next);
  searchDraft.value = next.search;
  if (selectedShopId.value !== next.shopId) {
    ignoreNextShopChange = true;
    selectShop(next.shopId);
  }
  return next;
}

function updateRoute(next: TimelinessFilters, replace = false): void {
  const normalized = { ...next, search: next.search.trim() };
  Object.assign(filters, normalized);
  searchDraft.value = normalized.search;
  if (queryMatches(route.query, normalized)) {
    void loadTimeliness(normalized);
    return;
  }
  void (replace ? router.replace({ query: queryFor(normalized) }) : router.push({ query: queryFor(normalized) }));
}

function currentFilters(): TimelinessFilters {
  const next = { ...filters, search: searchDraft.value };
  if (!queryValue(route.query, "from") && !queryValue(route.query, "to")) {
    [next.from, next.to] = defaultDateRange();
  }
  return next;
}

function updateFilters(overrides: Partial<TimelinessFilters>): void {
  updateRoute({ ...currentFilters(), ...overrides });
}

async function loadTimeliness(queryFilters: TimelinessFilters): Promise<void> {
  const currentRequest = ++requestId;
  loading.value = true;
  error.value = "";
  data.value = null;
  try {
    const response = await listTimeliness({
      shopId: queryFilters.shopId,
      page: queryFilters.page,
      size: PAGE_SIZE,
      search: queryFilters.search || undefined,
      from: queryFilters.from,
      to: queryFilters.to,
    });
    if (currentRequest !== requestId) return;
    const pages = Math.max(1, Math.ceil(response.total / (response.size || PAGE_SIZE)));
    if (queryFilters.page > pages) {
      await router.replace({ query: queryFor({ ...queryFilters, page: pages }) });
      return;
    }
    data.value = response;
  } catch (cause) {
    if (currentRequest !== requestId) return;
    error.value = getErrorMessage(cause);
    message.error(error.value);
  } finally {
    if (currentRequest === requestId) loading.value = false;
  }
}

function retry(): void {
  const next = currentFilters();
  Object.assign(filters, next);
  void loadTimeliness(next);
}

function submitSearch(): void {
  updateFilters({ page: 1 });
}

function clearSearch(): void {
  searchDraft.value = "";
  updateFilters({ page: 1 });
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

function changePage(page: number): void {
  if (page !== filters.page) updateFilters({ page });
}

async function copyValue(value: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    message.success(`已复制：${value}`);
  } catch {
    message.error("复制失败");
  }
}

function channelClass(channel: Channel): string {
  return channel === "FBP" ? "timeliness-channel-tag--fbp" : channel === "realFBS" ? "timeliness-channel-tag--fbs" : "timeliness-channel-tag--whd";
}

function renderChannelTag(channel: Channel): VNodeChild {
  return h(NTag, {
    bordered: false,
    round: true,
    size: "small",
    type: "default",
    class: `timeliness-channel-tag ${channelClass(channel)}`,
  }, { default: () => channel });
}

function renderGroupIdentity(row: TimelinessGroup): VNodeChild {
  return h("div", { class: "timeliness-identity-cell" }, [
    h("strong", { class: "timeliness-shop-name" }, row.shop_name),
    renderChannelTag(row.channel),
  ]);
}

function renderCompletenessChip(label: string, value: number, warning: boolean): VNodeChild {
  return h(NTag, {
    bordered: false,
    round: true,
    size: "small",
    type: warning ? "warning" : "default",
    class: `timeliness-complete-chip${warning ? " is-warning" : ""}`,
  }, {
    default: () => [h("span", { class: "timeliness-sub-label" }, label), h("b", formatPercent(value))],
  });
}

function renderCompleteness(row: TimelinessGroup): VNodeChild {
  return h("div", { class: "timeliness-completeness-cell" }, [
    h("span", { class: "timeliness-complete-total" }, [
      "有效订单 ",
      h("b", formatInteger(row.orders)),
      " 单",
    ]),
    h("div", { class: "timeliness-complete-chips" }, [
      renderCompletenessChip("创建", row.created_completeness, false),
      renderCompletenessChip("发货", row.shipped_completeness, row.shipped_completeness < 0.8),
      renderCompletenessChip("签收", row.delivered_completeness, row.delivered_completeness < 0.8),
    ]),
  ]);
}

function shipTagType(value: number | null): TagType {
  return value != null && value <= 24 ? "success" : value != null && value <= 48 ? "warning" : "error";
}

function renderStatCell(
  samples: number,
  insufficient: boolean,
  p50: number | null,
  average: number | null,
  p90: number | null,
  type: "ship" | "delivery",
): VNodeChild {
  if (!samples) {
    return h("div", { class: "timeliness-stat-empty" }, [
      h(MorphIcon, { icon: "clock", size: "13", strokeWidth: "1.8" }),
      h("span", "暂无有效样本"),
    ]);
  }
  const p50Tag = h(NTag, {
    bordered: false,
    round: true,
    size: "small",
    type: type === "ship" ? shipTagType(p50) : "info",
    class: "timeliness-p50-tag",
  }, {
    default: () => [
      h(MorphIcon, { icon: "clock", size: "12", strokeWidth: "2.2" }),
      h("b", "P50"),
      ` ${formatHours(p50)}`,
    ],
  });
  const sampleTag = insufficient
    ? h(NTag, { bordered: false, round: true, size: "small", type: "warning", class: "timeliness-sample-tag" }, {
        default: () => [h(MorphIcon, { icon: "alertTriangle", size: "11", strokeWidth: "2" }), "样本不足"],
      })
    : h("span", { class: "timeliness-sample-text" }, `样本 ${formatInteger(samples)}`);
  return h("div", { class: "timeliness-stat-wrap" }, [
    h("div", { class: "timeliness-p50-row" }, [p50Tag, sampleTag]),
    h("div", { class: "timeliness-sub-stats" }, [
      h("span", ["平均 ", h("b", formatHours(average))]),
      h("span", { class: "timeliness-p90-stat" }, ["P90 ", h("b", formatHours(p90))]),
    ]),
  ]);
}

function renderDetailTime(row: TimelinessItem, type: "ship" | "delivery"): VNodeChild {
  const value = type === "ship" ? row.shipped_at : row.delivered_at;
  const duration = type === "ship" ? row.ship_hours : row.delivery_hours;
  const anomaly = type === "ship" ? row.ship_anomaly : row.delivery_anomaly;
  if (anomaly) {
    return h("div", { class: "timeliness-time-cell" }, [
      h("strong", { class: "timeliness-time-value" }, value ? formatBeijingDateTime(value) : "—"),
      h(NTag, { bordered: false, round: true, size: "small", type: "error", class: "timeliness-time-tag" }, {
        default: () => [h(MorphIcon, { icon: "alertTriangle", size: "11", strokeWidth: "2" }), "数据异常"],
      }),
    ]);
  }
  if (!value) {
    return h("div", { class: "timeliness-time-cell" }, h("span", { class: "timeliness-empty-time" },
      type === "ship" ? "待发货 / 暂无出库记录" : "运输中 / 暂无签收记录"));
  }
  const tagType = type === "ship" ? shipTagType(duration) : duration != null && duration <= 120 ? "info" : "warning";
  const icon = type === "ship" ? duration != null && duration <= 24 ? "zap" : "clock" : duration != null && duration <= 120 ? "zap" : "clock";
  return h("div", { class: "timeliness-time-cell" }, [
    h("strong", { class: "timeliness-time-value" }, formatBeijingDateTime(value)),
    h(NTag, { bordered: false, round: true, size: "small", type: tagType, class: "timeliness-time-tag" }, {
      default: () => [h(MorphIcon, { icon, size: "11", strokeWidth: "2" }), `耗时 ${formatHours(duration)}`],
    }),
  ]);
}

function renderOrderNumber(row: TimelinessItem): VNodeChild {
  return h("button", {
    type: "button",
    class: "timeliness-copy-value",
    title: "点击复制订单号",
    onClick: () => { void copyValue(row.posting_number); },
  }, [
    h(MorphIcon, { icon: "copy", size: "12", strokeWidth: "2" }),
    row.posting_number,
  ]);
}

const groupColumns: DataTableColumns<TimelinessGroup> = [
  { key: "identity", title: "店铺与履约渠道", minWidth: 160, render: renderGroupIdentity },
  { key: "completeness", title: "订单量与完整率", minWidth: 230, render: renderCompleteness },
  {
    key: "ship",
    title: "发货出库时效（创建 → 发货）",
    minWidth: 280,
    render: (row) => renderStatCell(row.ship_samples, row.ship_sample_insufficient, row.p50_ship_hours, row.avg_ship_hours, row.p90_ship_hours, "ship"),
  },
  {
    key: "delivery",
    title: "在途配送时效（发货 → 签收）",
    minWidth: 280,
    render: (row) => renderStatCell(row.delivery_samples, row.delivery_sample_insufficient, row.p50_delivery_hours, row.avg_delivery_hours, row.p90_delivery_hours, "delivery"),
  },
];

const detailColumns: DataTableColumns<TimelinessItem> = [
  {
    key: "identity",
    title: "店铺／渠道",
    width: 150,
    render: (row) => h("div", { class: "timeliness-detail-identity" }, [
      h("strong", { class: "timeliness-shop-badge" }, row.shop_name),
      renderChannelTag(row.channel),
    ]),
  },
  { key: "posting_number", title: "订单号", minWidth: 200, render: renderOrderNumber },
  { key: "created_at", title: "订购时间", width: 180, render: (row) => h("span", { class: "timeliness-cell-time" }, formatBeijingDateTime(row.created_at)) },
  { key: "ship", title: "实际发货／出库耗时", minWidth: 240, render: (row) => renderDetailTime(row, "ship") },
  { key: "delivery", title: "实际签收／在途耗时", minWidth: 240, render: (row) => renderDetailTime(row, "delivery") },
];

watch(() => route.fullPath, () => {
  if (!routeReady) return;
  const next = applyRouteQuery(route.query, 0);
  void loadTimeliness(next);
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
    void loadTimeliness(next);
  }
});

onBeforeUnmount(() => {
  requestId += 1;
});
</script>

<template>
  <section class="timeliness-view">
    <div class="analytics-toolbar timeliness-toolbar">
      <div class="timeliness-date-control analytics-date-control">
        <span>统计日期</span>
        <NDatePicker
          :formatted-value="dateRange"
          type="daterange"
          value-format="yyyy-MM-dd"
          separator="至"
          :clearable="false"
          class="analytics-date-picker"
          aria-label="发货与配送时效日期范围"
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
      <div class="analytics-toolbar-foot timeliness-toolbar-foot">
        <span>订单按创建时间、北京时间自然日筛选；统计口径由后端返回</span>
        <span class="analytics-data-through">
          <span class="analytics-data-dot" aria-hidden="true" />数据截止
          <strong>{{ data?.data_through ? formatBeijingDateTime(data.data_through) : "暂无" }}</strong>
        </span>
      </div>
    </div>

    <NAlert v-if="error" type="error" class="analytics-error timeliness-error" :title="error">
      <div class="analytics-error-content">
        <span>时效统计未更新，请重试。</span>
        <NButton size="small" @click="retry">重试</NButton>
      </div>
    </NAlert>

    <div v-if="summaryKpis.length" class="analytics-kpi-grid timeliness-kpi-grid">
      <NCard
        v-for="kpi in summaryKpis"
        :key="kpi.label"
        :bordered="false"
        class="analytics-kpi-card timeliness-kpi-card"
        :class="`analytics-tone-${kpi.tone}`"
      >
        <div class="analytics-kpi-head">
          <span class="timeliness-kpi-label">
            <span>{{ kpi.label }}</span>
            <NTag v-if="kpi.badge" size="small" round :bordered="false" type="default">{{ kpi.badge }}</NTag>
          </span>
          <span class="analytics-icon-badge"><morph-icon :icon="kpi.icon" size="18" stroke-width="1.8" /></span>
        </div>
        <strong class="analytics-kpi-value">{{ kpi.value }}</strong>
        <small>{{ kpi.note }}</small>
      </NCard>
    </div>

    <NCard :bordered="false" class="analytics-table-card timeliness-table-card timeliness-matrix-card">
      <template #header>
        <div class="analytics-panel-heading">
          <div>
            <h2><morph-icon icon="clock" size="18" stroke-width="1.8" />店铺与渠道时效矩阵</h2>
            <span>统计发货出库与在途配送耗时的中位数(P50)及尾部时效(P90)</span>
          </div>
          <span v-if="loading" class="analytics-loading-label">时效统计加载中…</span>
        </div>
      </template>
      <NDataTable
        class="analytics-table timeliness-matrix-table"
        :columns="groupColumns"
        :data="data?.groups ?? []"
        :loading="loading"
        :pagination="false"
        :remote="true"
        :scroll-x="950"
      >
        <template #empty><NEmpty :description="error ? '时效统计加载失败' : '当前范围内暂无有效订单'" /></template>
      </NDataTable>
    </NCard>

    <NCard :bordered="false" class="analytics-table-card timeliness-table-card timeliness-detail-card">
      <template #header>
        <div class="timeliness-detail-header">
          <div class="analytics-panel-heading">
            <div>
              <h2><morph-icon icon="truck" size="18" stroke-width="1.8" />订单时效明细</h2>
              <span>仅支持按订单号筛选，点击订单号可直接复制</span>
            </div>
          </div>
          <form class="timeliness-detail-filter" role="search" @submit.prevent="submitSearch">
            <NInput
              v-model:value="searchDraft"
              type="text"
              class="timeliness-search-input"
              aria-label="搜索时效订单号"
              placeholder="输入完整或部分订单号…"
              @keydown.enter.prevent="submitSearch"
            >
              <template #prefix><morph-icon icon="search" size="15" stroke-width="1.8" /></template>
            </NInput>
            <NButton type="primary" attr-type="submit" :loading="loading">
              <template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>
              查询
            </NButton>
            <NButton attr-type="button" @click="clearSearch">清除</NButton>
          </form>
        </div>
      </template>
      <NDataTable
        class="analytics-table timeliness-detail-table"
        :columns="detailColumns"
        :data="data?.items ?? []"
        :loading="loading"
        :pagination="false"
        :remote="true"
        :scroll-x="980"
      >
        <template #empty><NEmpty :description="error ? '订单时效加载失败' : '没有匹配的订单时效明细'" /></template>
      </NDataTable>
      <div class="analytics-pager timeliness-pager">
        <span>第 {{ filters.page }} / {{ pageCount }} 页，共 {{ formatInteger(data?.total) }} 条</span>
        <NPagination
          :page="filters.page"
          :page-count="pageCount"
          :page-size="PAGE_SIZE"
          :disabled="loading"
          :page-slot="7"
          @update:page="changePage"
        />
      </div>
    </NCard>
  </section>
</template>
