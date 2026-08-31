<script setup lang="ts">
import SearchField from "../../shared/components/SearchField.vue";
import DatePresetPills from "../../shared/components/DatePresetPills.vue";
import "../../styles/analytics.css";
import "./complaints.css";
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch, type VNodeChild } from "vue";
import ReceivedDisputeEditor from "./components/ReceivedDisputeEditor.vue";
import ShippingComplaintEditor from "./components/ShippingComplaintEditor.vue";
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
  NSelect,
  NTag,
  useMessage,
} from "naive-ui";
import EmptyState from "../../shared/components/EmptyState.vue";
import type { DataTableColumns } from "naive-ui";
import { getErrorMessage } from "../../shared/api/client";
import {
  listReceivedDisputes,
  listShippingComplaints,
} from "./api";
import { useShop } from "../../shared/composables/useShop";
import type {
  ComplaintDeadlineStatus,
  ComplaintRecord,
  ComplaintStatusFilter,
  ReceivedDisputeRecord,
  ReceivedDisputesResponse,
  ShippingComplaintOrder,
  ShippingComplaintsResponse,
} from "./types";
import type { ShopSelection } from "../../shared/types/common";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../../shared/utils/format";
import {
  beijingThreeMonthRange,
  parseValidDateRange,
  standardDatePresetRange,
  type DateRange,
  type StandardDatePreset,
} from "../../shared/utils/date";
import { positiveInteger, queryMatches, queryValue, shopSelectionFromQuery } from "../../shared/utils/query";
import { copyText } from "../../shared/utils/clipboard";

type ComplaintTab = "shipping" | "received";
type DatePreset = StandardDatePreset;
type MacaronTone = "azure" | "lavender" | "mint" | "peach" | "butter";
type ComplaintFilters = {
  shopId: ShopSelection;
  from: string;
  to: string;
  tab: ComplaintTab;
  search: string;
  status: ComplaintStatusFilter;
  page: number;
};
type ComplaintApiBase = Pick<ComplaintFilters, "shopId" | "from" | "to">;
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
const shippingStatusOptions = [
  { label: "全部状态", value: "" },
  { label: "未创建投诉", value: "unfiled" },
  { label: "处理中", value: "open" },
  { label: "已完结", value: "closed" },
];
const receivedStatusOptions = [
  { label: "全部状态", value: "" },
  { label: "未记录", value: "unfiled" },
  { label: "处理中", value: "open" },
  { label: "已结束", value: "closed" },
];

function isComplaintTab(value: string): value is ComplaintTab {
  return value === "shipping" || value === "received";
}

function isComplaintStatus(value: string): value is ComplaintStatusFilter {
  return value === "" || value === "unfiled" || value === "open" || value === "closed";
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): ComplaintFilters {
  const tab = queryValue(query, "tab");
  const status = queryValue(query, "status");
  const [from, to] = parseValidDateRange(queryValue(query, "from"), queryValue(query, "to"), beijingThreeMonthRange());
  return {
    shopId: shopSelectionFromQuery(query, fallbackShop),
    from,
    to,
    tab: isComplaintTab(tab) ? tab : "shipping",
    search: queryValue(query, "q").trim(),
    status: isComplaintStatus(status) ? status : "",
    page: positiveInteger(queryValue(query, "page"), 1),
  };
}

const initialFilters = parseFilters(route.query, selectedShopId.value);
const filters = reactive<ComplaintFilters>(initialFilters);
const tabSearches = reactive<Record<ComplaintTab, string>>({
  shipping: initialFilters.tab === "shipping" ? initialFilters.search : "",
  received: initialFilters.tab === "received" ? initialFilters.search : "",
});
const tabStatuses = reactive<Record<ComplaintTab, ComplaintStatusFilter>>({
  shipping: initialFilters.tab === "shipping" ? initialFilters.status : "",
  received: initialFilters.tab === "received" ? initialFilters.status : "",
});
const tabPages = reactive<Record<ComplaintTab, number>>({
  shipping: initialFilters.tab === "shipping" ? initialFilters.page : 1,
  received: initialFilters.tab === "received" ? initialFilters.page : 1,
});
const searchDraft = ref(initialFilters.search);
const shippingData = ref<ShippingComplaintsResponse | null>(null);
const receivedData = ref<ReceivedDisputesResponse | null>(null);
const shippingLoading = ref(false);
const receivedLoading = ref(false);
const shippingError = ref("");
const receivedError = ref("");
const shippingEditorShow = ref(false);
const receivedEditorShow = ref(false);
const selectedShipping = ref<ShippingComplaintOrder | null>(null);
const selectedShippingComplaint = ref<ComplaintRecord | null>(null);
const selectedReceived = ref<ReceivedDisputeRecord | null>(null);
let shippingRequestId = 0;
let receivedRequestId = 0;
let routeReady = false;
let ignoreNextShopChange = false;
let loadedApiBase: ComplaintApiBase | null = null;

const dateRange = computed<DateRange>(() => [filters.from, filters.to]);
const activePreset = computed(() => {
  for (const preset of datePresets) {
    const [from, to] = standardDatePresetRange(preset.key);
    if (filters.from === from && filters.to === to) return preset.key;
  }
  return "";
});
const activeDataThrough = computed(() => filters.tab === "shipping"
  ? shippingData.value?.data_through ?? null
  : receivedData.value?.data_through ?? null);
const shippingPageCount = computed(() => pageCountFor(shippingData.value));
const receivedPageCount = computed(() => pageCountFor(receivedData.value));

function queryFor(value: ComplaintFilters): Record<string, string> {
  const query: Record<string, string> = { shop_id: String(value.shopId) };
  const defaultRange = beijingThreeMonthRange();
  const search = value.search.trim();
  if (value.tab === "received") query.tab = value.tab;
  if (search) query.q = search;
  if (value.status) query.status = value.status;
  if (value.page !== 1) query.page = String(value.page);
  if (value.from !== defaultRange[0] || value.to !== defaultRange[1]) {
    query.from = value.from;
    query.to = value.to;
  }
  return query;
}

function applyRouteQuery(query: LocationQuery, fallbackShop: ShopSelection): ComplaintFilters {
  const next = parseFilters(query, fallbackShop);
  Object.assign(filters, next);
  tabSearches[next.tab] = next.search;
  tabStatuses[next.tab] = next.status;
  tabPages[next.tab] = next.page;
  searchDraft.value = next.search;
  if (selectedShopId.value !== next.shopId) {
    ignoreNextShopChange = true;
    selectShop(next.shopId);
  }
  return next;
}

function updateRoute(next: ComplaintFilters, replace = false): void {
  const normalized = { ...next, search: next.search.trim() };
  Object.assign(filters, normalized);
  tabSearches[normalized.tab] = normalized.search;
  tabStatuses[normalized.tab] = normalized.status;
  tabPages[normalized.tab] = normalized.page;
  searchDraft.value = normalized.search;
  if (queryMatches(route.query, queryFor(normalized))) {
    void loadActiveTab(normalized);
    return;
  }
  void (replace ? router.replace({ query: queryFor(normalized) }) : router.push({ query: queryFor(normalized) }));
}

function currentFilters(): ComplaintFilters {
  const next = { ...filters, search: searchDraft.value.trim() };
  if (!queryValue(route.query, "from") && !queryValue(route.query, "to")) {
    [next.from, next.to] = beijingThreeMonthRange();
  }
  return next;
}

function updateFilters(overrides: Partial<ComplaintFilters>): void {
  updateRoute({ ...currentFilters(), ...overrides });
}

function baseOf(value: ComplaintFilters): ComplaintApiBase {
  return { shopId: value.shopId, from: value.from, to: value.to };
}

function sameBase(left: ComplaintApiBase, right: ComplaintApiBase): boolean {
  return left.shopId === right.shopId && left.from === right.from && left.to === right.to;
}

function tabRequestFilters(base: ComplaintFilters, tab: ComplaintTab): ComplaintFilters {
  return {
    ...base,
    tab,
    search: tabSearches[tab],
    status: tabStatuses[tab],
    page: tabPages[tab],
  };
}

function pageCountFor(data: { total: number; size: number } | null): number {
  return Math.max(1, Math.ceil((data?.total ?? 0) / (data?.size || PAGE_SIZE)));
}

async function loadShipping(queryFilters: ComplaintFilters): Promise<void> {
  const currentRequest = ++shippingRequestId;
  shippingLoading.value = true;
  shippingError.value = "";
  shippingData.value = null;
  try {
    const data = await listShippingComplaints({
      shopId: queryFilters.shopId,
      page: queryFilters.page,
      size: PAGE_SIZE,
      search: queryFilters.search || undefined,
      status: queryFilters.status,
      from: queryFilters.from,
      to: queryFilters.to,
    });
    if (currentRequest !== shippingRequestId) return;
    const pages = pageCountFor(data);
    if (queryFilters.page > pages) {
      tabPages.shipping = pages;
      if (filters.tab === "shipping" && filters.page === queryFilters.page) {
        await router.replace({ query: queryFor({ ...queryFilters, page: pages }) });
      }
      return;
    }
    shippingData.value = data;
  } catch (cause) {
    if (currentRequest !== shippingRequestId) return;
    shippingError.value = getErrorMessage(cause);
    message.error(shippingError.value);
  } finally {
    if (currentRequest === shippingRequestId) shippingLoading.value = false;
  }
}

async function loadReceived(queryFilters: ComplaintFilters): Promise<void> {
  const currentRequest = ++receivedRequestId;
  receivedLoading.value = true;
  receivedError.value = "";
  receivedData.value = null;
  try {
    const data = await listReceivedDisputes({
      shopId: queryFilters.shopId,
      page: queryFilters.page,
      size: PAGE_SIZE,
      search: queryFilters.search || undefined,
      status: queryFilters.status,
      from: queryFilters.from,
      to: queryFilters.to,
    });
    if (currentRequest !== receivedRequestId) return;
    const pages = pageCountFor(data);
    if (queryFilters.page > pages) {
      tabPages.received = pages;
      if (filters.tab === "received" && filters.page === queryFilters.page) {
        await router.replace({ query: queryFor({ ...queryFilters, page: pages }) });
      }
      return;
    }
    receivedData.value = data;
  } catch (cause) {
    if (currentRequest !== receivedRequestId) return;
    receivedError.value = getErrorMessage(cause);
    message.error(receivedError.value);
  } finally {
    if (currentRequest === receivedRequestId) receivedLoading.value = false;
  }
}

function loadAll(value: ComplaintFilters): void {
  loadedApiBase = baseOf(value);
  void Promise.all([
    loadShipping(tabRequestFilters(value, "shipping")),
    loadReceived(tabRequestFilters(value, "received")),
  ]);
}

function loadActiveTab(value: ComplaintFilters): Promise<void> {
  return value.tab === "shipping" ? loadShipping(value) : loadReceived(value);
}

function retryShipping(): void {
  void loadShipping(tabRequestFilters(currentFilters(), "shipping"));
}

function retryReceived(): void {
  void loadReceived(tabRequestFilters(currentFilters(), "received"));
}

function resetPages(): void {
  tabPages.shipping = 1;
  tabPages.received = 1;
}

function submitSearch(): void {
  const search = searchDraft.value.trim();
  tabSearches[filters.tab] = search;
  updateFilters({ search, page: 1 });
}

function clearSearch(): void {
  searchDraft.value = "";
  tabSearches[filters.tab] = "";
  tabStatuses[filters.tab] = "";
  updateFilters({ search: "", status: "", page: 1 });
}

function changeStatus(value: string | null): void {
  const status: ComplaintStatusFilter = value && isComplaintStatus(value) ? value : "";
  tabStatuses[filters.tab] = status;
  updateFilters({ status, page: 1 });
}

function changeTab(tab: ComplaintTab): void {
  if (filters.tab === tab) return;
  updateRoute({
    ...filters,
    tab,
    search: tabSearches[tab],
    status: tabStatuses[tab],
    page: tabPages[tab],
  });
}

function handleDateRangeChange(value: string | DateRange | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  const [from, to] = parseValidDateRange(value[0], value[1], beijingThreeMonthRange());
  if (from !== value[0] || to !== value[1]) return;
  resetPages();
  updateFilters({ from, to, page: 1 });
}

function selectPreset(preset: (typeof datePresets)[number]["key"]): void {
  const [from, to] = standardDatePresetRange(preset);
  resetPages();
  updateFilters({ from, to, page: 1 });
}

function changePage(page: number): void {
  if (page === filters.page) return;
  tabPages[filters.tab] = page;
  updateFilters({ page });
}

function display(value: string | null | undefined, fallback = "—"): string {
  return value && value.trim() ? value : fallback;
}

function formatComplaintMoney(amount: number | string | null | undefined, currency: string | null | undefined): string {
  if (amount == null || amount === "") return "—";
  const numeric = Number(amount);
  if (!Number.isFinite(numeric)) return "—";
  return `${formatNumber(numeric)}${currency ? ` ${currency}` : ""}`;
}

function formatConvertedMoney(amount: string | null | undefined, currency: string | null | undefined): string {
  const numeric = Number(amount);
  return Number.isFinite(numeric) ? `${numeric.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency || ""}` : "—";
}

async function copyValue(value: string): Promise<void> {
  try {
    await copyText(value);
    message.success(`已复制：${value}`);
  } catch {
    message.error("复制失败");
  }
}

function renderCopyButton(
  value: string | null | undefined,
  title: string,
  className = "",
  label = value || "",
  icon: IconName = "copy",
): VNodeChild {
  if (!value || !value.trim()) return h("span", { class: `complaints-missing ${className}` }, "—");
  return h("button", {
    type: "button",
    class: `complaints-copy-value ${className}`,
    title,
    onClick: (event: MouseEvent) => {
      event.stopPropagation();
      void copyValue(value);
    },
  }, [h(MorphIcon, { icon, size: "12", strokeWidth: "2" }), label]);
}

function renderMetaChip(label: string, value: string | null | undefined): VNodeChild {
  return h("span", { class: "complaints-meta-chip" }, [label, " ", h("b", display(value))]);
}

const deadlineLabels: Partial<Record<ComplaintDeadlineStatus, string>> = {
  overdue: "已逾期",
  due_today: "今日截止",
  due_soon: "即将截止",
};

function renderDeadline(row: { complaint_deadline: string | null; complaint_deadline_status: ComplaintDeadlineStatus }): VNodeChild {
  const status = row.complaint_deadline_status || "missing";
  return h("span", { class: `complaints-deadline complaints-deadline--${status}` }, [
    h(MorphIcon, { icon: status === "overdue" ? "alertCircle" : "clock", size: "11", strokeWidth: "2" }),
    h("span", `投诉截止：${row.complaint_deadline || "—"}`),
    deadlineLabels[status] ? h("b", deadlineLabels[status]) : null,
  ]);
}

function renderTag(tone: MacaronTone | "", text: string, className = ""): VNodeChild {
  return h(NTag, {
    size: "small",
    round: true,
    bordered: false,
    type: "default",
    class: tone ? `complaints-tone-tag--${tone}${className ? ` ${className}` : ""}` : className,
  }, { default: () => text });
}

// Macaron tone mapping (DESIGN.md §colors.tones): mint = 已完结/已接收,
// peach = 拒绝/争议/取消, butter = 处理中/审核中, no shell = 未知或描述性标签.
function receivedStatusTone(value: string | null | undefined): MacaronTone | "" {
  const status = String(value || "").toLowerCase();
  if (/approved|accepted|delivered|同意|已接收|已批准|完成|已签收/.test(status)) return "mint";
  if (/rejected|declined|dispute|cancelled|拒绝|争议|取消/.test(status)) return "peach";
  if (/pending|progress|审核|审批|处理中|在途|退回中/.test(status)) return "butter";
  return "";
}

function compensationLine(row: ReceivedDisputeRecord, prefix: "platform" | "logistics"): string {
  const platform = prefix === "platform";
  const label = platform ? "平台赔偿" : "物流商赔偿";
  const source = platform ? "RUB" : "CNY";
  const amount = platform ? row.platform_compensation_rub : row.logistics_compensation_cny;
  if (amount == null || amount === "") return `${label}：—`;
  const raw = formatComplaintMoney(amount, source);
  const missing = platform ? row.platform_compensation_missing_rate : row.logistics_compensation_missing_rate;
  if (missing) return `${label}：${raw} · 缺少赔偿时点汇率`;
  const target = platform ? row.platform_compensation_converted_currency : row.logistics_compensation_converted_currency;
  const converted = platform ? row.platform_compensation_converted_amount : row.logistics_compensation_converted_amount;
  if (!converted || source === target) return `${label}：${raw}`;
  return `${label}：${raw} ≈ ${formatConvertedMoney(converted, target)}`;
}

function renderShippingIdentity(row: ShippingComplaintOrder): VNodeChild {
  return h("div", { class: "complaints-shop-time" }, [
    h("span", { class: "analytics-shop-badge" }, row.shop_name),
    renderCopyButton(row.posting_number, "点击复制订单号", "complaints-order-number", row.posting_number),
    row.data_anomaly
      ? h(NTag, { size: "small", round: true, bordered: false, type: "default", class: "complaints-tone-tag--butter" }, {
          default: () => [h(MorphIcon, { icon: "alertTriangle", size: "11", strokeWidth: "2" }), "数据异常"],
        })
      : null,
  ]);
}

function renderShippingTime(row: ShippingComplaintOrder): VNodeChild {
  return h("div", { class: "complaints-time-cell" }, [
    renderCopyButton(row.tracking_number, "点击复制物流单号", "complaints-tracking-number", row.tracking_number || "", "truck"),
    h("span", `下单：${formatBeijingDateTime(row.created_at)}`),
    h("span", `发货：${row.shipped_at ? formatBeijingDateTime(row.shipped_at) : "—"}`),
    h("span", `取消：${row.cancelled_at ? formatBeijingDateTime(row.cancelled_at) : "—"}`),
    renderDeadline(row),
  ]);
}

function renderShippingProduct(row: ShippingComplaintOrder): VNodeChild {
  const first = row.items[0];
  const quantity = row.items.reduce((total, item) => total + Number(item.quantity || 0), 0);
  return h("div", { class: "complaints-product-cell" }, [
    h("strong", { class: "complaints-product-title", title: display(first?.product_name, "产品名称暂无") }, display(first?.product_name, "产品名称暂无")),
    h("div", { class: "complaints-product-meta" }, [
      renderMetaChip("SKU", first?.sku),
      renderMetaChip("货号", first?.offer_id),
      h("span", { class: "complaints-quantity-chip" }, [h("b", formatInteger(quantity)), " 件", row.items.length > 1 ? ` · 另有 ${row.items.length - 1} 种` : ""]),
    ]),
  ]);
}

function renderComplaintList(row: ShippingComplaintOrder): VNodeChild {
  const complaints = row.complaints || [];
  return h("div", { class: "complaints-action-cell" }, [
    h("div", { class: "complaints-record-list" }, complaints.length
      ? complaints.map((complaint) => h("button", {
          type: "button",
          title: "点击查看/编辑投诉明细",
          onClick: () => openShippingEditor(row, complaint),
        }, [
          h("strong", [h(MorphIcon, { icon: "fileText", size: "11", strokeWidth: "2" }), complaint.complaint_number]),
          h("small", [
            renderTag(complaint.resolved === 1 ? "mint" : "butter", complaint.resolved === 1 ? "已完结" : "处理中", "complaints-inline-status"),
            ` · ${formatBeijingDateTime(complaint.complaint_at)}`,
          ]),
        ]))
      : [h("span", { class: "complaints-missing" }, "未创建投诉")]),
    h("button", {
      type: "button",
      class: "complaints-action-button",
      onClick: () => openShippingEditor(row),
    }, [h(MorphIcon, { icon: "plus", size: "12", strokeWidth: "2" }), "新建投诉"]),
  ]);
}

function renderShippingAmount(row: ShippingComplaintOrder): VNodeChild {
  return h("div", { class: "complaints-amount-cell" }, [
    h("strong", { class: "complaints-money-value" }, formatComplaintMoney(row.amount_original, row.amount_currency)),
    h("span", { class: "complaints-reason-chip", title: display(row.cancel_reason_raw) }, display(row.cancel_reason || row.cancel_reason_raw, "原因暂缺")),
  ]);
}

function renderReceivedIdentity(row: ReceivedDisputeRecord): VNodeChild {
  return h("div", { class: "complaints-shop-time" }, [
    h("span", { class: "analytics-shop-badge" }, row.shop_name),
    renderCopyButton(row.return_number, "点击复制申请编号", "complaints-return-number", row.return_number),
    h("span", { class: "complaints-muted-line" }, `申请：${formatBeijingDateTime(row.created_at)}`),
    renderDeadline(row),
  ]);
}

function renderReceivedProduct(row: ReceivedDisputeRecord): VNodeChild {
  return h("div", { class: "complaints-product-cell" }, [
    renderCopyButton(row.posting_number, "点击复制订单号", "complaints-order-sub", row.posting_number ? `订单 ${row.posting_number}` : "订单 —", "package"),
    h("strong", { class: "complaints-product-title", title: display(row.product_name, "产品名称暂无") }, display(row.product_name, "产品名称暂无")),
    h("div", { class: "complaints-product-meta" }, [renderMetaChip("SKU", row.sku), renderMetaChip("货号", row.offer_id)]),
  ]);
}

function renderReceivedReason(row: ReceivedDisputeRecord): VNodeChild {
  const comment = row.buyer_comment_raw?.trim();
  return h("div", { class: "complaints-reason-cell" }, [
    h("strong", { class: "complaints-money-value" }, formatComplaintMoney(row.product_amount, row.product_currency)),
    h("span", { class: "complaints-reason-chip", title: display(row.reason_raw) }, display(row.reason_name || row.reason_raw, "平台未提供原因")),
    comment
      ? h("details", { class: "complaints-buyer-details" }, [
          h("summary", [h(MorphIcon, { icon: "messageSquare", size: "11", strokeWidth: "2" }), "买家留言原文"]),
          h("p", { lang: "ru" }, comment),
        ])
      : null,
  ]);
}

function renderReceivedCompensation(row: ReceivedDisputeRecord): VNodeChild {
  return h("div", { class: "complaints-state-cell" }, [
    row.refund_type ? renderTag("", row.refund_type) : null,
    h("small", `退款：${row.refund_amount == null ? "—" : formatComplaintMoney(row.refund_amount, row.refund_currency)}`),
    h("small", compensationLine(row, "platform")),
    h("small", compensationLine(row, "logistics")),
    h("small", ["退货方式：", h("b", display(row.return_method))]),
  ]);
}

function renderReceivedState(row: ReceivedDisputeRecord): VNodeChild {
  return h("div", { class: "complaints-action-cell" }, [
    h("div", { class: "complaints-state-cell" }, [
      renderTag(receivedStatusTone(row.process_status || "待处理"), row.process_status || "未记录"),
      h("span", { class: "complaints-muted-line" }, ["方式：", h("b", display(row.handling_method))]),
      h("span", { class: "complaints-muted-line" }, ["结果：", h("b", display(row.return_result))]),
    ]),
    h("button", {
      type: "button",
      class: "complaints-action-button",
      onClick: () => openReceivedEditor(row),
    }, [h(MorphIcon, { icon: "edit", size: "12", strokeWidth: "2" }), "编辑"]),
  ]);
}

// Fixed-layout width system (DESIGN.md §3): every column carries an explicit
// width and the sum equals the table's scroll-x (shipping 190+225+280+170+190
// = 1055, received 200+260+240+260+210 = 1170), so long product names clip
// with ellipsis instead of stretching columns.
const shippingColumns: DataTableColumns<ShippingComplaintOrder> = [
  { key: "identity", title: "店铺与订单", width: 190, render: renderShippingIdentity },
  { key: "time", title: "物流与时效", width: 225, render: renderShippingTime },
  { key: "product", title: "商品信息", width: 280, render: renderShippingProduct },
  { key: "amount", title: "金额与取消原因", width: 170, align: "right", render: renderShippingAmount },
  { key: "complaints", title: "投诉记录与操作", width: 190, align: "right", render: renderComplaintList },
];
const receivedColumns: DataTableColumns<ReceivedDisputeRecord> = [
  { key: "identity", title: "店铺与退货申请", width: 200, render: renderReceivedIdentity },
  { key: "product", title: "订单与商品", width: 260, render: renderReceivedProduct },
  { key: "reason", title: "金额与纠纷原因", width: 240, render: renderReceivedReason },
  { key: "compensation", title: "退款与赔偿", width: 260, render: renderReceivedCompensation },
  { key: "state", title: "处理状态与操作", width: 210, align: "right", render: renderReceivedState },
];

function shippingRowKey(row: ShippingComplaintOrder): string {
  return `${row.shop_id}:${row.posting_number}`;
}

function receivedRowKey(row: ReceivedDisputeRecord): string {
  return `${row.shop_id}:${row.return_number}`;
}

function openShippingEditor(row: ShippingComplaintOrder, complaint: ComplaintRecord | null = null): void {
  selectedShipping.value = row;
  selectedShippingComplaint.value = complaint;
  shippingEditorShow.value = true;
}

function openReceivedEditor(row: ReceivedDisputeRecord): void {
  selectedReceived.value = row;
  receivedEditorShow.value = true;
}

function refreshShippingAfterSave(): void {
  void loadShipping(tabRequestFilters(currentFilters(), "shipping"));
}

function refreshReceivedAfterSave(): void {
  void loadReceived(tabRequestFilters(currentFilters(), "received"));
}

watch(() => route.fullPath, () => {
  if (!routeReady) return;
  const next = applyRouteQuery(route.query, 0);
  const base = baseOf(next);
  if (!loadedApiBase || !sameBase(base, loadedApiBase)) {
    tabPages.shipping = next.tab === "shipping" ? next.page : 1;
    tabPages.received = next.tab === "received" ? next.page : 1;
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
  shippingRequestId += 1;
  receivedRequestId += 1;
});
</script>

<template>
  <section class="complaints-view">
    <div class="analytics-toolbar">
      <div class="analytics-date-control">
        <span>统计日期</span>
        <NDatePicker
          :formatted-value="dateRange"
          type="daterange"
          value-format="yyyy-MM-dd"
          separator="至"
          :clearable="false"
          class="analytics-date-picker"
          aria-label="异常订单投诉日期范围"
          @update:formatted-value="handleDateRangeChange"
        />
        <DatePresetPills class="analytics-date-presets" aria-label="日期快捷范围" :options="datePresets" :active-key="activePreset" @select="selectPreset" />
      </div>
      <div class="analytics-toolbar-foot">
        <span>发货未收货按订单创建时间、已收货纠纷按退货申请时间筛选；投诉截止日期由后端返回</span>
        <span class="analytics-data-through">
          <span class="analytics-data-dot" aria-hidden="true" />数据截止
          <strong>{{ activeDataThrough ? formatBeijingDateTime(activeDataThrough) : "暂无" }}</strong>
        </span>
      </div>
    </div>

    <div class="analytics-tabs" role="tablist" aria-label="异常订单投诉子板块">
      <NButton
        size="small"
        attr-type="button"
        role="tab"
        :aria-selected="filters.tab === 'shipping'"
        :type="filters.tab === 'shipping' ? 'primary' : 'default'"
        :secondary="filters.tab !== 'shipping'"
        @click="changeTab('shipping')"
      >
        <template #icon><morph-icon icon="truck" size="14" stroke-width="2" /></template>
        发货未收货投诉
        <NTag size="tiny" round :bordered="false" type="default">{{ formatInteger(shippingData?.total ?? 0) }}</NTag>
      </NButton>
      <NButton
        size="small"
        attr-type="button"
        role="tab"
        :aria-selected="filters.tab === 'received'"
        :type="filters.tab === 'received' ? 'primary' : 'default'"
        :secondary="filters.tab !== 'received'"
        @click="changeTab('received')"
      >
        <template #icon><morph-icon icon="messageSquareAlert" size="14" stroke-width="2" /></template>
        已收货纠纷
        <NTag size="tiny" round :bordered="false" type="default">{{ formatInteger(receivedData?.total ?? 0) }}</NTag>
      </NButton>
    </div>

    <NCard v-if="filters.tab === 'shipping'" :bordered="false" class="analytics-table-card">
      <template #header>
        <div class="complaints-panel-header">
          <div>
            <h2><morph-icon icon="truck" size="18" stroke-width="1.8" />发货未收货投诉</h2>
            <span>仅展示发货后取消或存在数据异常的候选订单</span>
          </div>
          <form class="complaints-filter" role="search" @submit.prevent="submitSearch">
            <SearchField
              v-model:value="searchDraft"
              type="text"
              aria-label="搜索发货未收货投诉"
              placeholder="搜索订单号、物流单号、SKU、货号或投诉编号…"
              @keydown.enter.prevent="submitSearch"
            />
            <NSelect
              :value="filters.status"
              :options="shippingStatusOptions"
              aria-label="投诉状态筛选"
              class="complaints-status-select"
              @update:value="changeStatus"
            />
            <NButton type="primary" attr-type="submit" :loading="shippingLoading">
              <template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>
              查询
            </NButton>
            <NButton attr-type="button" @click="clearSearch">清除</NButton>
          </form>
        </div>
      </template>
      <NAlert v-if="shippingError" type="error" class="analytics-error" :title="shippingError">
        <div class="analytics-error-content">
          <span>发货未收货投诉未更新，请重试。</span>
          <NButton size="small" @click="retryShipping">重试</NButton>
        </div>
      </NAlert>
      <NDataTable
        class="analytics-table"
        :columns="shippingColumns"
        :data="shippingData?.items ?? []"
        :loading="shippingLoading"
        :pagination="false"
        :remote="true"
        :scroll-x="1055"
        table-layout="fixed"
        :row-key="shippingRowKey"
      >
        <template #empty><EmptyState :title="shippingError ? '投诉候选加载失败' : '当前筛选范围内没有候选订单'" icon="truck" /></template>
      </NDataTable>
      <div v-if="shippingData" class="analytics-pager">
        <NButton size="small" attr-type="button" :disabled="shippingLoading || filters.page <= 1" @click="changePage(filters.page - 1)">
          <template #icon><morph-icon icon="chevronLeft" size="14" stroke-width="1.8" /></template>
          上一页
        </NButton>
        <span>第 {{ filters.page }} / {{ shippingPageCount }} 页，共 {{ formatInteger(shippingData.total) }} 条</span>
        <NButton size="small" attr-type="button" :disabled="shippingLoading || filters.page >= shippingPageCount" @click="changePage(filters.page + 1)">
          下一页
          <template #icon><morph-icon icon="chevronRight" size="14" stroke-width="1.8" /></template>
        </NButton>
      </div>
    </NCard>

    <NCard v-else :bordered="false" class="analytics-table-card">
      <template #header>
        <div class="complaints-panel-header">
          <div>
            <h2><morph-icon icon="messageSquareAlert" size="18" stroke-width="1.8" />已收货纠纷</h2>
            <span>按店铺与退货申请编号独立保存人工处理信息</span>
          </div>
          <form class="complaints-filter" role="search" @submit.prevent="submitSearch">
            <SearchField
              v-model:value="searchDraft"
              type="text"
              aria-label="搜索已收货纠纷"
              placeholder="搜索SKU、货号、订单号或退货申请编号…"
              @keydown.enter.prevent="submitSearch"
            />
            <NSelect
              :value="filters.status"
              :options="receivedStatusOptions"
              aria-label="处理状态筛选"
              class="complaints-status-select"
              @update:value="changeStatus"
            />
            <NButton type="primary" attr-type="submit" :loading="receivedLoading">
              <template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>
              查询
            </NButton>
            <NButton attr-type="button" @click="clearSearch">清除</NButton>
          </form>
        </div>
      </template>
      <NAlert v-if="receivedError" type="error" class="analytics-error" :title="receivedError">
        <div class="analytics-error-content">
          <span>已收货纠纷未更新，请重试。</span>
          <NButton size="small" @click="retryReceived">重试</NButton>
        </div>
      </NAlert>
      <NDataTable
        class="analytics-table"
        :columns="receivedColumns"
        :data="receivedData?.items ?? []"
        :loading="receivedLoading"
        :pagination="false"
        :remote="true"
        :scroll-x="1170"
        table-layout="fixed"
        :row-key="receivedRowKey"
      >
        <template #empty><EmptyState :title="receivedError ? '已收货纠纷加载失败' : '当前筛选范围内没有退货申请'" icon="messageSquareAlert" /></template>
      </NDataTable>
      <div v-if="receivedData" class="analytics-pager">
        <NButton size="small" attr-type="button" :disabled="receivedLoading || filters.page <= 1" @click="changePage(filters.page - 1)">
          <template #icon><morph-icon icon="chevronLeft" size="14" stroke-width="1.8" /></template>
          上一页
        </NButton>
        <span>第 {{ filters.page }} / {{ receivedPageCount }} 页，共 {{ formatInteger(receivedData.total) }} 条</span>
        <NButton size="small" attr-type="button" :disabled="receivedLoading || filters.page >= receivedPageCount" @click="changePage(filters.page + 1)">
          下一页
          <template #icon><morph-icon icon="chevronRight" size="14" stroke-width="1.8" /></template>
        </NButton>
      </div>
    </NCard>

    <ShippingComplaintEditor
      v-model:show="shippingEditorShow"
      :row="selectedShipping"
      :complaint="selectedShippingComplaint"
      @saved="refreshShippingAfterSave"
    />
    <ReceivedDisputeEditor
      v-model:show="receivedEditorShow"
      :row="selectedReceived"
      @saved="refreshReceivedAfterSave"
    />
  </section>
</template>
