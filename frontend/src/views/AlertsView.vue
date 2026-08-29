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
  NEmpty,
  NInput,
  NInputNumber,
  NPagination,
  NSelect,
  NSpin,
  NSwitch,
  NTag,
  useMessage,
} from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { acknowledgeAlert, evaluateAlerts, getAlertSummary, listAlertEvents, listAlertRules, updateAlertRule, type AlertRuleUpdate } from "../api/alerts";
import { getErrorMessage } from "../api/client";
import { useShop } from "../composables/useShop";
import type {
  AlertCategory,
  AlertEvent,
  AlertEventListResponse,
  AlertMetricValue,
  AlertRule,
  AlertRuleKey,
  AlertSeverity,
  AlertStatus,
  AlertSummary,
  ShopId,
  ShopSelection,
} from "../types/api";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../utils/format";
import { isShopSelection, positiveInteger, queryValue } from "../utils/query";

type AlertFilters = {
  shopId: ShopSelection;
  status: AlertStatus;
  severity: AlertSeverity | "";
  category: AlertCategory | "";
  search: string;
  page: number;
};
type SummaryTone = "warning" | "danger" | "peach" | "lavender" | "safe";
type SummaryCard = { icon: IconName; label: string; value: string; note: string; tone: SummaryTone };

const PAGE_SIZE = 50;
const route = useRoute();
const router = useRouter();
const message = useMessage();
const { selectedShopId, selectShop } = useShop();
const ruleShopId = ref<ShopId>(1);
const ruleShops: ShopId[] = [1, 2];

const statusOptions = [
  { label: "活动", value: "open" },
  { label: "已恢复", value: "resolved" },
  { label: "全部", value: "all" },
];
const severityOptions = [
  { label: "全部等级", value: "" },
  { label: "Critical", value: "critical" },
  { label: "High", value: "high" },
  { label: "Warning", value: "warning" },
];
const categoryOptions = [
  { label: "全部类型", value: "" },
  { label: "广告", value: "advertising" },
  { label: "库存", value: "inventory" },
  { label: "销售", value: "sales" },
];
const severityLabels: Record<AlertSeverity, string> = { critical: "Critical", high: "High", warning: "Warning" };
const categoryLabels: Record<AlertCategory, string> = { advertising: "广告", inventory: "库存", sales: "销售" };
const fieldLabels: Record<string, string> = {
  baseline_days: "基准周期",
  minimum_baseline_days: "最少基准天数",
  increase_percent: "增长超过",
  minimum_current_spend_rub: "最低当前花费",
  window_days: "统计周期",
  threshold_drr: "DRR阈值",
  minimum_spend_rub: "最低花费",
  minimum_clicks: "最低点击数",
  drop_percent: "下降超过",
  minimum_baseline_orders_per_day: "最低基准订单/天",
  minimum_spend_ratio: "最低花费比例",
  minimum_baseline_units_per_day: "最低基准销量/天",
};
const fieldUnits: Record<string, string> = {
  baseline_days: "天",
  minimum_baseline_days: "天",
  increase_percent: "%",
  minimum_current_spend_rub: "RUB",
  window_days: "天",
  threshold_drr: "%",
  minimum_spend_rub: "RUB",
  minimum_clicks: "次",
  drop_percent: "%",
  minimum_baseline_orders_per_day: "单/天",
  minimum_spend_ratio: "倍",
  minimum_baseline_units_per_day: "件/天",
};
const integerFields = new Set(["baseline_days", "minimum_baseline_days", "window_days", "minimum_clicks"]);

function isAlertStatus(value: string): value is AlertStatus {
  return value === "open" || value === "resolved" || value === "all";
}

function isAlertSeverity(value: string): value is AlertSeverity {
  return value === "critical" || value === "high" || value === "warning";
}

function isAlertCategory(value: string): value is AlertCategory {
  return value === "advertising" || value === "inventory" || value === "sales";
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): AlertFilters {
  const shop = queryValue(query, "shop_id");
  const status = queryValue(query, "status");
  const severity = queryValue(query, "severity");
  const category = queryValue(query, "category");
  return {
    shopId: isShopSelection(shop) ? Number(shop) as ShopSelection : fallbackShop,
    status: isAlertStatus(status) ? status : "open",
    severity: isAlertSeverity(severity) ? severity : "",
    category: isAlertCategory(category) ? category : "",
    search: queryValue(query, "q").trim(),
    page: positiveInteger(queryValue(query, "page"), 1),
  };
}

const initialFilters = parseFilters(route.query, selectedShopId.value);
const filters = reactive<AlertFilters>(initialFilters);
const searchDraft = ref(initialFilters.search);
const summary = ref<AlertSummary | null>(null);
const eventsData = ref<AlertEventListResponse | null>(null);
const rules = ref<AlertRule[]>([]);
const summaryLoading = ref(false);
const eventsLoading = ref(false);
const rulesLoading = ref(false);
const summaryError = ref("");
const eventsError = ref("");
const rulesError = ref("");
const evaluating = ref(false);
const acknowledgingId = ref<number | null>(null);
const ruleSavingKey = ref<AlertRuleKey | null>(null);
let summaryRequestId = 0;
let eventsRequestId = 0;
let rulesRequestId = 0;
let evaluateRequestId = 0;
let acknowledgeRequestId = 0;
let ruleSaveId = 0;
let routeReady = false;
let mounted = false;
let ignoreNextShopChange = false;
let skipNextRouteLoad = false;

const summaryCards = computed<SummaryCard[]>(() => {
  const data = summary.value;
  if (!data) return [];
  return [
    {
      icon: "alertTriangle",
      label: "活动预警",
      value: formatInteger(data.active),
      tone: data.active ? "warning" : "safe",
      note: "当前尚未自动恢复的异常",
    },
    {
      icon: "shieldAlert",
      label: "严重 / 高风险",
      value: formatInteger(data.critical + data.high),
      tone: data.critical || data.high ? "danger" : "safe",
      note: `Critical ${formatInteger(data.critical)} · High ${formatInteger(data.high)}`,
    },
    {
      icon: "activity",
      label: "广告异常",
      value: formatInteger(data.advertising),
      tone: data.advertising ? "peach" : "safe",
      note: "花费、DRR、点击与订单规则",
    },
    {
      icon: "stock",
      label: "库存 / 销售异常",
      value: formatInteger(data.inventory + data.sales),
      tone: data.inventory || data.sales ? "lavender" : "safe",
      note: `库存 ${formatInteger(data.inventory)} · 销售 ${formatInteger(data.sales)}`,
    },
  ];
});
const currentRules = computed(() => rules.value.filter((rule) => rule.shop_id === ruleShopId.value));
const eventPageCount = computed(() => Math.max(1, Math.ceil((eventsData.value?.total ?? 0) / (eventsData.value?.size || PAGE_SIZE))));

function queryFor(value: AlertFilters): Record<string, string> {
  const query: Record<string, string> = { shop_id: String(value.shopId) };
  if (value.status !== "open") query.status = value.status;
  if (value.severity) query.severity = value.severity;
  if (value.category) query.category = value.category;
  if (value.search.trim()) query.q = value.search.trim();
  if (value.page !== 1) query.page = String(value.page);
  return query;
}

function queryMatches(query: LocationQuery, value: AlertFilters): boolean {
  const expected = queryFor(value);
  const keys = new Set([...Object.keys(query), ...Object.keys(expected)]);
  return [...keys].every((key) => queryValue(query, key) === (expected[key] ?? ""));
}

function applyRouteQuery(query: LocationQuery, fallbackShop: ShopSelection): AlertFilters {
  const next = parseFilters(query, fallbackShop);
  Object.assign(filters, next);
  searchDraft.value = next.search;
  if (selectedShopId.value !== next.shopId) {
    ignoreNextShopChange = true;
    selectShop(next.shopId);
  }
  return next;
}

function currentFilters(): AlertFilters {
  return { ...filters };
}

function updateRoute(next: AlertFilters, replace = false): void {
  const previousShop = filters.shopId;
  const normalized = { ...next, search: next.search.trim() };
  Object.assign(filters, normalized);
  searchDraft.value = normalized.search;
  if (previousShop !== normalized.shopId) void loadSummary(normalized.shopId);
  if (queryMatches(route.query, normalized)) {
    void loadEvents(normalized);
    return;
  }
  void (replace ? router.replace({ query: queryFor(normalized) }) : router.push({ query: queryFor(normalized) }));
}

async function loadSummary(shopId: ShopSelection): Promise<void> {
  const currentRequest = ++summaryRequestId;
  summaryLoading.value = true;
  summaryError.value = "";
  summary.value = null;
  try {
    const data = await getAlertSummary(shopId);
    if (currentRequest !== summaryRequestId) return;
    summary.value = data;
  } catch (cause) {
    if (currentRequest !== summaryRequestId) return;
    summaryError.value = getErrorMessage(cause);
    message.error(summaryError.value);
  } finally {
    if (currentRequest === summaryRequestId) summaryLoading.value = false;
  }
}

async function loadEvents(queryFilters: AlertFilters): Promise<void> {
  const currentRequest = ++eventsRequestId;
  eventsLoading.value = true;
  eventsError.value = "";
  eventsData.value = null;
  try {
    const data = await listAlertEvents({
      shopId: queryFilters.shopId,
      status: queryFilters.status,
      severity: queryFilters.severity || undefined,
      category: queryFilters.category || undefined,
      search: queryFilters.search || undefined,
      page: queryFilters.page,
      size: PAGE_SIZE,
    });
    if (currentRequest !== eventsRequestId) return;
    const responsePageCount = Math.max(1, Math.ceil(data.total / (data.size || PAGE_SIZE)));
    if (queryFilters.page > responsePageCount) {
      await router.replace({ query: queryFor({ ...queryFilters, page: responsePageCount }) });
      return;
    }
    eventsData.value = data;
  } catch (cause) {
    if (currentRequest !== eventsRequestId) return;
    eventsError.value = getErrorMessage(cause);
    message.error(eventsError.value);
  } finally {
    if (currentRequest === eventsRequestId) eventsLoading.value = false;
  }
}

async function loadRules(): Promise<void> {
  const currentRequest = ++rulesRequestId;
  rulesLoading.value = true;
  rulesError.value = "";
  rules.value = [];
  try {
    const data = await listAlertRules(0);
    if (currentRequest !== rulesRequestId) return;
    rules.value = data;
  } catch (cause) {
    if (currentRequest !== rulesRequestId) return;
    rulesError.value = getErrorMessage(cause);
    message.error(rulesError.value);
  } finally {
    if (currentRequest === rulesRequestId) rulesLoading.value = false;
  }
}

function loadAll(value: AlertFilters): void {
  void Promise.allSettled([loadSummary(value.shopId), loadEvents(value), loadRules()]);
}

function submitSearch(): void {
  updateRoute({ ...currentFilters(), search: searchDraft.value, page: 1 });
}

function changeStatus(value: string | number | null): void {
  const status = typeof value === "string" && isAlertStatus(value) ? value : "open";
  updateRoute({ ...currentFilters(), status, page: 1 });
}

function changeSeverity(value: string | number | null): void {
  const severity = typeof value === "string" && isAlertSeverity(value) ? value : "";
  updateRoute({ ...currentFilters(), severity, page: 1 });
}

function changeCategory(value: string | number | null): void {
  const category = typeof value === "string" && isAlertCategory(value) ? value : "";
  updateRoute({ ...currentFilters(), category, page: 1 });
}

function changePage(page: number): void {
  if (page !== filters.page) updateRoute({ ...currentFilters(), page });
}

function retrySummary(): void {
  void loadSummary(filters.shopId);
}

function retryEvents(): void {
  void loadEvents(currentFilters());
}

function retryRules(): void {
  void loadRules();
}

function changeRuleShop(shopId: ShopId): void {
  if (ruleShopId.value === shopId) return;
  ruleShopId.value = shopId;
  void loadRules();
}

async function runEvaluate(): Promise<void> {
  if (evaluating.value) return;
  const currentRequest = ++evaluateRequestId;
  evaluating.value = true;
  try {
    const result = await evaluateAlerts(filters.shopId);
    if (currentRequest !== evaluateRequestId || !mounted) return;
    message.success(`检查完成：新增 ${formatInteger(result.triggered)} 条，恢复 ${formatInteger(result.resolved)} 条`);
    const current = currentFilters();
    await Promise.allSettled([loadSummary(current.shopId), loadEvents(current), loadRules()]);
  } catch (cause) {
    if (currentRequest === evaluateRequestId && mounted) message.error(getErrorMessage(cause));
  } finally {
    if (currentRequest === evaluateRequestId) evaluating.value = false;
  }
}

async function acknowledgeRow(row: AlertEvent): Promise<void> {
  if (acknowledgingId.value !== null) return;
  const currentRequest = ++acknowledgeRequestId;
  acknowledgingId.value = row.id;
  try {
    await acknowledgeAlert(row.id);
    if (currentRequest !== acknowledgeRequestId || !mounted) return;
    message.success("预警已标记为已读");
    const current = currentFilters();
    await Promise.allSettled([loadSummary(current.shopId), loadEvents(current)]);
  } catch (cause) {
    if (currentRequest === acknowledgeRequestId && mounted) message.error(getErrorMessage(cause));
  } finally {
    if (currentRequest === acknowledgeRequestId) acknowledgingId.value = null;
  }
}

function updateRuleConfig(rule: AlertRule, key: string, value: number | null): void {
  rule.config[key] = value ?? 0;
}

function updateRuleEnabled(rule: AlertRule, value: boolean): void {
  rule.enabled = value;
}

function updateRuleNotify(rule: AlertRule, value: boolean): void {
  rule.notify_dingtalk = value;
}

function fieldLabel(key: string): string {
  return fieldLabels[key] || key;
}

function fieldUnit(key: string): string {
  return fieldUnits[key] || "";
}

function fieldStep(key: string): number {
  return integerFields.has(key) ? 1 : 0.01;
}

async function saveRule(rule: AlertRule): Promise<void> {
  if (ruleSavingKey.value !== null) return;
  const currentSave = ++ruleSaveId;
  ruleSavingKey.value = rule.rule_key;
  const body: AlertRuleUpdate = {
    shop_id: rule.shop_id,
    enabled: rule.enabled,
    notify_dingtalk: rule.notify_dingtalk,
    config: { ...rule.config },
  };
  try {
    await updateAlertRule(rule.rule_key, body);
    if (currentSave !== ruleSaveId || !mounted) return;
    message.success("预警规则已保存");
    await loadRules();
  } catch (cause) {
    if (currentSave === ruleSaveId && mounted) message.error(getErrorMessage(cause));
  } finally {
    if (currentSave === ruleSaveId) ruleSavingKey.value = null;
  }
}

function metricNumber(value: AlertMetricValue | undefined, digits = 2): string {
  if (typeof value !== "number" && typeof value !== "string") return "—";
  const number = Number(value);
  return Number.isFinite(number) ? formatNumber(number, digits) : "—";
}

function metricLine(row: AlertEvent): string {
  const metrics = row.metrics;
  switch (row.rule_key) {
    case "ad_spend_spike":
      return `当前 ${metricNumber(metrics.current_spend_rub)} RUB · 基准 ${metricNumber(metrics.baseline_spend_rub)} RUB · 增幅 ${metricNumber(metrics.increase_percent, 1)}%`;
    case "ad_drr_high":
      return `花费 ${metricNumber(metrics.spend_window_rub ?? metrics.spend_3d)} RUB · 销售 ${metricNumber(metrics.revenue_window_rub ?? metrics.revenue_3d)} RUB · DRR ${metricNumber(metrics.drr, 1)}% / ${metricNumber(metrics.threshold_drr, 1)}%`;
    case "ad_clicks_no_orders":
      return `点击 ${metricNumber(metrics.clicks, 0)} · 花费 ${metricNumber(metrics.spend_rub)} RUB · 订单 0`;
    case "ad_orders_drop":
      return `当日 ${metricNumber(metrics.current_orders, 0)} 单 · 基准 ${metricNumber(metrics.baseline_orders_per_day)} 单/天 · 下降 ${metricNumber(metrics.drop_percent, 1)}%`;
    case "inventory_risk":
      return `FBP有效库存 ${metricNumber(metrics.effective_stock, 0)} · 预测日销（FBP+realFBS） ${metricNumber(metrics.forecast_daily)} · FBP可售 ${metricNumber(metrics.days_cover)} 天`;
    case "sales_drop":
      return `核心渠道昨日 ${metricNumber(metrics.current_units, 0)} 件 · 基准 ${metricNumber(metrics.baseline_units_per_day)} 件/天 · 下降 ${metricNumber(metrics.drop_percent, 1)}%`;
  }
}

function severityType(value: AlertSeverity): "error" | "warning" | "info" {
  if (value === "critical") return "error";
  if (value === "high") return "warning";
  return "info";
}

function renderSeverity(row: AlertEvent): VNodeChild {
  return h(NTag, { size: "small", round: true, bordered: false, type: severityType(row.severity) }, {
    default: () => severityLabels[row.severity],
  });
}

function renderStatus(row: AlertEvent): VNodeChild {
  return h("div", { class: "alerts-status-cell" }, [
    h(NTag, { size: "small", round: true, bordered: false, type: row.status === "open" ? "error" : "success" }, {
      default: () => `${row.status === "open" ? "活动" : "已恢复"}${row.acknowledged_at ? " · 已读" : ""}`,
    }),
    row.last_notify_error ? h("small", { class: "alerts-notify-error" }, row.last_notify_error) : null,
  ]);
}

const eventColumns: DataTableColumns<AlertEvent> = [
  { key: "severity", title: "等级", width: 92, render: renderSeverity },
  {
    key: "object",
    title: "类型 / 对象",
    minWidth: 180,
    render: (row) => h("div", { class: "alerts-object-cell" }, [h("strong", row.rule_label), h("small", row.object_name || row.entity_id)]),
  },
  { key: "shop", title: "店铺", width: 110, render: (row) => h("span", { class: "alerts-shop-badge" }, row.shop_name) },
  { key: "message", title: "触发原因", minWidth: 280, render: (row) => h("div", { class: "alerts-reason-cell" }, row.message || "—") },
  { key: "metrics", title: "当前值 / 阈值", minWidth: 260, render: (row) => h("small", { class: "alerts-metric-line" }, metricLine(row)) },
  { key: "first_seen_at", title: "首次发现", width: 160, render: (row) => formatBeijingDateTime(row.first_seen_at) },
  { key: "last_seen_at", title: "最近发现", width: 160, render: (row) => formatBeijingDateTime(row.last_seen_at) },
  { key: "status", title: "状态", minWidth: 150, render: renderStatus },
  {
    key: "action",
    title: "操作",
    width: 100,
    align: "right",
    render: (row) => row.status === "open" && !row.acknowledged_at
      ? h(NButton, {
          size: "small",
          type: "primary",
          secondary: true,
          loading: acknowledgingId.value === row.id,
          disabled: acknowledgingId.value !== null && acknowledgingId.value !== row.id,
          onClick: () => void acknowledgeRow(row),
        }, {
          icon: () => h(MorphIcon, { icon: "check", size: "12", strokeWidth: "2" }),
          default: () => "已读",
        })
      : "—",
  },
];

watch(() => route.fullPath, () => {
  if (!routeReady) return;
  if (skipNextRouteLoad) {
    skipNextRouteLoad = false;
    return;
  }
  const previousShop = filters.shopId;
  const next = applyRouteQuery(route.query, selectedShopId.value);
  if (previousShop !== next.shopId) void loadSummary(next.shopId);
  void loadEvents(next);
});

watch(selectedShopId, (shopId) => {
  if (ignoreNextShopChange) {
    ignoreNextShopChange = false;
    return;
  }
  if (!routeReady || filters.shopId === shopId) return;
  updateRoute({ ...currentFilters(), shopId, page: 1 });
});

onMounted(() => {
  mounted = true;
  const next = applyRouteQuery(route.query, selectedShopId.value);
  routeReady = true;
  if (!queryMatches(route.query, next)) {
    skipNextRouteLoad = true;
    void router.replace({ query: queryFor(next) }).catch(() => {
      skipNextRouteLoad = false;
    });
  }
  loadAll(next);
});

onBeforeUnmount(() => {
  mounted = false;
  summaryRequestId += 1;
  eventsRequestId += 1;
  rulesRequestId += 1;
  evaluateRequestId += 1;
  acknowledgeRequestId += 1;
  ruleSaveId += 1;
});
</script>

<template>
  <section class="alerts-view">
    <div v-if="summaryCards.length" class="alerts-summary">
      <NCard v-for="card in summaryCards" :key="card.label" :bordered="false" class="alerts-summary-card" :class="`alerts-tone-${card.tone}`">
        <div class="alerts-summary-head"><span>{{ card.label }}</span><span class="alerts-summary-icon"><morph-icon :icon="card.icon" size="18" stroke-width="1.8" /></span></div>
        <strong>{{ card.value }}</strong>
        <small>{{ card.note }}</small>
      </NCard>
    </div>
    <div v-else-if="summaryLoading" class="alerts-summary-loading"><NSpin size="small" /> <span>预警汇总加载中…</span></div>
    <NAlert v-if="summaryError" type="error" class="alerts-error" :title="summaryError">
      <div class="alerts-error-content"><span>预警汇总未更新，请重试。</span><NButton size="small" @click="retrySummary">重试</NButton></div>
    </NAlert>

    <NCard :bordered="false" class="alerts-panel">
      <template #header>
        <div class="alerts-panel-header">
          <div>
            <h2><morph-icon icon="alertTriangle" size="18" stroke-width="1.8" />异常预警</h2>
            <span>只基于已同步到本地 SQLite 的数据；数据过期时会跳过判断</span>
          </div>
          <NButton type="primary" :loading="evaluating" @click="runEvaluate">
            <template #icon><morph-icon icon="refreshCw" size="14" stroke-width="2" /></template>
            {{ evaluating ? "检查中…" : "立即检查" }}
          </NButton>
        </div>
      </template>

      <form class="alerts-filter" role="search" @submit.prevent="submitSearch">
        <NInput v-model:value="searchDraft" type="text" aria-label="搜索预警" placeholder="搜索 Campaign、SKU 或商品名称…" @keydown.enter.prevent="submitSearch">
          <template #prefix><morph-icon icon="search" size="15" stroke-width="1.8" /></template>
        </NInput>
        <NSelect :value="filters.status" :options="statusOptions" aria-label="预警状态筛选" @update:value="changeStatus" />
        <NSelect :value="filters.severity" :options="severityOptions" aria-label="预警等级筛选" @update:value="changeSeverity" />
        <NSelect :value="filters.category" :options="categoryOptions" aria-label="预警类型筛选" @update:value="changeCategory" />
        <NButton type="primary" attr-type="submit" :loading="eventsLoading">
          <template #icon><morph-icon icon="search" size="13" stroke-width="2" /></template>
          查询
        </NButton>
      </form>

      <NAlert v-if="eventsError" type="error" class="alerts-error" :title="eventsError">
        <div class="alerts-error-content"><span>预警列表未更新，请重试。</span><NButton size="small" @click="retryEvents">重试</NButton></div>
      </NAlert>
      <div class="alerts-table-meta"><span>共 {{ formatInteger(eventsData?.total ?? 0) }} 条预警</span><span v-if="eventsLoading" class="alerts-loading-label">正在加载…</span></div>
      <NDataTable
        class="alerts-table"
        :columns="eventColumns"
        :data="eventsData?.items ?? []"
        :loading="eventsLoading"
        :pagination="false"
        :remote="true"
        :scroll-x="1240"
        :row-key="(row: AlertEvent) => row.id"
      >
        <template #empty><NEmpty :description="eventsError ? '预警列表加载失败' : '当前筛选范围内暂无预警'" /></template>
      </NDataTable>
      <div v-if="eventsData" class="alerts-pager">
        <span>第 {{ filters.page }} / {{ eventPageCount }} 页，共 {{ formatInteger(eventsData.total) }} 条</span>
        <NPagination :page="filters.page" :page-count="eventPageCount" :page-size="PAGE_SIZE" :disabled="eventsLoading" :page-slot="7" @update:page="changePage" />
      </div>
    </NCard>

    <NCard :bordered="false" class="alerts-panel alerts-rules-panel">
      <template #header>
        <div class="alerts-panel-header">
          <div>
            <h2><morph-icon icon="sliders" size="18" stroke-width="1.8" />预警规则</h2>
            <span>两个店铺分别设置；保存后仅影响后续检查</span>
          </div>
          <div class="alerts-rule-shop-tabs" role="tablist" aria-label="预警规则店铺">
            <NButton
              v-for="shop in ruleShops"
              :key="shop"
              size="small"
              attr-type="button"
              role="tab"
              :aria-selected="ruleShopId === shop"
              :type="ruleShopId === shop ? 'primary' : 'default'"
              :secondary="ruleShopId !== shop"
              @click="changeRuleShop(shop)"
            >
              Shop {{ shop }}
            </NButton>
          </div>
        </div>
      </template>

      <NAlert v-if="rulesError" type="error" class="alerts-error" :title="rulesError">
        <div class="alerts-error-content"><span>预警规则未更新，请重试。</span><NButton size="small" @click="retryRules">重试</NButton></div>
      </NAlert>
      <div v-if="rulesLoading" class="alerts-loading-state"><NSpin size="small" /><span>预警规则加载中…</span></div>
      <div v-else-if="currentRules.length" class="alerts-rules-list">
        <article v-for="rule in currentRules" :key="rule.rule_key" class="alerts-rule-card">
          <div class="alerts-rule-head">
            <div class="alerts-rule-title"><strong>{{ rule.label }}</strong><NTag size="small" round :bordered="false" type="default">{{ categoryLabels[rule.category] }}</NTag></div>
            <div class="alerts-rule-switches">
              <label><NSwitch :value="rule.enabled" :disabled="ruleSavingKey !== null" @update:value="updateRuleEnabled(rule, $event)" />启用</label>
              <label><NSwitch :value="rule.notify_dingtalk" :disabled="ruleSavingKey !== null" @update:value="updateRuleNotify(rule, $event)" />钉钉</label>
            </div>
          </div>
          <div v-if="Object.keys(rule.config).length" class="alerts-rule-fields">
            <label v-for="key in Object.keys(rule.config)" :key="key">
              <span>{{ fieldLabel(key) }}</span>
              <div>
                <NInputNumber :value="rule.config[key]" :min="0" :step="fieldStep(key)" :disabled="ruleSavingKey !== null" @update:value="updateRuleConfig(rule, key, $event)" />
                <small>{{ fieldUnit(key) }}</small>
              </div>
            </label>
          </div>
          <p v-else class="alerts-rule-note">复用库存预测结果：仅提醒缺货与到货前缺货风险。</p>
          <div class="alerts-rule-foot">
            <span>{{ rule.notify_dingtalk ? "未配置钉钉时仍保留站内预警" : "当前不发送钉钉" }}</span>
            <NButton type="primary" size="small" :loading="ruleSavingKey === rule.rule_key" :disabled="ruleSavingKey !== null" @click="saveRule(rule)">保存</NButton>
          </div>
        </article>
      </div>
      <NEmpty v-else description="暂无规则配置" />
    </NCard>
  </section>
</template>
