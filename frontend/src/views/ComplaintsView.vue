<script setup lang="ts">
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
  NInputNumber,
  NModal,
  NSelect,
  NTag,
  useMessage,
} from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { getErrorMessage } from "../api/client";
import {
  listReceivedDisputes,
  listShippingComplaints,
  saveReceivedDispute,
  saveShippingComplaint,
  type ReceivedDisputePayload,
  type ShippingComplaintPayload,
} from "../api/complaints";
import { useShop } from "../composables/useShop";
import type {
  ComplaintDeadlineStatus,
  ComplaintRecord,
  ComplaintStatusFilter,
  ReceivedDisputeRecord,
  ReceivedDisputesResponse,
  ShippingComplaintOrder,
  ShippingComplaintsResponse,
  ShopId,
  ShopSelection,
} from "../types/api";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../utils/format";
import {
  beijingToday,
  parseValidDateRange,
  shiftDays,
  subtractMonths,
  type DateRange,
} from "../utils/date";
import { isShopSelection, positiveInteger, queryValue } from "../utils/query";
import { copyText } from "../utils/clipboard";

type ComplaintTab = "shipping" | "received";
type BoolChoice = "" | "true" | "false";
type TagType = "default" | "info" | "success" | "warning" | "error";
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
type ShippingComplaintForm = {
  shopId: ShopId;
  postingNumber: string;
  complaintNumber: string;
  complaintAt: string;
  channel: string;
  warehouse: string;
  orderProcessStatus: string;
  complaintStatus: string;
  compensationStatus: string;
  platformCompensation: number | null;
  platformAt: string;
  logisticsCompensation: number | null;
  logisticsAt: string;
  notReceivedReturn: BoolChoice;
  resolved: BoolChoice;
  notes: string;
};
type ReceivedDisputeForm = {
  shopId: ShopId;
  returnNumber: string;
  refundType: string;
  refundAmount: number | null;
  refundCurrency: string;
  platformCompensation: number | null;
  platformAt: string;
  logisticsCompensation: number | null;
  logisticsAt: string;
  processStatus: string;
  returnMethod: string;
  imlReturnNumber: string;
  imlSystemSn: string;
  buyerTrackingNumber: string;
  handlingMethod: string;
  videoRecorded: BoolChoice;
  outboundOrderNumber: string;
  returnResult: string;
  notes: string;
};

const PAGE_SIZE = 50;
const route = useRoute();
const router = useRouter();
const message = useMessage();
const { selectedShopId, selectShop } = useShop();
const datePresets: ReadonlyArray<{ key: "today" | "3days" | "7days" | "3months" | "all"; label: string }> = [
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

function formatBeijingDateTimeInput(value: string | Date | null | undefined): string {
  if (!value) return "";
  const text = formatBeijingDateTime(value instanceof Date ? value.toISOString() : value);
  return text === "暂无" ? "" : text.replace(" ", "T");
}

function beijingInputToUtc(value: string): string {
  if (!value) return "";
  const date = new Date(`${value}:00+08:00`);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}
const booleanOptions = [
  { label: "未填写", value: "" },
  { label: "是", value: "true" },
  { label: "否", value: "false" },
];
const refundTypeOptions = [
  { label: "未填写", value: "" },
  { label: "部分退款", value: "部分退款" },
  { label: "全额退款", value: "全额退款" },
  { label: "多次纠纷", value: "多次纠纷" },
];
const returnMethodOptions = [
  { label: "未填写", value: "" },
  { label: "未退货", value: "未退货" },
  { label: "IML", value: "IML" },
  { label: "FBO二次销售", value: "FBO二次销售" },
];
const handlingMethodOptions = [
  { label: "未填写", value: "" },
  { label: "退回", value: "退回" },
  { label: "销毁", value: "销毁" },
];
const returnResultOptions = [
  { label: "未填写", value: "" },
  { label: "退回国内中", value: "退回国内中" },
  { label: "已签收", value: "已签收" },
  { label: "已销毁", value: "已销毁" },
];

function defaultDateRange(): DateRange {
  const today = beijingToday();
  return [subtractMonths(today, 3), today];
}

function isComplaintTab(value: string): value is ComplaintTab {
  return value === "shipping" || value === "received";
}

function isComplaintStatus(value: string): value is ComplaintStatusFilter {
  return value === "" || value === "unfiled" || value === "open" || value === "closed";
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): ComplaintFilters {
  const shop = queryValue(query, "shop_id");
  const tab = queryValue(query, "tab");
  const status = queryValue(query, "status");
  const [from, to] = parseValidDateRange(queryValue(query, "from"), queryValue(query, "to"), defaultDateRange());
  return {
    shopId: isShopSelection(shop) ? Number(shop) as ShopSelection : fallbackShop,
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
const shippingSaving = ref(false);
const receivedSaving = ref(false);
const selectedShipping = ref<ShippingComplaintOrder | null>(null);
const selectedShippingComplaint = ref<ComplaintRecord | null>(null);
const selectedReceived = ref<ReceivedDisputeRecord | null>(null);
const shippingForm = reactive<ShippingComplaintForm>({
  shopId: 1,
  postingNumber: "",
  complaintNumber: "",
  complaintAt: "",
  channel: "",
  warehouse: "",
  orderProcessStatus: "",
  complaintStatus: "",
  compensationStatus: "",
  platformCompensation: null,
  platformAt: "",
  logisticsCompensation: null,
  logisticsAt: "",
  notReceivedReturn: "",
  resolved: "",
  notes: "",
});
const receivedForm = reactive<ReceivedDisputeForm>({
  shopId: 1,
  returnNumber: "",
  refundType: "",
  refundAmount: null,
  refundCurrency: "",
  platformCompensation: null,
  platformAt: "",
  logisticsCompensation: null,
  logisticsAt: "",
  processStatus: "",
  returnMethod: "",
  imlReturnNumber: "",
  imlSystemSn: "",
  buyerTrackingNumber: "",
  handlingMethod: "",
  videoRecorded: "",
  outboundOrderNumber: "",
  returnResult: "",
  notes: "",
});
let shippingRequestId = 0;
let receivedRequestId = 0;
let shippingSaveId = 0;
let receivedSaveId = 0;
let routeReady = false;
let mounted = false;
let ignoreNextShopChange = false;
let loadedApiBase: ComplaintApiBase | null = null;

const dateRange = computed<DateRange>(() => [filters.from, filters.to]);
const activePreset = computed(() => {
  for (const preset of datePresets) {
    const [from, to] = presetRange(preset.key);
    if (filters.from === from && filters.to === to) return preset.key;
  }
  return "";
});
const activeDataThrough = computed(() => filters.tab === "shipping"
  ? shippingData.value?.data_through ?? null
  : receivedData.value?.data_through ?? null);
const shippingPageCount = computed(() => pageCountFor(shippingData.value));
const receivedPageCount = computed(() => pageCountFor(receivedData.value));
const shippingPlatformConversion = computed(() => compensationPreview(
  shippingForm.platformCompensation,
  shippingForm.platformAt,
  selectedShippingComplaint.value?.platform_compensation_rub,
  selectedShippingComplaint.value?.platform_compensated_at,
  selectedShippingComplaint.value?.platform_compensation_missing_rate,
  selectedShippingComplaint.value?.platform_compensation_converted_currency,
  selectedShippingComplaint.value?.platform_compensation_converted_amount,
  selectedShippingComplaint.value?.platform_compensation_base_rates,
  "RUB",
));
const shippingLogisticsConversion = computed(() => compensationPreview(
  shippingForm.logisticsCompensation,
  shippingForm.logisticsAt,
  selectedShippingComplaint.value?.logistics_compensation_cny,
  selectedShippingComplaint.value?.logistics_compensated_at,
  selectedShippingComplaint.value?.logistics_compensation_missing_rate,
  selectedShippingComplaint.value?.logistics_compensation_converted_currency,
  selectedShippingComplaint.value?.logistics_compensation_converted_amount,
  selectedShippingComplaint.value?.logistics_compensation_base_rates,
  "CNY",
));
const receivedPlatformConversion = computed(() => compensationPreview(
  receivedForm.platformCompensation,
  receivedForm.platformAt,
  selectedReceived.value?.platform_compensation_rub,
  selectedReceived.value?.platform_compensated_at,
  selectedReceived.value?.platform_compensation_missing_rate,
  selectedReceived.value?.platform_compensation_converted_currency,
  selectedReceived.value?.platform_compensation_converted_amount,
  selectedReceived.value?.platform_compensation_base_rates,
  "RUB",
));
const receivedLogisticsConversion = computed(() => compensationPreview(
  receivedForm.logisticsCompensation,
  receivedForm.logisticsAt,
  selectedReceived.value?.logistics_compensation_cny,
  selectedReceived.value?.logistics_compensated_at,
  selectedReceived.value?.logistics_compensation_missing_rate,
  selectedReceived.value?.logistics_compensation_converted_currency,
  selectedReceived.value?.logistics_compensation_converted_amount,
  selectedReceived.value?.logistics_compensation_base_rates,
  "CNY",
));

function presetRange(preset: (typeof datePresets)[number]["key"]): DateRange {
  const today = beijingToday();
  if (preset === "today") return [today, today];
  if (preset === "3days") return [shiftDays(today, -2), today];
  if (preset === "7days") return [shiftDays(today, -6), today];
  if (preset === "all") return ["2020-01-01", today];
  return defaultDateRange();
}

function queryFor(value: ComplaintFilters): Record<string, string> {
  const query: Record<string, string> = { shop_id: String(value.shopId) };
  const defaultRange = defaultDateRange();
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

function queryMatches(query: LocationQuery, value: ComplaintFilters): boolean {
  const expected = queryFor(value);
  const keys = new Set([...Object.keys(query), ...Object.keys(expected)]);
  return [...keys].every((key) => queryValue(query, key) === (expected[key] ?? ""));
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
  if (queryMatches(route.query, normalized)) {
    void loadActiveTab(normalized);
    return;
  }
  void (replace ? router.replace({ query: queryFor(normalized) }) : router.push({ query: queryFor(normalized) }));
}

function currentFilters(): ComplaintFilters {
  const next = { ...filters, search: searchDraft.value.trim() };
  if (!queryValue(route.query, "from") && !queryValue(route.query, "to")) {
    [next.from, next.to] = defaultDateRange();
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
  const [from, to] = parseValidDateRange(value[0], value[1], defaultDateRange());
  if (from !== value[0] || to !== value[1]) return;
  resetPages();
  updateFilters({ from, to, page: 1 });
}

function selectPreset(preset: (typeof datePresets)[number]["key"]): void {
  const [from, to] = presetRange(preset);
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

function sameAmount(left: number | null, right: string | number | null | undefined): boolean {
  if (left == null) return right == null || right === "";
  return right != null && right !== "" && Number(left) === Number(right);
}

function sameDateTimeInput(input: string, original: string | null | undefined): boolean {
  if (!input) return !original;
  if (!original) return false;
  const left = Date.parse(beijingInputToUtc(input));
  const right = Date.parse(original);
  return Number.isFinite(left) && Number.isFinite(right) && left === right;
}

function compensationPreview(
  amount: number | null,
  time: string,
  originalAmount: string | number | null | undefined,
  originalTime: string | null | undefined,
  missingRate: boolean | undefined,
  target: string | null | undefined,
  converted: string | null | undefined,
  rates: Record<string, string> | undefined,
  source: string,
): string {
  if (amount == null) return "折算金额：—";
  if (!sameAmount(amount, originalAmount) || !sameDateTimeInput(time, originalTime)) return "保存后按赔偿时点重新计算";
  if (missingRate) return "缺少赔偿时点汇率";
  if (!converted || !target) return "折算金额：—";
  if (source === target) return `折算金额：${formatConvertedMoney(converted, target)}\n店铺币种相同，无需折算`;
  const rateText = Object.entries(rates || {}).map(([key, value]) => `${key.replace("_", "/")} ${value}`).join("｜");
  return `折算金额：${formatConvertedMoney(converted, target)}${rateText ? `\n采用基础汇率：${rateText}` : ""}`;
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

function deadlineText(row: { complaint_deadline: string | null; complaint_deadline_status: ComplaintDeadlineStatus }): string {
  return `投诉截止：${row.complaint_deadline || "—"}${deadlineLabels[row.complaint_deadline_status] ? ` · ${deadlineLabels[row.complaint_deadline_status]}` : ""}`;
}

function renderDeadline(row: { complaint_deadline: string | null; complaint_deadline_status: ComplaintDeadlineStatus }): VNodeChild {
  const status = row.complaint_deadline_status || "missing";
  return h("span", { class: `complaints-deadline complaints-deadline--${status}` }, [
    h(MorphIcon, { icon: status === "overdue" ? "alertCircle" : "clock", size: "11", strokeWidth: "2" }),
    h("span", `投诉截止：${row.complaint_deadline || "—"}`),
    deadlineLabels[status] ? h("b", deadlineLabels[status]) : null,
  ]);
}

function renderTag(type: TagType, text: string, className = ""): VNodeChild {
  return h(NTag, { size: "small", round: true, bordered: false, type, class: className }, { default: () => text });
}

function receivedStatusType(value: string | null | undefined): TagType {
  const status = String(value || "").toLowerCase();
  if (/approved|accepted|delivered|同意|已接收|已批准|完成|已签收/.test(status)) return "success";
  if (/rejected|declined|dispute|cancelled|拒绝|争议|取消/.test(status)) return "error";
  if (/pending|progress|审核|审批|处理中|在途|退回中/.test(status)) return "warning";
  return "info";
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
    h("span", { class: "complaints-shop-badge" }, row.shop_name),
    renderCopyButton(row.posting_number, "点击复制订单号", "complaints-order-number", row.posting_number),
    row.data_anomaly
      ? h(NTag, { size: "small", round: true, bordered: false, type: "warning", class: "complaints-anomaly-tag" }, {
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
            renderTag(complaint.resolved === 1 ? "success" : "warning", complaint.resolved === 1 ? "已完结" : "处理中", "complaints-inline-status"),
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
    h("span", { class: "complaints-shop-badge" }, row.shop_name),
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
    row.refund_type ? renderTag("info", row.refund_type) : null,
    h("small", `退款：${row.refund_amount == null ? "—" : formatComplaintMoney(row.refund_amount, row.refund_currency)}`),
    h("small", compensationLine(row, "platform")),
    h("small", compensationLine(row, "logistics")),
    h("small", ["退货方式：", h("b", display(row.return_method))]),
  ]);
}

function renderReceivedState(row: ReceivedDisputeRecord): VNodeChild {
  return h("div", { class: "complaints-action-cell" }, [
    h("div", { class: "complaints-state-cell" }, [
      renderTag(receivedStatusType(row.process_status || "待处理"), row.process_status || "未记录"),
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

const shippingColumns: DataTableColumns<ShippingComplaintOrder> = [
  { key: "identity", title: "店铺与订单", minWidth: 190, render: renderShippingIdentity },
  { key: "time", title: "物流与时效", minWidth: 225, render: renderShippingTime },
  { key: "product", title: "商品信息", minWidth: 280, render: renderShippingProduct },
  { key: "amount", title: "金额与取消原因", minWidth: 170, align: "right", render: renderShippingAmount },
  { key: "complaints", title: "投诉记录与操作", minWidth: 190, align: "right", render: renderComplaintList },
];
const receivedColumns: DataTableColumns<ReceivedDisputeRecord> = [
  { key: "identity", title: "店铺与退货申请", minWidth: 190, render: renderReceivedIdentity },
  { key: "product", title: "订单与商品", minWidth: 250, render: renderReceivedProduct },
  { key: "reason", title: "金额与纠纷原因", minWidth: 220, render: renderReceivedReason },
  { key: "compensation", title: "退款与赔偿", minWidth: 250, render: renderReceivedCompensation },
  { key: "state", title: "处理状态与操作", minWidth: 180, align: "right", render: renderReceivedState },
];

function shippingRowKey(row: ShippingComplaintOrder): string {
  return `${row.shop_id}:${row.posting_number}`;
}

function receivedRowKey(row: ReceivedDisputeRecord): string {
  return `${row.shop_id}:${row.return_number}`;
}

function boolChoice(value: number | null | undefined): BoolChoice {
  return value == null ? "" : String(Boolean(value)) as BoolChoice;
}

function nullableBool(value: BoolChoice): boolean | null {
  return value === "" ? null : value === "true";
}

function numberOrNull(value: string | number | null | undefined): number | null {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function openShippingEditor(row: ShippingComplaintOrder, complaint: ComplaintRecord | null = null): void {
  selectedShipping.value = row;
  selectedShippingComplaint.value = complaint;
  Object.assign(shippingForm, {
    shopId: row.shop_id,
    postingNumber: row.posting_number,
    complaintNumber: complaint?.complaint_number || "",
    complaintAt: formatBeijingDateTimeInput(complaint?.complaint_at) || formatBeijingDateTimeInput(new Date()),
    channel: complaint?.channel || "",
    warehouse: complaint?.warehouse || "",
    orderProcessStatus: complaint?.order_process_status || "",
    complaintStatus: complaint?.complaint_status || "",
    compensationStatus: complaint?.compensation_status || "",
    platformCompensation: numberOrNull(complaint?.platform_compensation_rub),
    platformAt: formatBeijingDateTimeInput(complaint?.platform_compensated_at),
    logisticsCompensation: numberOrNull(complaint?.logistics_compensation_cny),
    logisticsAt: formatBeijingDateTimeInput(complaint?.logistics_compensated_at),
    notReceivedReturn: boolChoice(complaint?.not_received_return),
    resolved: boolChoice(complaint?.resolved),
    notes: complaint?.notes || "",
  });
  shippingEditorShow.value = true;
}

function openReceivedEditor(row: ReceivedDisputeRecord): void {
  selectedReceived.value = row;
  Object.assign(receivedForm, {
    shopId: row.shop_id,
    returnNumber: row.return_number,
    refundType: row.refund_type || "",
    refundAmount: row.refund_amount,
    refundCurrency: row.refund_currency || row.settlement_currency,
    platformCompensation: numberOrNull(row.platform_compensation_rub),
    platformAt: formatBeijingDateTimeInput(row.platform_compensated_at),
    logisticsCompensation: numberOrNull(row.logistics_compensation_cny),
    logisticsAt: formatBeijingDateTimeInput(row.logistics_compensated_at),
    processStatus: row.process_status || "",
    returnMethod: row.return_method || "",
    imlReturnNumber: row.iml_return_number || "",
    imlSystemSn: row.iml_system_sn || "",
    buyerTrackingNumber: row.buyer_tracking_number || "",
    handlingMethod: row.handling_method || "",
    videoRecorded: boolChoice(row.video_recorded),
    outboundOrderNumber: row.outbound_order_number || "",
    returnResult: row.return_result || "",
    notes: row.notes || "",
  });
  receivedEditorShow.value = true;
}

async function submitShipping(): Promise<void> {
  if (shippingSaving.value) return;
  if (!shippingForm.complaintNumber.trim() || !shippingForm.complaintAt || !shippingForm.channel.trim()) {
    message.error("投诉编号、投诉时间和投诉渠道为必填项");
    return;
  }
  const currentSave = ++shippingSaveId;
  shippingSaving.value = true;
  const body: ShippingComplaintPayload = {
    shop_id: shippingForm.shopId,
    posting_number: shippingForm.postingNumber,
    complaint_number: shippingForm.complaintNumber.trim(),
    complaint_at: beijingInputToUtc(shippingForm.complaintAt),
    channel: shippingForm.channel.trim(),
    not_received_return: nullableBool(shippingForm.notReceivedReturn),
    warehouse: shippingForm.warehouse.trim(),
    order_process_status: shippingForm.orderProcessStatus.trim(),
    complaint_status: shippingForm.complaintStatus.trim(),
    compensation_status: shippingForm.compensationStatus.trim(),
    platform_compensation_rub: shippingForm.platformCompensation,
    platform_compensated_at: beijingInputToUtc(shippingForm.platformAt),
    logistics_compensation_cny: shippingForm.logisticsCompensation,
    logistics_compensated_at: beijingInputToUtc(shippingForm.logisticsAt),
    resolved: nullableBool(shippingForm.resolved),
    package_returned: null,
    notes: shippingForm.notes,
  };
  try {
    await saveShippingComplaint(body);
    if (currentSave !== shippingSaveId || !mounted) return;
    message.success("投诉已保存");
    shippingEditorShow.value = false;
    await loadShipping(tabRequestFilters(currentFilters(), "shipping"));
  } catch (cause) {
    if (currentSave === shippingSaveId && mounted) message.error(getErrorMessage(cause));
  } finally {
    if (currentSave === shippingSaveId) shippingSaving.value = false;
  }
}

async function submitReceived(): Promise<void> {
  if (receivedSaving.value) return;
  const currentSave = ++receivedSaveId;
  receivedSaving.value = true;
  const body: ReceivedDisputePayload = {
    shop_id: receivedForm.shopId,
    return_number: receivedForm.returnNumber,
    refund_type: receivedForm.refundType,
    refund_amount: receivedForm.refundAmount,
    refund_currency: receivedForm.refundCurrency.trim(),
    platform_compensation_rub: receivedForm.platformCompensation,
    platform_compensated_at: beijingInputToUtc(receivedForm.platformAt),
    logistics_compensation_cny: receivedForm.logisticsCompensation,
    logistics_compensated_at: beijingInputToUtc(receivedForm.logisticsAt),
    process_status: receivedForm.processStatus.trim(),
    return_method: receivedForm.returnMethod,
    iml_return_number: receivedForm.imlReturnNumber.trim(),
    iml_system_sn: receivedForm.imlSystemSn.trim(),
    buyer_tracking_number: receivedForm.buyerTrackingNumber.trim(),
    handling_method: receivedForm.handlingMethod,
    video_recorded: nullableBool(receivedForm.videoRecorded),
    outbound_order_number: receivedForm.outboundOrderNumber.trim(),
    return_result: receivedForm.returnResult,
    notes: receivedForm.notes,
  };
  try {
    await saveReceivedDispute(body);
    if (currentSave !== receivedSaveId || !mounted) return;
    message.success("已收货纠纷已保存");
    receivedEditorShow.value = false;
    await loadReceived(tabRequestFilters(currentFilters(), "received"));
  } catch (cause) {
    if (currentSave === receivedSaveId && mounted) message.error(getErrorMessage(cause));
  } finally {
    if (currentSave === receivedSaveId) receivedSaving.value = false;
  }
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
  mounted = true;
  const next = applyRouteQuery(route.query, selectedShopId.value);
  routeReady = true;
  if (!queryMatches(route.query, next)) {
    void router.replace({ query: queryFor(next) });
  } else {
    loadAll(next);
  }
});

onBeforeUnmount(() => {
  mounted = false;
  shippingRequestId += 1;
  receivedRequestId += 1;
  shippingSaveId += 1;
  receivedSaveId += 1;
});
</script>

<template>
  <section class="complaints-view">
    <div class="analytics-toolbar complaints-toolbar">
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
      <div class="analytics-toolbar-foot">
        <span>发货未收货按订单创建时间、已收货纠纷按退货申请时间筛选；投诉截止日期由后端返回</span>
        <span class="analytics-data-through">
          <span class="analytics-data-dot" aria-hidden="true" />数据截止
          <strong>{{ activeDataThrough ? formatBeijingDateTime(activeDataThrough) : "暂无" }}</strong>
        </span>
      </div>
    </div>

    <div class="complaints-tabs" role="tablist" aria-label="异常订单投诉子板块">
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

    <NCard v-if="filters.tab === 'shipping'" :bordered="false" class="analytics-table-card complaints-panel">
      <template #header>
        <div class="complaints-panel-header">
          <div>
            <h2><morph-icon icon="truck" size="18" stroke-width="1.8" />发货未收货投诉</h2>
            <span>仅展示发货后取消或存在数据异常的候选订单</span>
          </div>
          <form class="complaints-filter" role="search" @submit.prevent="submitSearch">
            <NInput
              v-model:value="searchDraft"
              type="text"
              aria-label="搜索发货未收货投诉"
              placeholder="搜索订单号、物流单号、SKU、货号或投诉编号…"
              @keydown.enter.prevent="submitSearch"
            >
              <template #prefix><morph-icon icon="search" size="15" stroke-width="1.8" /></template>
            </NInput>
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
        class="analytics-table complaints-table"
        :columns="shippingColumns"
        :data="shippingData?.items ?? []"
        :loading="shippingLoading"
        :pagination="false"
        :remote="true"
        :scroll-x="1055"
        :row-key="shippingRowKey"
      >
        <template #empty><NEmpty :description="shippingError ? '投诉候选加载失败' : '当前筛选范围内没有候选订单'" /></template>
      </NDataTable>
      <div v-if="shippingData" class="analytics-pager complaints-pager">
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

    <NCard v-else :bordered="false" class="analytics-table-card complaints-panel">
      <template #header>
        <div class="complaints-panel-header">
          <div>
            <h2><morph-icon icon="messageSquareAlert" size="18" stroke-width="1.8" />已收货纠纷</h2>
            <span>按店铺与退货申请编号独立保存人工处理信息</span>
          </div>
          <form class="complaints-filter" role="search" @submit.prevent="submitSearch">
            <NInput
              v-model:value="searchDraft"
              type="text"
              aria-label="搜索已收货纠纷"
              placeholder="搜索SKU、货号、订单号或退货申请编号…"
              @keydown.enter.prevent="submitSearch"
            >
              <template #prefix><morph-icon icon="search" size="15" stroke-width="1.8" /></template>
            </NInput>
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
        class="analytics-table complaints-table"
        :columns="receivedColumns"
        :data="receivedData?.items ?? []"
        :loading="receivedLoading"
        :pagination="false"
        :remote="true"
        :scroll-x="1170"
        :row-key="receivedRowKey"
      >
        <template #empty><NEmpty :description="receivedError ? '已收货纠纷加载失败' : '当前筛选范围内没有退货申请'" /></template>
      </NDataTable>
      <div v-if="receivedData" class="analytics-pager complaints-pager">
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

    <NModal v-model:show="shippingEditorShow" preset="card" class="complaints-modal" :style="{ width: 'min(720px, 92vw)' }" :mask-closable="!shippingSaving" :title="selectedShippingComplaint ? `编辑投诉 ${selectedShippingComplaint.complaint_number}` : `为 ${selectedShipping?.posting_number || ''} 新建投诉`">
      <p class="complaints-modal-subtitle">投诉编号、投诉时间和投诉渠道为必填项</p>
      <form class="complaints-form" @submit.prevent="submitShipping">
        <div class="complaints-form-grid">
          <label class="complaints-field">投诉编号<NInput v-model:value="shippingForm.complaintNumber" :readonly="Boolean(selectedShippingComplaint)" /></label>
          <label class="complaints-field">投诉时间<input v-model="shippingForm.complaintAt" class="complaints-native-input" type="datetime-local" required /></label>
          <label class="complaints-field">投诉渠道<NInput v-model:value="shippingForm.channel" placeholder="如：Ozon Support / 官方工单" /></label>
          <div class="complaints-field"><span>固定投诉截止日期</span><div class="complaints-readonly-field">{{ selectedShipping ? deadlineText(selectedShipping) : "—" }}</div></div>
          <label class="complaints-field">所在仓库<NInput v-model:value="shippingForm.warehouse" placeholder="如：中国前置仓 / 本地仓" /></label>
          <label class="complaints-field">订单处理状态<NInput v-model:value="shippingForm.orderProcessStatus" placeholder="如：已核实 / 待处理" /></label>
          <label class="complaints-field">投诉状态<NInput v-model:value="shippingForm.complaintStatus" placeholder="如：已受理 / 平台审核中" /></label>
          <label class="complaints-field">赔付状态<NInput v-model:value="shippingForm.compensationStatus" placeholder="如：已批准 / 待打款" /></label>
          <fieldset class="complaints-compensation">
            <legend>Ozon 平台赔偿</legend>
            <label class="complaints-field">平台赔偿金额（RUB）<NInputNumber v-model:value="shippingForm.platformCompensation" :min="0.01" :precision="2" placeholder="0.00" /></label>
            <label class="complaints-field">平台赔偿北京时间<input v-model="shippingForm.platformAt" class="complaints-native-input" type="datetime-local" /></label>
            <div class="complaints-compensation-result">{{ shippingPlatformConversion }}</div>
          </fieldset>
          <fieldset class="complaints-compensation">
            <legend>物流商赔偿</legend>
            <label class="complaints-field">物流商赔偿金额（CNY）<NInputNumber v-model:value="shippingForm.logisticsCompensation" :min="0.01" :precision="2" placeholder="0.00" /></label>
            <label class="complaints-field">物流商赔偿北京时间<input v-model="shippingForm.logisticsAt" class="complaints-native-input" type="datetime-local" /></label>
            <div class="complaints-compensation-result">{{ shippingLogisticsConversion }}</div>
          </fieldset>
          <label class="complaints-field">未收到退件<NSelect v-model:value="shippingForm.notReceivedReturn" :options="booleanOptions" /></label>
          <label class="complaints-field">是否完结<NSelect v-model:value="shippingForm.resolved" :options="booleanOptions" /></label>
          <label class="complaints-field complaints-notes">备注<NInput v-model:value="shippingForm.notes" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写处理备注…" /></label>
        </div>
        <div class="complaints-form-actions">
          <NButton type="primary" attr-type="submit" :loading="shippingSaving"><template #icon><morph-icon icon="check" size="14" stroke-width="2" /></template>保存</NButton>
          <NButton attr-type="button" :disabled="shippingSaving" @click="shippingEditorShow = false">取消</NButton>
        </div>
      </form>
    </NModal>

    <NModal v-model:show="receivedEditorShow" preset="card" class="complaints-modal" :style="{ width: 'min(720px, 92vw)' }" :mask-closable="!receivedSaving" title="编辑已收货纠纷">
      <p class="complaints-modal-subtitle">{{ selectedReceived ? `${selectedReceived.return_number} · ${selectedReceived.shop_name}` : "请选择一条退货申请" }}</p>
      <form class="complaints-form" @submit.prevent="submitReceived">
        <div class="complaints-form-grid">
          <div class="complaints-field"><span>固定投诉截止日期</span><div class="complaints-readonly-field">{{ selectedReceived ? deadlineText(selectedReceived) : "—" }}</div></div>
          <label class="complaints-field">是否退款<NSelect v-model:value="receivedForm.refundType" :options="refundTypeOptions" /></label>
          <label class="complaints-field">退款金额<NInputNumber v-model:value="receivedForm.refundAmount" :min="0" :precision="2" placeholder="0.00" /></label>
          <label class="complaints-field">退款币种<NInput v-model:value="receivedForm.refundCurrency" readonly /></label>
          <fieldset class="complaints-compensation">
            <legend>Ozon 平台赔偿</legend>
            <label class="complaints-field">平台赔偿金额（RUB）<NInputNumber v-model:value="receivedForm.platformCompensation" :min="0.01" :precision="2" placeholder="0.00" /></label>
            <label class="complaints-field">平台赔偿北京时间<input v-model="receivedForm.platformAt" class="complaints-native-input" type="datetime-local" /></label>
            <div class="complaints-compensation-result">{{ receivedPlatformConversion }}</div>
          </fieldset>
          <fieldset class="complaints-compensation">
            <legend>物流商赔偿</legend>
            <label class="complaints-field">物流商赔偿金额（CNY）<NInputNumber v-model:value="receivedForm.logisticsCompensation" :min="0.01" :precision="2" placeholder="0.00" /></label>
            <label class="complaints-field">物流商赔偿北京时间<input v-model="receivedForm.logisticsAt" class="complaints-native-input" type="datetime-local" /></label>
            <div class="complaints-compensation-result">{{ receivedLogisticsConversion }}</div>
          </fieldset>
          <label class="complaints-field">处理状态<NInput v-model:value="receivedForm.processStatus" placeholder="如：处理中 / 待核实 / 已完结" /></label>
          <label class="complaints-field">退货方式<NSelect v-model:value="receivedForm.returnMethod" :options="returnMethodOptions" /></label>
          <label class="complaints-field">IML退货单号<NInput v-model:value="receivedForm.imlReturnNumber" placeholder="IML 单号" /></label>
          <label class="complaints-field">IML系统SN<NInput v-model:value="receivedForm.imlSystemSn" placeholder="IML 系统序列号" /></label>
          <label class="complaints-field">买家邮寄追踪号<NInput v-model:value="receivedForm.buyerTrackingNumber" placeholder="买家寄出物流单号" /></label>
          <label class="complaints-field">处理方式<NSelect v-model:value="receivedForm.handlingMethod" :options="handlingMethodOptions" /></label>
          <label class="complaints-field">是否拍视频<NSelect v-model:value="receivedForm.videoRecorded" :options="booleanOptions" /></label>
          <label class="complaints-field">出库订单编号<NInput v-model:value="receivedForm.outboundOrderNumber" placeholder="关联出库单号" /></label>
          <label class="complaints-field">退件结果<NSelect v-model:value="receivedForm.returnResult" :options="returnResultOptions" /></label>
          <label class="complaints-field complaints-notes">备注<NInput v-model:value="receivedForm.notes" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写纠纷备注…" /></label>
        </div>
        <div class="complaints-form-actions">
          <NButton type="primary" attr-type="submit" :loading="receivedSaving"><template #icon><morph-icon icon="check" size="14" stroke-width="2" /></template>保存</NButton>
          <NButton attr-type="button" :disabled="receivedSaving" @click="receivedEditorShow = false">取消</NButton>
        </div>
      </form>
    </NModal>
  </section>
</template>
