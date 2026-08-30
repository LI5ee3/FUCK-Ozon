<script setup lang="ts">
import "../../styles/analytics.css";
import "./returns.css";
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch, type VNodeChild } from "vue";
import ReturnsKpiCards from "./components/ReturnsKpiCards.vue";
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
  NEmpty,
  NInput,
  NTag,
  useMessage,
} from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { getErrorMessage } from "../../shared/api/client";
import { listRfbsReturns, listReturns } from "./api";
import { useShop } from "../../shared/composables/useShop";
import type {
  ReturnDeadlineStatus,
  ReturnRecord,
  ReturnsResponse,
  RfbsReturnRecord,
  RfbsReturnsResponse,
} from "./types";
import type { ShopSelection } from "../../shared/types/common";
import { formatBeijingDateTime, formatInteger, formatMoney, formatNumber } from "../../shared/utils/format";
import { beijingThreeMonthRange, parseValidDateRange, standardDatePresetRange, type DateRange, type StandardDatePreset } from "../../shared/utils/date";
import { positiveInteger, queryMatches, queryValue, shopSelectionFromQuery } from "../../shared/utils/query";
import { copyText } from "../../shared/utils/clipboard";

type DatePreset = StandardDatePreset;
type ReturnTab = "cancel" | "rfbs";
type ReturnsFilters = {
  shopId: ShopSelection;
  from: string;
  to: string;
  tab: ReturnTab;
  search: string;
  page: number;
};
type ApiBase = Pick<ReturnsFilters, "shopId" | "from" | "to">;
type TagType = "default" | "info" | "success" | "warning" | "error";
type ReturnsKpi = {
  icon: IconName;
  label: string;
  value: string;
  badge: string;
  note: string;
  tone: "azure" | "lavender" | "mint" | "peach" | "blue";
};

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
const filters = reactive<ReturnsFilters>(initialFilters);
const tabSearches = reactive<Record<ReturnTab, string>>({
  cancel: initialFilters.tab === "cancel" ? initialFilters.search : "",
  rfbs: initialFilters.tab === "rfbs" ? initialFilters.search : "",
});
const tabPages = reactive<Record<ReturnTab, number>>({
  cancel: initialFilters.tab === "cancel" ? initialFilters.page : 1,
  rfbs: initialFilters.tab === "rfbs" ? initialFilters.page : 1,
});
const searchDraft = ref(initialFilters.search);
const cancelData = ref<ReturnsResponse | null>(null);
const rfbsData = ref<RfbsReturnsResponse | null>(null);
const cancelLoading = ref(false);
const rfbsLoading = ref(false);
const cancelError = ref("");
const rfbsError = ref("");
let cancelRequestId = 0;
let rfbsRequestId = 0;
let routeReady = false;
let ignoreNextShopChange = false;
let loadedApiBase: ApiBase | null = null;

const dateRange = computed<DateRange>(() => [filters.from, filters.to]);
const activePreset = computed<DatePreset | "">(() => {
  for (const preset of datePresets) {
    const [from, to] = standardDatePresetRange(preset.key);
    if (filters.from === from && filters.to === to) return preset.key;
  }
  return "";
});
const cancelPageCount = computed(() => pageCountFor(cancelData.value));
const rfbsPageCount = computed(() => pageCountFor(rfbsData.value));
const activeDataThrough = computed(() => filters.tab === "cancel"
  ? cancelData.value?.data_through ?? null
  : rfbsData.value?.data_through ?? null);
const cancelKpis = computed<ReturnsKpi[]>(() => {
  const summary = cancelData.value?.summary;
  if (!summary) return [];
  const quantity = summary.shops.reduce((total, shop) => total + (shop.quantity || 0), 0);
  return [
    {
      icon: "xCircle",
      label: "取消总记录数",
      value: `${formatInteger(summary.records)} 条`,
      badge: "全量取消",
      note: "当前店铺与筛选范围内的取消单量",
      tone: "peach",
    },
    {
      icon: "box",
      label: "取消商品总件数",
      value: `${formatInteger(quantity)} 件`,
      badge: "商品件数",
      note: "所有取消记录中的商品累计件数",
      tone: "lavender",
    },
    ...summary.shops.map((shop): ReturnsKpi => ({
      icon: "shoppingBag",
      label: `${shop.shop_name} 取消`,
      value: `${formatInteger(shop.records)} 条 / ${formatInteger(shop.quantity)} 件`,
      badge: "分店铺",
      note: `${shop.shop_name} 的取消单量与商品件数`,
      tone: "blue" as const,
    })),
  ];
});
const rfbsKpis = computed<ReturnsKpi[]>(() => {
  const summary = rfbsData.value?.summary;
  if (!summary) return [];
  return [
    {
      icon: "rotateCcw",
      label: "退货申请总数",
      value: `${formatInteger(summary.records)} 条`,
      badge: "rFBS 退货",
      note: "包含有效申请编号的退货申请单",
      tone: "lavender",
    },
    ...summary.shops.map((shop): ReturnsKpi => ({
      icon: "shoppingBag",
      label: `${shop.shop_name} 退货`,
      value: `${formatInteger(shop.records)} 条申请`,
      badge: "分店铺",
      note: `${shop.shop_name} 的退货申请记录`,
      tone: "blue" as const,
    })),
  ];
});

function isReturnTab(value: string): value is ReturnTab {
  return value === "cancel" || value === "rfbs";
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): ReturnsFilters {
  const tab = queryValue(query, "tab");
  const [from, to] = parseValidDateRange(queryValue(query, "from"), queryValue(query, "to"), beijingThreeMonthRange());
  return {
    shopId: shopSelectionFromQuery(query, fallbackShop),
    from,
    to,
    tab: isReturnTab(tab) ? tab : "cancel",
    search: queryValue(query, "q").trim(),
    page: positiveInteger(queryValue(query, "page"), 1),
  };
}

function queryFor(value: ReturnsFilters): Record<string, string> {
  const defaultRange = beijingThreeMonthRange();
  const query: Record<string, string> = { shop_id: String(value.shopId) };
  const search = value.search.trim();
  if (value.tab === "rfbs") query.tab = value.tab;
  if (search) query.q = search;
  if (value.page !== 1) query.page = String(value.page);
  if (value.from !== defaultRange[0] || value.to !== defaultRange[1]) {
    query.from = value.from;
    query.to = value.to;
  }
  return query;
}

function applyRouteQuery(query: LocationQuery, fallbackShop: ShopSelection): ReturnsFilters {
  const next = parseFilters(query, fallbackShop);
  Object.assign(filters, next);
  tabSearches[next.tab] = next.search;
  tabPages[next.tab] = next.page;
  searchDraft.value = next.search;
  if (selectedShopId.value !== next.shopId) {
    ignoreNextShopChange = true;
    selectShop(next.shopId);
  }
  return next;
}

function updateRoute(next: ReturnsFilters, replace = false): void {
  const normalized = { ...next, search: next.search.trim() };
  Object.assign(filters, normalized);
  tabSearches[normalized.tab] = normalized.search;
  tabPages[normalized.tab] = normalized.page;
  searchDraft.value = normalized.search;
  if (queryMatches(route.query, queryFor(normalized))) {
    void loadActiveTab(normalized);
    return;
  }
  void (replace ? router.replace({ query: queryFor(normalized) }) : router.push({ query: queryFor(normalized) }));
}

function currentFilters(): ReturnsFilters {
  const next = { ...filters, search: searchDraft.value.trim() };
  if (!queryValue(route.query, "from") && !queryValue(route.query, "to")) {
    [next.from, next.to] = beijingThreeMonthRange();
  }
  return next;
}

function updateFilters(overrides: Partial<ReturnsFilters>, replace = false): void {
  updateRoute({ ...currentFilters(), ...overrides }, replace);
}

function baseOf(value: ReturnsFilters): ApiBase {
  return { shopId: value.shopId, from: value.from, to: value.to };
}

function sameBase(left: ApiBase, right: ApiBase): boolean {
  return left.shopId === right.shopId && left.from === right.from && left.to === right.to;
}

function tabRequestFilters(base: ReturnsFilters, tab: ReturnTab): ReturnsFilters {
  return {
    ...base,
    tab,
    search: tabSearches[tab],
    page: tabPages[tab],
  };
}

function pageCountFor(data: { total: number; size: number } | null): number {
  return Math.max(1, Math.ceil((data?.total ?? 0) / (data?.size || PAGE_SIZE)));
}

async function loadReturns(queryFilters: ReturnsFilters): Promise<void> {
  const currentRequest = ++cancelRequestId;
  cancelLoading.value = true;
  cancelError.value = "";
  cancelData.value = null;
  try {
    const data = await listReturns({
      shopId: queryFilters.shopId,
      page: queryFilters.page,
      size: PAGE_SIZE,
      search: queryFilters.search || undefined,
      from: queryFilters.from,
      to: queryFilters.to,
    });
    if (currentRequest !== cancelRequestId) return;
    const pages = pageCountFor(data);
    if (queryFilters.page > pages) {
      tabPages.cancel = pages;
      if (filters.tab === "cancel") {
        await router.replace({ query: queryFor({ ...queryFilters, page: pages }) });
      }
      return;
    }
    cancelData.value = data;
  } catch (cause) {
    if (currentRequest !== cancelRequestId) return;
    cancelError.value = getErrorMessage(cause);
    message.error(cancelError.value);
  } finally {
    if (currentRequest === cancelRequestId) cancelLoading.value = false;
  }
}

async function loadRfbsReturns(queryFilters: ReturnsFilters): Promise<void> {
  const currentRequest = ++rfbsRequestId;
  rfbsLoading.value = true;
  rfbsError.value = "";
  rfbsData.value = null;
  try {
    const data = await listRfbsReturns({
      shopId: queryFilters.shopId,
      page: queryFilters.page,
      size: PAGE_SIZE,
      search: queryFilters.search || undefined,
      from: queryFilters.from,
      to: queryFilters.to,
    });
    if (currentRequest !== rfbsRequestId) return;
    const pages = pageCountFor(data);
    if (queryFilters.page > pages) {
      tabPages.rfbs = pages;
      if (filters.tab === "rfbs") {
        await router.replace({ query: queryFor({ ...queryFilters, page: pages }) });
      }
      return;
    }
    rfbsData.value = data;
  } catch (cause) {
    if (currentRequest !== rfbsRequestId) return;
    rfbsError.value = getErrorMessage(cause);
    message.error(rfbsError.value);
  } finally {
    if (currentRequest === rfbsRequestId) rfbsLoading.value = false;
  }
}

function loadAll(value: ReturnsFilters): void {
  loadedApiBase = baseOf(value);
  void Promise.all([
    loadReturns(tabRequestFilters(value, "cancel")),
    loadRfbsReturns(tabRequestFilters(value, "rfbs")),
  ]);
}

function loadActiveTab(value: ReturnsFilters): Promise<void> {
  return value.tab === "cancel" ? loadReturns(value) : loadRfbsReturns(value);
}

function retryActive(): void {
  const next = currentFilters();
  tabSearches[next.tab] = next.search;
  tabPages[next.tab] = next.page;
  void loadActiveTab(next);
}

function submitSearch(): void {
  updateFilters({ page: 1 });
}

function clearSearch(): void {
  searchDraft.value = "";
  updateFilters({ page: 1 });
}

function resetPages(): void {
  tabPages.cancel = 1;
  tabPages.rfbs = 1;
}

function changeTab(tab: ReturnTab): void {
  if (filters.tab === tab) return;
  updateRoute({ ...filters, tab, search: tabSearches[tab], page: tabPages[tab] });
}

function handleDateRangeChange(value: string | DateRange | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  const [from, to] = parseValidDateRange(value[0], value[1], beijingThreeMonthRange());
  if (from !== value[0] || to !== value[1]) return;
  resetPages();
  updateFilters({ from, to, page: 1 });
}

function selectPreset(preset: DatePreset): void {
  const [from, to] = standardDatePresetRange(preset);
  resetPages();
  updateFilters({ from, to, page: 1 });
}

function changePage(page: number): void {
  if (page === filters.page) return;
  tabPages[filters.tab] = page;
  updateFilters({ page });
}

async function copyValue(value: string): Promise<void> {
  try {
    await copyText(value);
    message.success(`已复制：${value}`);
  } catch {
    message.error("复制失败");
  }
}

function display(value: string | null | undefined, fallback = "—"): string {
  return value && value.trim() ? value : fallback;
}

function renderCopyButton(
  value: string | null | undefined,
  title: string,
  className = "",
  label = value || "",
  withIcon = true,
): VNodeChild {
  if (!value || !value.trim()) return h("span", { class: `returns-missing ${className}` }, "—");
  return h("button", {
    type: "button",
    class: `returns-copy-value ${className}`,
    title,
    onClick: (event: MouseEvent) => {
      event.stopPropagation();
      void copyValue(value);
    },
  }, withIcon ? [h(MorphIcon, { icon: "copy", size: "12", strokeWidth: "2" }), label] : label);
}

function renderMetaButton(label: string, value: string | null, title: string): VNodeChild {
  if (!value || !value.trim()) {
    return h("span", { class: "returns-meta-chip returns-meta-chip--empty" }, [label, " ", h("b", "—")]);
  }
  return h("button", {
    type: "button",
    class: "returns-meta-chip",
    title,
    onClick: (event: MouseEvent) => {
      event.stopPropagation();
      void copyValue(value);
    },
  }, [label, " ", h("b", value)]);
}

function renderProductCell(row: { product_name: string | null; sku: string | null; offer_id: string | null }): VNodeChild {
  return h("div", { class: "returns-product-cell" }, [
    h("strong", { class: "returns-product-title", title: display(row.product_name, "商品信息暂无") }, display(row.product_name, "商品信息暂无")),
    h("div", { class: "returns-product-meta" }, [
      renderMetaButton("SKU", row.sku, "点击复制 SKU"),
      renderMetaButton("货号", row.offer_id, "点击复制货号"),
    ]),
  ]);
}

function renderDeadline(row: { complaint_deadline: string | null; complaint_deadline_status: ReturnDeadlineStatus }): VNodeChild {
  if (!row.complaint_deadline && !row.complaint_deadline_status) return null;
  const status = row.complaint_deadline_status || "missing";
  const labels: Partial<Record<ReturnDeadlineStatus, string>> = {
    overdue: "已逾期",
    due_today: "今日截止",
    due_soon: "即将截止",
  };
  return h("span", { class: `returns-deadline returns-deadline--${status}` }, [
    h(MorphIcon, { icon: status === "overdue" ? "alertCircle" : "clock", size: "11", strokeWidth: "2" }),
    h("span", `投诉截止：${row.complaint_deadline || "—"}`),
    labels[status] ? h("b", labels[status]) : null,
  ]);
}

function renderReturnTime(row: Pick<ReturnRecord, "shop_name" | "cancelled_at" | "occurred_at" | "complaint_deadline" | "complaint_deadline_status">): VNodeChild {
  return h("div", { class: "returns-shop-time" }, [
    h("span", { class: "returns-shop-badge" }, display(row.shop_name)),
    h("span", { class: "returns-time-value" }, formatBeijingDateTime(row.cancelled_at || row.occurred_at)),
    renderDeadline(row),
  ]);
}

function renderCancelReason(row: ReturnRecord): VNodeChild {
  return h("div", { class: "returns-reason-cell" }, [
    h("span", { class: "returns-reason-chip", title: display(row.reason_raw) }, display(row.reason || row.reason_raw)),
    h("span", { class: "returns-status-sub" }, display(row.status || row.type, "已取消")),
  ]);
}

function renderQuantity(value: number | null): VNodeChild {
  return h("span", { class: "returns-quantity-badge" }, [h("b", value == null ? "—" : formatInteger(value)), " 件"]);
}

function rfbsStatusType(status: string | null): TagType {
  const value = String(status || "").toLowerCase();
  if (/approved|accepted|delivered|同意|已接收|已批准|完成|已签收/.test(value)) return "success";
  if (/rejected|declined|dispute|cancelled|拒绝|争议|取消/.test(value)) return "error";
  if (/pending|progress|审核|审批|处理中|在途|退回中/.test(value)) return "warning";
  return "info";
}

function formatRawMoney(value: string | number, currency: string): string {
  const number = Number(value);
  return `${Number.isFinite(number) ? formatNumber(number) : display(String(value))}${currency ? ` ${currency}` : ""}`;
}

function formatConvertedMoney(value: string | null, currency: string): string {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}` : "—";
}

function compensationLine(row: RfbsReturnRecord, prefix: "platform" | "logistics"): string {
  const platform = prefix === "platform";
  const label = platform ? "平台赔偿" : "物流商赔偿";
  const source = platform ? "RUB" : "CNY";
  const amount = platform ? row.platform_compensation_rub : row.logistics_compensation_cny;
  if (amount == null || amount === "") return `${label}：—`;
  const raw = formatRawMoney(amount, source);
  const missing = platform ? row.platform_compensation_missing_rate : row.logistics_compensation_missing_rate;
  if (missing) return `${label}：${raw} · 缺少赔偿时点汇率`;
  const target = platform ? row.platform_compensation_converted_currency : row.logistics_compensation_converted_currency;
  const converted = platform ? row.platform_compensation_converted_amount : row.logistics_compensation_converted_amount;
  if (!converted || source === target) return `${label}：${raw}`;
  return `${label}：${raw} ≈ ${formatConvertedMoney(converted, target)}`;
}

function renderRfbsIdentity(row: RfbsReturnRecord): VNodeChild {
  return h("div", { class: "returns-ident-cell" }, [
    renderCopyButton(row.return_number, "点击复制申请编号", "returns-return-number"),
    row.posting_number
      ? renderCopyButton(row.posting_number, "点击复制订单号", "returns-order-sub", `订单 ${row.posting_number}`, false)
      : h("span", { class: "returns-order-sub returns-missing" }, "订单 —"),
  ]);
}

function renderRfbsState(row: RfbsReturnRecord): VNodeChild {
  return h("div", { class: "returns-state-cell" }, [
    h(NTag, {
      bordered: false,
      round: true,
      size: "small",
      type: rfbsStatusType(row.status_raw || row.status_name),
      class: "returns-status-tag",
    }, { default: () => display(row.status_name || row.status_raw, "待处理") }),
    h("small", { class: "returns-compensation-text" }, `退款：${row.refund_amount == null ? "—" : formatMoney(row.refund_amount, row.refund_currency || "")}`),
    h("small", { class: "returns-compensation-text" }, compensationLine(row, "platform")),
    h("small", { class: "returns-compensation-text" }, compensationLine(row, "logistics")),
  ]);
}

function renderRfbsQuantity(row: RfbsReturnRecord): VNodeChild {
  return h("div", { class: "returns-quantity-money" }, [
    h("span", { class: "returns-quantity-badge returns-quantity-badge--neutral" }, [h("b", row.quantity == null ? "—" : formatInteger(row.quantity)), " 件"]),
    h("strong", { class: "returns-money-value" }, formatMoney(row.product_amount, row.product_currency || "")),
  ]);
}

function renderRfbsReason(row: RfbsReturnRecord): VNodeChild {
  const comment = row.buyer_comment_raw?.trim();
  return h("div", { class: "returns-reason-logistics" }, [
    h("span", { class: "returns-reason-chip", title: display(row.reason_raw) }, display(row.reason_name || row.reason_raw, "平台未提供原因")),
    h("span", { class: "returns-logistics-sub" }, ["退货方式：", h("b", display(row.return_method))]),
    h("span", { class: "returns-logistics-sub" }, ["退件结果：", h("b", display(row.return_result))]),
    comment
      ? h("details", { class: "returns-buyer-details" }, [
          h("summary", [h(MorphIcon, { icon: "messageSquare", size: "11", strokeWidth: "2" }), "买家留言原文"]),
          h("p", { lang: "ru" }, comment),
        ])
      : null,
  ]);
}

const cancelColumns: DataTableColumns<ReturnRecord> = [
  { key: "shop_time", title: "店铺与取消时间", minWidth: 190, render: renderReturnTime },
  { key: "posting_number", title: "订单号", minWidth: 180, render: (row) => renderCopyButton(row.posting_number, "点击复制订单号", "returns-order-number") },
  { key: "product", title: "商品信息", minWidth: 280, render: renderProductCell },
  { key: "quantity", title: "取消件数", width: 110, align: "right", render: (row) => renderQuantity(row.quantity) },
  { key: "reason", title: "取消原因与状态", minWidth: 230, render: renderCancelReason },
];

const rfbsColumns: DataTableColumns<RfbsReturnRecord> = [
  {
    key: "shop_time",
    title: "店铺与申请时间",
    minWidth: 190,
    render: (row) => renderReturnTime({
      shop_name: row.shop_name,
      cancelled_at: row.created_at,
      occurred_at: null,
      complaint_deadline: row.complaint_deadline,
      complaint_deadline_status: row.complaint_deadline_status,
    }),
  },
  { key: "identity", title: "申请编号与订单号", minWidth: 190, render: renderRfbsIdentity },
  { key: "product", title: "商品信息", minWidth: 280, render: renderProductCell },
  { key: "state", title: "状态与赔偿", minWidth: 210, render: renderRfbsState },
  { key: "quantity", title: "件数与金额", width: 135, align: "right", render: renderRfbsQuantity },
  { key: "reason", title: "原因与退件跟踪", minWidth: 270, render: renderRfbsReason },
];

function cancelRowKey(row: ReturnRecord): string {
  return `${row.shop_id}:${row.posting_number || ""}:${row.sku || ""}:${row.occurred_at || ""}`;
}

function rfbsRowKey(row: RfbsReturnRecord): string {
  return `${row.shop_id}:${row.return_id}`;
}

watch(() => route.fullPath, () => {
  if (!routeReady) return;
  const next = applyRouteQuery(route.query, 0);
  const base = baseOf(next);
  if (!loadedApiBase || !sameBase(base, loadedApiBase)) {
    loadAll(next);
  } else {
    void loadActiveTab(next);
  }
});

watch(selectedShopId, (shopId) => {
  if (ignoreNextShopChange) {
    ignoreNextShopChange = false;
    return;
  }
  if (!routeReady || filters.shopId === shopId) return;
  resetPages();
  updateFilters({ shopId, page: 1 });
});

onMounted(() => {
  const next = applyRouteQuery(route.query, selectedShopId.value);
  routeReady = true;
  if (!queryMatches(route.query, queryFor(next))) {
    void router.replace({ query: queryFor(next) });
  } else {
    loadAll(next);
  }
});

onBeforeUnmount(() => {
  cancelRequestId += 1;
  rfbsRequestId += 1;
});
</script>

<template>
  <section class="returns-view">
    <div class="analytics-toolbar returns-toolbar">
      <div class="returns-date-control analytics-date-control">
        <span>统计日期</span>
        <NDatePicker
          :formatted-value="dateRange"
          type="daterange"
          value-format="yyyy-MM-dd"
          separator="至"
          :clearable="false"
          class="analytics-date-picker"
          aria-label="异常订单明细日期范围"
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
      <div class="analytics-toolbar-foot returns-toolbar-foot">
        <span>取消记录按发生时间、rFBS退货按申请时间筛选；统计口径由后端返回</span>
        <span class="analytics-data-through">
          <span class="analytics-data-dot" aria-hidden="true" />数据截止
          <strong>{{ activeDataThrough ? formatBeijingDateTime(activeDataThrough) : "暂无" }}</strong>
        </span>
      </div>
    </div>

    <div class="returns-tabs" role="tablist" aria-label="异常订单明细子板块">
      <NButton
        size="small"
        attr-type="button"
        role="tab"
        :aria-selected="filters.tab === 'cancel'"
        :type="filters.tab === 'cancel' ? 'primary' : 'default'"
        :secondary="filters.tab !== 'cancel'"
        @click="changeTab('cancel')"
      >
        <template #icon><morph-icon icon="xCircle" size="14" stroke-width="2" /></template>
        取消明细
        <NTag size="tiny" round :bordered="false" type="default">{{ formatInteger(cancelData?.total ?? 0) }}</NTag>
      </NButton>
      <NButton
        size="small"
        attr-type="button"
        role="tab"
        :aria-selected="filters.tab === 'rfbs'"
        :type="filters.tab === 'rfbs' ? 'primary' : 'default'"
        :secondary="filters.tab !== 'rfbs'"
        @click="changeTab('rfbs')"
      >
        <template #icon><morph-icon icon="rotateCcw" size="14" stroke-width="2" /></template>
        退货明细
        <NTag size="tiny" round :bordered="false" type="default">{{ formatInteger(rfbsData?.total ?? 0) }}</NTag>
      </NButton>
    </div>

    <template v-if="filters.tab === 'cancel'">
      <ReturnsKpiCards :items="cancelKpis" />

      <NCard :bordered="false" class="analytics-table-card returns-panel">
        <template #header>
          <div class="returns-panel-header">
            <div>
              <h2><morph-icon icon="xCircle" size="18" stroke-width="1.8" />取消明细</h2>
              <span>查看所有订单取消记录与明细信息</span>
            </div>
            <form class="returns-filter" role="search" @submit.prevent="submitSearch">
              <NInput
                v-model:value="searchDraft"
                type="text"
                aria-label="搜索取消明细"
                placeholder="搜索SKU、货号或订单号…"
                @keydown.enter.prevent="submitSearch"
              >
                <template #prefix><morph-icon icon="search" size="15" stroke-width="1.8" /></template>
              </NInput>
              <NButton type="primary" attr-type="submit" :loading="cancelLoading">
                <template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>
                查询
              </NButton>
              <NButton attr-type="button" @click="clearSearch">清除</NButton>
            </form>
          </div>
        </template>
        <NAlert v-if="cancelError" type="error" class="analytics-error returns-error" :title="cancelError">
          <div class="analytics-error-content returns-error-content">
            <span>取消明细未更新，请重试。</span>
            <NButton size="small" @click="retryActive">重试</NButton>
          </div>
        </NAlert>
        <NDataTable
          class="analytics-table returns-table returns-cancel-table"
          :columns="cancelColumns"
          :data="cancelData?.items ?? []"
          :loading="cancelLoading"
          :pagination="false"
          :remote="true"
          :scroll-x="1000"
          :row-key="cancelRowKey"
        >
          <template #empty><NEmpty :description="cancelError ? '取消明细加载失败' : '当前筛选范围内没有取消记录'" /></template>
        </NDataTable>
        <div v-if="cancelData" class="analytics-pager returns-pager">
          <NButton
            size="small"
            attr-type="button"
            :disabled="cancelLoading || filters.page <= 1"
            @click="changePage(filters.page - 1)"
          >
            <template #icon><morph-icon icon="chevronLeft" size="14" stroke-width="1.8" /></template>
            上一页
          </NButton>
          <span>第 {{ filters.page }} / {{ cancelPageCount }} 页，共 {{ formatInteger(cancelData.total) }} 条</span>
          <NButton
            size="small"
            attr-type="button"
            :disabled="cancelLoading || filters.page >= cancelPageCount"
            @click="changePage(filters.page + 1)"
          >
            下一页
            <template #icon><morph-icon icon="chevronRight" size="14" stroke-width="1.8" /></template>
          </NButton>
        </div>
      </NCard>
    </template>

    <template v-else>
      <ReturnsKpiCards :items="rfbsKpis" />

      <NCard :bordered="false" class="analytics-table-card returns-panel">
        <template #header>
          <div class="returns-panel-header">
            <div>
              <h2><morph-icon icon="rotateCcw" size="18" stroke-width="1.8" />退货明细</h2>
              <span>仅显示有申请编号的 rFBS 退货申请</span>
            </div>
            <form class="returns-filter" role="search" @submit.prevent="submitSearch">
              <NInput
                v-model:value="searchDraft"
                type="text"
                aria-label="搜索退货明细"
                placeholder="搜索SKU、货号、订单号或申请编号…"
                @keydown.enter.prevent="submitSearch"
              >
                <template #prefix><morph-icon icon="search" size="15" stroke-width="1.8" /></template>
              </NInput>
              <NButton type="primary" attr-type="submit" :loading="rfbsLoading">
                <template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>
                查询
              </NButton>
              <NButton attr-type="button" @click="clearSearch">清除</NButton>
            </form>
          </div>
        </template>
        <NAlert v-if="rfbsError" type="error" class="analytics-error returns-error" :title="rfbsError">
          <div class="analytics-error-content returns-error-content">
            <span>退货明细未更新，请重试。</span>
            <NButton size="small" @click="retryActive">重试</NButton>
          </div>
        </NAlert>
        <NDataTable
          class="analytics-table returns-table returns-rfbs-table"
          :columns="rfbsColumns"
          :data="rfbsData?.items ?? []"
          :loading="rfbsLoading"
          :pagination="false"
          :remote="true"
          :scroll-x="1275"
          :row-key="rfbsRowKey"
        >
          <template #empty><NEmpty :description="rfbsError ? '退货明细加载失败' : '当前筛选范围内没有退货申请'" /></template>
        </NDataTable>
        <div v-if="rfbsData" class="analytics-pager returns-pager">
          <NButton
            size="small"
            attr-type="button"
            :disabled="rfbsLoading || filters.page <= 1"
            @click="changePage(filters.page - 1)"
          >
            <template #icon><morph-icon icon="chevronLeft" size="14" stroke-width="1.8" /></template>
            上一页
          </NButton>
          <span>第 {{ filters.page }} / {{ rfbsPageCount }} 页，共 {{ formatInteger(rfbsData.total) }} 条</span>
          <NButton
            size="small"
            attr-type="button"
            :disabled="rfbsLoading || filters.page >= rfbsPageCount"
            @click="changePage(filters.page + 1)"
          >
            下一页
            <template #icon><morph-icon icon="chevronRight" size="14" stroke-width="1.8" /></template>
          </NButton>
        </div>
      </NCard>
    </template>
  </section>
</template>
