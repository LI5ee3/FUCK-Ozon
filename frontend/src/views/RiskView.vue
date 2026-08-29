<script setup lang="ts">
import "./analytics.css";
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch, type VNode, type VNodeChild } from "vue";
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
  NSpin,
  NTag,
  useMessage,
} from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { getErrorMessage } from "../api/client";
import { getRisk, getRiskReasons } from "../api/risk";
import { useShop } from "../composables/useShop";
import type {
  Channel,
  RiskItem,
  RiskReasonDetail,
  RiskReasonRow,
  RiskReasonStats,
  RiskReasonsResponse,
  RiskResponse,
  RiskStats,
  ShopSelection,
} from "../types/api";
import { beijingToday, parseValidDateRange, shiftDays, subtractMonths, type DateRange } from "../utils/date";
import { formatInteger } from "../utils/format";
import { isShopSelection, queryValue } from "../utils/query";

type DatePreset = "today" | "3days" | "7days" | "3months" | "all";
type RiskFilters = {
  shopId: ShopSelection;
  search: string;
  highOnly: boolean;
  from: string;
  to: string;
};
type RiskKpi = {
  icon: IconName;
  label: string;
  value: string;
  badge?: string;
  note: string;
  tone: "azure" | "lavender" | "mint" | "peach" | "blue";
};

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
const filters = reactive<RiskFilters>(initialFilters);
const searchDraft = ref(initialFilters.search);
const riskData = ref<RiskResponse | null>(null);
const reasonData = ref<RiskReasonsResponse | null>(null);
const selectedReason = ref<string | null>(null);
const detailRows = ref<RiskReasonDetail[] | null>(null);
const loading = ref(false);
const error = ref("");
const detailLoading = ref(false);
const detailError = ref("");
let requestId = 0;
let detailRequestId = 0;
let routeReady = false;
let loadedApiFilters: Pick<RiskFilters, "shopId" | "from" | "to"> | null = null;
let ignoreNextShopChange = false;

const dateRange = computed<DateRange>(() => [filters.from, filters.to]);
const activePreset = computed<DatePreset | "">(() => {
  for (const preset of datePresets) {
    const [from, to] = presetRange(preset.key);
    if (filters.from === from && filters.to === to) return preset.key;
  }
  return "";
});
const visibleItems = computed(() => {
  const keyword = searchDraft.value.trim().toLocaleLowerCase();
  return (riskData.value?.items ?? []).filter((row) => {
    const text = (row.search_text || "") + " " + (row.product_name || "");
    const matchesSearch = !keyword || text.toLocaleLowerCase().includes(keyword);
    return matchesSearch && (!filters.highOnly || (row.total.cancelled_rate ?? 0) >= 0.15);
  });
});
const matrixEmptyDescription = computed(() => {
  if (error.value) return "风险数据加载失败";
  if (searchDraft.value.trim() || filters.highOnly) return "没有匹配的SKU或高危商品";
  return "当前范围内暂无有效货件";
});
const reasonEmptyDescription = computed(() => error.value ? "取消原因加载失败" : "当前范围内暂无发货后取消原因");
const selectedReasonName = computed(() => {
  const row = reasonData.value?.items.find((item) => item.reason_raw === selectedReason.value);
  return row?.reason_name ?? selectedReason.value ?? "";
});
const summaryKpis = computed<RiskKpi[]>(() => {
  const summary = riskData.value?.summary;
  if (!summary) return [];
  const hasSamples = summary.valid > 0;
  return [
    {
      icon: "package",
      label: "有效货件数",
      value: formatInteger(summary.valid) + " 件",
      note: "当前筛选范围内的全部有效货件",
      tone: "azure",
    },
    {
      icon: "alertTriangle",
      label: "发货后取消",
      value: hasSamples ? formatInteger(summary.cancelled) + " 件" : "数据不足",
      badge: hasSamples ? formatRiskRate(summary.cancelled_rate) + " 取消率" : undefined,
      note: "发货后在途或配送阶段取消",
      tone: "peach",
    },
    {
      icon: "userX",
      label: "买家未取货",
      value: hasSamples ? formatInteger(summary.unclaimed) + " 件" : "数据不足",
      badge: hasSamples ? formatRiskRate(summary.unclaimed_rate) + " 发生率" : undefined,
      note: "5 种买家原因导致的未完成收货",
      tone: "lavender",
    },
    {
      icon: "shieldAlert",
      label: "通关失败",
      value: hasSamples ? formatInteger(summary.customs) + " 件" : "数据不足",
      badge: hasSamples ? formatRiskRate(summary.customs_rate) + " 拦截率" : undefined,
      note: "海关查验未通过导致的退运拦截",
      tone: "blue",
    },
  ];
});

function defaultDateRange(): DateRange {
  const today = beijingToday();
  return [subtractMonths(today, 3), today];
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): RiskFilters {
  const shop = queryValue(query, "shop_id");
  const [from, to] = parseValidDateRange(queryValue(query, "from"), queryValue(query, "to"), defaultDateRange());
  return {
    shopId: isShopSelection(shop) ? Number(shop) as ShopSelection : fallbackShop,
    search: queryValue(query, "q").trim(),
    highOnly: queryValue(query, "high") === "1",
    from,
    to,
  };
}

function presetRange(preset: DatePreset): DateRange {
  const today = beijingToday();
  if (preset === "today") return [today, today];
  if (preset === "3days") return [shiftDays(today, -2), today];
  if (preset === "7days") return [shiftDays(today, -6), today];
  if (preset === "3months") return defaultDateRange();
  return ["2020-01-01", today];
}

function queryFor(value: RiskFilters): Record<string, string> {
  const defaultRange = defaultDateRange();
  const query: Record<string, string> = { shop_id: String(value.shopId) };
  if (value.search.trim()) query.q = value.search.trim();
  if (value.highOnly) query.high = "1";
  if (value.from !== defaultRange[0] || value.to !== defaultRange[1]) {
    query.from = value.from;
    query.to = value.to;
  }
  return query;
}

function queryMatches(query: LocationQuery, value: RiskFilters): boolean {
  const expected = queryFor(value);
  const keys = new Set([...Object.keys(query), ...Object.keys(expected)]);
  return [...keys].every((key) => queryValue(query, key) === (expected[key] ?? ""));
}

function applyRouteQuery(query: LocationQuery, fallbackShop: ShopSelection): RiskFilters {
  const next = parseFilters(query, fallbackShop);
  Object.assign(filters, next);
  searchDraft.value = next.search;
  if (selectedShopId.value !== next.shopId) {
    ignoreNextShopChange = true;
    selectShop(next.shopId);
  }
  return next;
}

function updateRoute(next: RiskFilters, replace = false): void {
  const normalized = { ...next, search: next.search.trim() };
  Object.assign(filters, normalized);
  searchDraft.value = normalized.search;
  if (queryMatches(route.query, normalized)) {
    void loadRisk(normalized);
    return;
  }
  void (replace ? router.replace({ query: queryFor(normalized) }) : router.push({ query: queryFor(normalized) }));
}

function currentFilters(): RiskFilters {
  const next = { ...filters, search: searchDraft.value };
  if (!queryValue(route.query, "from") && !queryValue(route.query, "to")) {
    [next.from, next.to] = defaultDateRange();
  }
  return next;
}

function updateFilters(overrides: Partial<RiskFilters>, replace = false): void {
  updateRoute({ ...currentFilters(), ...overrides }, replace);
}

async function loadRisk(queryFilters: RiskFilters): Promise<void> {
  loadedApiFilters = { shopId: queryFilters.shopId, from: queryFilters.from, to: queryFilters.to };
  const currentRequest = ++requestId;
  detailRequestId += 1;
  selectedReason.value = null;
  detailRows.value = null;
  detailError.value = "";
  detailLoading.value = false;
  loading.value = true;
  error.value = "";
  riskData.value = null;
  reasonData.value = null;
  try {
    const [risk, reasons] = await Promise.all([
      getRisk({ shopId: queryFilters.shopId, from: queryFilters.from, to: queryFilters.to }),
      getRiskReasons({ shopId: queryFilters.shopId, from: queryFilters.from, to: queryFilters.to }),
    ]);
    if (currentRequest !== requestId) return;
    riskData.value = risk;
    reasonData.value = reasons;
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
  void loadRisk(next);
}

function submitSearch(): void {
  updateFilters({ search: searchDraft.value });
}

function handleSearchInput(value: string): void {
  updateRoute({ ...filters, search: value }, true);
}

function toggleHighRisk(): void {
  updateFilters({ highOnly: !filters.highOnly });
}

function handleDateRangeChange(value: string | DateRange | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  const [from, to] = parseValidDateRange(value[0], value[1], defaultDateRange());
  if (from !== value[0] || to !== value[1]) return;
  updateFilters({ from, to });
}

function selectPreset(preset: DatePreset): void {
  const [from, to] = presetRange(preset);
  updateFilters({ from, to });
}

function formatRiskRate(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return (value * 100).toFixed(2) + "%";
}

function rateTone(value: number | null): "safe" | "warning" | "danger" {
  return value != null && value >= 0.15 ? "danger" : value != null && value >= 0.05 ? "warning" : "safe";
}

function rateIcon(value: number | null): IconName {
  return value != null && value >= 0.15 ? "alertTriangle" : value != null && value >= 0.05 ? "alertCircle" : "check";
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
    message.success("已复制：" + value);
  } catch {
    message.error("复制失败");
  }
}

function channelClass(channel: Channel): string {
  return channel === "FBP" ? "risk-channel-tag--fbp" : channel === "realFBS" ? "risk-channel-tag--fbs" : "risk-channel-tag--whd";
}

function renderChannelHeader(label: string, channel?: Channel): VNode {
  return h("span", { class: "risk-channel-tag " + (channel ? channelClass(channel) : "risk-channel-tag--neutral") }, label);
}

function renderRiskIdentity(row: RiskItem): VNodeChild {
  const meta: VNodeChild[] = [h("span", { class: "risk-shop-badge" }, row.shop_name)];
  if (row.primary_offer_id) {
    meta.push(h("button", {
      type: "button",
      class: "risk-offer-badge",
      title: "点击复制主货号",
      onClick: (event: MouseEvent) => {
        event.stopPropagation();
        void copyValue(row.primary_offer_id as string);
      },
    }, [h(MorphIcon, { icon: "gitMerge", size: "11", strokeWidth: "2" }), "主货号 ", h("b", row.primary_offer_id)]));
    meta.push(h("span", { class: "risk-member-badge" }, formatInteger(row.member_count) + " 个成员"));
  } else {
    meta.push(h("span", { class: "risk-sku-badge" }, [h(MorphIcon, { icon: "tag", size: "11", strokeWidth: "1.8" }), "SKU ", h("b", row.sku || "—")]));
  }
  return h("div", { class: "risk-product-cell" }, [
    h("strong", { class: "risk-product-name", title: row.product_name || "商品名称暂无" }, row.product_name || "商品名称暂无"),
    h("div", { class: "risk-product-meta" }, meta),
  ]);
}

function renderRiskStats(label: string, stats: RiskStats | null): VNodeChild {
  if (!stats || !stats.valid) {
    return h("div", { class: "risk-stat-empty-cell" }, [
      h("strong", { class: "risk-cell-title" }, label),
      h("span", "— 无有效样本 —"),
    ]);
  }
  const tone = rateTone(stats.cancelled_rate);
  return h("div", { class: "risk-stat-cell risk-stat-cell--" + tone }, [
    h("strong", { class: "risk-cell-title" }, label),
    h("span", { class: "risk-valid-count" }, ["有效 ", h("b", formatInteger(stats.valid)), " 件"]),
    h("span", { class: "risk-rate-pill risk-rate-pill--" + tone }, [
      h(MorphIcon, { icon: rateIcon(stats.cancelled_rate), size: "11", strokeWidth: "2.2" }),
      h("strong", formatRiskRate(stats.cancelled_rate)),
      h("small", "(" + formatInteger(stats.cancelled) + "件)"),
    ]),
    h("div", { class: "risk-subtags" }, [
      h("span", { class: "risk-subtag" + (stats.unclaimed > 0 ? " risk-subtag--warning" : "") }, ["未取货 ", h("b", formatRiskRate(stats.unclaimed_rate))]),
      h("span", { class: "risk-subtag" + (stats.customs > 0 ? " risk-subtag--danger" : "") }, ["通关失败 ", h("b", formatRiskRate(stats.customs_rate))]),
    ]),
  ]);
}

function renderReasonIdentity(row: RiskReasonRow): VNodeChild {
  return h("div", { class: "risk-reason-cell" }, [
    h(NButton, {
      text: true,
      type: selectedReason.value === row.reason_raw ? "primary" : "default",
      class: "risk-reason-button" + (selectedReason.value === row.reason_raw ? " is-active" : ""),
      title: "点击展开此原因关联订单",
      onClick: () => { void toggleReason(row.reason_raw); },
    }, {
      default: () => [h(MorphIcon, { icon: "alertTriangle", size: "13", strokeWidth: "2" }), h("span", row.reason_name)],
    }),
    h("span", { class: "risk-reason-raw" }, row.reason_raw),
  ]);
}

function renderReasonStats(label: string, stats: RiskReasonStats): VNodeChild {
  if (!stats.orders && !stats.pieces) {
    return h("div", { class: "risk-reason-stat-empty" }, [h("strong", { class: "risk-cell-title" }, label), h("span", "—")]);
  }
  return h("div", { class: "risk-reason-stat" }, [
    h("strong", { class: "risk-cell-title" }, label),
    h("span", { class: "risk-reason-orders" }, [h("b", formatInteger(stats.orders)), " 单"]),
    h("span", { class: "risk-reason-pieces" }, [h("b", formatInteger(stats.pieces)), " 件"]),
  ]);
}

async function toggleReason(reason: string): Promise<void> {
  if (selectedReason.value === reason && !detailError.value) {
    closeDetails();
    return;
  }
  const currentRequest = ++detailRequestId;
  selectedReason.value = reason;
  detailRows.value = null;
  detailError.value = "";
  detailLoading.value = true;
  try {
    const response = await getRiskReasons({
      shopId: filters.shopId,
      reason,
      from: filters.from,
      to: filters.to,
    });
    if (currentRequest !== detailRequestId) return;
    detailRows.value = response.details;
  } catch (cause) {
    if (currentRequest !== detailRequestId) return;
    detailError.value = getErrorMessage(cause);
    message.error(detailError.value);
  } finally {
    if (currentRequest === detailRequestId) detailLoading.value = false;
  }
}

function closeDetails(): void {
  detailRequestId += 1;
  selectedReason.value = null;
  detailRows.value = null;
  detailError.value = "";
  detailLoading.value = false;
}

const riskColumns: DataTableColumns<RiskItem> = [
  { key: "identity", title: () => renderChannelHeader("商品信息"), minWidth: 300, render: renderRiskIdentity },
  { key: "total", title: () => renderChannelHeader("综合概览"), minWidth: 180, render: (row) => renderRiskStats("综合", row.total) },
  { key: "fbp", title: () => renderChannelHeader("FBP 渠道", "FBP"), minWidth: 180, render: (row) => renderRiskStats("FBP", row.channels.FBP) },
  { key: "realFBS", title: () => renderChannelHeader("realFBS 渠道", "realFBS"), minWidth: 180, render: (row) => renderRiskStats("realFBS", row.channels.realFBS) },
  { key: "WHD", title: () => renderChannelHeader("WHD 渠道", "WHD"), minWidth: 180, render: (row) => renderRiskStats("WHD", row.channels.WHD) },
];

const reasonColumns: DataTableColumns<RiskReasonRow> = [
  { key: "reason", title: () => renderChannelHeader("固定取消原因"), minWidth: 330, render: renderReasonIdentity },
  { key: "total", title: () => renderChannelHeader("综合合计"), minWidth: 170, render: (row) => renderReasonStats("综合", row.total) },
  { key: "FBP", title: () => renderChannelHeader("FBP", "FBP"), minWidth: 150, render: (row) => renderReasonStats("FBP", row.channels.FBP) },
  { key: "realFBS", title: () => renderChannelHeader("realFBS", "realFBS"), minWidth: 150, render: (row) => renderReasonStats("realFBS", row.channels.realFBS) },
  { key: "WHD", title: () => renderChannelHeader("WHD", "WHD"), minWidth: 150, render: (row) => renderReasonStats("WHD", row.channels.WHD) },
];

watch(() => route.fullPath, () => {
  if (!routeReady) return;
  const next = applyRouteQuery(route.query, 0);
  if (!loadedApiFilters || loadedApiFilters.shopId !== next.shopId || loadedApiFilters.from !== next.from || loadedApiFilters.to !== next.to) {
    void loadRisk(next);
  }
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
  if (!queryMatches(route.query, next)) {
    void router.replace({ query: queryFor(next) });
  } else {
    void loadRisk(next);
  }
});

onBeforeUnmount(() => {
  requestId += 1;
  detailRequestId += 1;
});
</script>

<template>
  <section class="risk-view">
    <form class="analytics-toolbar risk-toolbar" @submit.prevent="submitSearch">
      <div class="risk-toolbar-row">
        <NInput
          v-model:value="searchDraft"
          class="risk-search-input"
          type="text"
          aria-label="筛选SKU风险矩阵"
          placeholder="搜索SKU、货号或商品名称…"
          @update:value="handleSearchInput"
          @keydown.enter.prevent="submitSearch"
        >
          <template #prefix><morph-icon icon="search" size="15" stroke-width="1.8" /></template>
        </NInput>
        <div class="analytics-date-control risk-date-control">
          <span>统计日期</span>
          <NDatePicker
            :formatted-value="dateRange"
            type="daterange"
            value-format="yyyy-MM-dd"
            separator="至"
            :clearable="false"
            class="analytics-date-picker"
            aria-label="订单取消分析日期范围"
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
        <div class="risk-filter-actions">
          <NButton
            attr-type="button"
            size="small"
            :type="filters.highOnly ? 'error' : 'default'"
            :secondary="!filters.highOnly"
            :aria-pressed="filters.highOnly"
            @click="toggleHighRisk"
          >
            <template #icon><morph-icon icon="zap" size="13" stroke-width="2" /></template>
            仅看高危 (≥15%)
          </NButton>
        </div>
      </div>
    </form>

    <NAlert v-if="error" type="error" class="analytics-error" :title="error">
      <div class="analytics-error-content">
        <span>风险数据未更新，请重试。</span>
        <NButton size="small" @click="retry">重试</NButton>
      </div>
    </NAlert>

    <div v-if="riskData" class="analytics-kpi-grid risk-kpi-grid">
      <NCard
        v-for="kpi in summaryKpis"
        :key="kpi.label"
        :bordered="false"
        class="analytics-kpi-card"
        :class="'analytics-tone-' + kpi.tone"
      >
        <div class="analytics-kpi-head">
          <span>{{ kpi.label }}</span>
          <span class="analytics-icon-badge"><morph-icon :icon="kpi.icon" size="18" stroke-width="1.8" /></span>
        </div>
        <strong class="analytics-kpi-value">{{ kpi.value }}</strong>
        <small v-if="kpi.badge" class="risk-kpi-badge">{{ kpi.badge }}</small>
        <small>{{ kpi.note }}</small>
      </NCard>
    </div>

    <NCard :bordered="false" class="analytics-table-card risk-panel">
      <template #header>
        <div class="analytics-panel-heading">
          <div>
            <h2><morph-icon icon="shieldAlert" size="18" stroke-width="1.8" />SKU 风险矩阵</h2>
            <span>买家未取货率表示因指定买家原因导致的未完成收货；全局应用主货号合并</span>
          </div>
          <span v-if="loading" class="analytics-loading-label">风险数据加载中…</span>
        </div>
      </template>
      <NDataTable
        class="analytics-table risk-table"
        :columns="riskColumns"
        :data="visibleItems"
        :loading="loading"
        :pagination="false"
        :remote="true"
        :scroll-x="1000"
      >
        <template #empty><NEmpty :description="matrixEmptyDescription" /></template>
      </NDataTable>
    </NCard>

    <NCard :bordered="false" class="analytics-table-card risk-panel">
      <template #header>
        <div class="analytics-panel-heading">
          <div>
            <h2><morph-icon icon="alertTriangle" size="18" stroke-width="1.8" />平台固定取消原因</h2>
            <span>仅统计发货后取消；点击原因查看对应订单明细</span>
          </div>
          <span v-if="loading" class="analytics-loading-label">取消原因加载中…</span>
        </div>
      </template>
      <NDataTable
        class="analytics-table risk-reason-table"
        :columns="reasonColumns"
        :data="reasonData?.items ?? []"
        :loading="loading"
        :pagination="false"
        :remote="true"
        :scroll-x="930"
      >
        <template #empty><NEmpty :description="reasonEmptyDescription" /></template>
      </NDataTable>

      <div v-if="selectedReason" class="risk-reason-details">
        <div class="risk-reason-detail-header">
          <div class="risk-reason-detail-title">
            <morph-icon icon="alertTriangle" size="15" stroke-width="2" />
            <h3>{{ selectedReasonName }} · 关联订单明细</h3>
          </div>
          <div class="risk-reason-detail-actions">
            <span>共 <b>{{ detailRows ? formatInteger(detailRows.length) : "—" }}</b> 个异常订单</span>
            <NButton text circle size="small" aria-label="关闭明细" title="关闭明细" @click="closeDetails">
              <template #icon><morph-icon icon="x" size="14" stroke-width="2" /></template>
            </NButton>
          </div>
        </div>
        <NAlert v-if="detailError" type="error" class="analytics-detail-error" :title="detailError">
          <NButton size="small" @click="toggleReason(selectedReason)">重试</NButton>
        </NAlert>
        <div v-if="detailLoading" class="risk-detail-loading">
          <NSpin size="small" />
          <span>原因对应订单加载中…</span>
        </div>
        <div v-else-if="detailRows?.length" class="risk-detail-grid">
          <article v-for="row in detailRows" :key="row.shop_id + ':' + row.posting_number" class="risk-detail-card">
            <button type="button" class="risk-detail-order" title="点击复制订单号" @click="copyValue(row.posting_number)">
              <morph-icon icon="copy" size="12" stroke-width="2" />
              {{ row.posting_number }}
            </button>
            <div class="risk-detail-meta">
              <span class="risk-shop-badge">{{ row.shop_name }}</span>
              <NTag bordered round size="small" :class="'risk-channel-tag ' + channelClass(row.channel)">{{ row.channel }}</NTag>
              <span class="risk-detail-pieces">× <b>{{ formatInteger(row.pieces) }}</b> 件</span>
            </div>
          </article>
        </div>
        <NEmpty v-else description="当前时间范围内没有对应订单。" />
      </div>
    </NCard>
  </section>
</template>
