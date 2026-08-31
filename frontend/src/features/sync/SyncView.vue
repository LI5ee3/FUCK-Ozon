<script setup lang="ts">
import DatePresetPills from "../../shared/components/DatePresetPills.vue";
import "../../styles/analytics.css";
import "./sync.css";
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, type VNodeChild } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import SyncSummaryCards from "./components/SyncSummaryCards.vue";
import type { IconName } from "../../shared/icons/tabler";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDatePicker,
  NInputNumber,
  NProgress,
  NSelect,
  NSpin,
  NSwitch,
  NTag,
  useDialog,
  useMessage,
} from "naive-ui";
import EmptyState from "../../shared/components/EmptyState.vue";
import type { DataTableColumns } from "naive-ui";
import { getErrorMessage } from "../../shared/api/client";
import {
  getAutoSyncSettings,
  getExchangeRateStatus,
  getSyncRun,
  getSyncRuns,
  startSync,
  syncExchangeRates,
  syncPerformanceCampaigns,
  syncPerformanceStatistics,
  updateAutoSyncSettings,
} from "./api";
import { useShop } from "../../shared/composables/useShop";
import type {
  AutoSyncModule,
  AutoSyncSetting,
  AutoSyncSettingsPayload,
  ExchangeRateStatus,
  ManualSyncModule,
  SyncRun,
} from "./types";
import type { ShopId } from "../../shared/types/common";
import {
  beijingThreeMonthRange,
  beijingToday,
  moscowToday,
  parseValidDateRange,
  standardDatePresetRange,
  type DateRange,
  type StandardDatePreset,
} from "../../shared/utils/date";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../../shared/utils/format";

type DatePreset = StandardDatePreset;
type SummaryTone = "azure" | "peach" | "mint" | "lavender";
type MacaronTone = "azure" | "lavender" | "mint" | "peach" | "butter";
type AutoDraft = { enabled: boolean; interval_hours: number; range_days: number };

const shopIds: ShopId[] = [1, 2];
const datePresets: ReadonlyArray<{ key: DatePreset; label: string }> = [
  { key: "today", label: "今天" },
  { key: "3days", label: "3天内" },
  { key: "7days", label: "7天内" },
  { key: "3months", label: "近三个月" },
  { key: "all", label: "全部时间" },
];
const intervalOptions = [1, 2, 3, 4, 6, 8, 12, 24].map((value) => ({
  label: `${value} 小时`,
  value,
}));
const autoModules: ReadonlyArray<{ module: AutoSyncModule; label: string; icon: IconName }> = [
  { module: "orders", label: "订单", icon: "shoppingBag" },
  { module: "returns", label: "退货", icon: "rotateCcw" },
  { module: "stock", label: "库存", icon: "stock" },
  { module: "ad_campaign_daily", label: "广告日统计", icon: "barChart" },
  { module: "ad_sku_daily", label: "SKU 广告统计", icon: "tag" },
];
const manualModules: ReadonlyArray<{
  module: ManualSyncModule;
  label: string;
  description: string;
  hint: string;
  icon: IconName;
}> = [
  { module: "orders", label: "订单数据", description: "拉取订单、商品明细及订单状态数据", hint: "受顶部时间范围影响", icon: "shoppingBag" },
  { module: "returns", label: "退货数据", description: "拉取退货与客户售后申请记录", hint: "受顶部时间范围影响", icon: "rotateCcw" },
  { module: "stock", label: "实时库存", description: "拉取当前全量现货与快照数据", hint: "全量快照 · 实时", icon: "stock" },
  { module: "ad_campaigns", label: "广告 Campaign", description: "读取 Performance API Campaign 元数据并同步到本地", hint: "Performance API · 只读", icon: "barChart" },
  { module: "ad_campaign_daily", label: "广告日统计", description: "同步 Campaign × 日期的曝光、点击、花费与订单", hint: "建议最近 7 天 · 只读", icon: "barChart" },
  { module: "ad_sku_daily", label: "SKU 广告统计", description: "同步 SKU 广告表现；Ozon 接口当前只支持今天或昨天", hint: "今天 / 昨天 · 只读", icon: "tag" },
];
const syncNames: Record<ManualSyncModule, string> = {
  orders: "订单",
  returns: "退货",
  stock: "库存",
  ad_campaigns: "广告 Campaign",
  ad_campaign_daily: "广告日统计",
  ad_sku_daily: "SKU广告统计",
};

const message = useMessage();
const dialog = useDialog();
const { shops, selectedShopId } = useShop();
const syncRuns = ref<SyncRun[]>([]);
const exchange = ref<ExchangeRateStatus | null>(null);
const autoSettings = ref<AutoSyncSetting[]>([]);
const manualRange = ref<DateRange>(standardDatePresetRange("7days", moscowToday()));
const exchangeRange = ref<DateRange>(beijingThreeMonthRange());
const historyLoading = ref(false);
const historyError = ref("");
const autoLoading = ref(false);
const autoError = ref("");
const autoSaving = ref(false);
const exchangeLoading = ref(false);
const exchangeError = ref("");
const exchangeSyncing = ref(false);
const manualSyncing = reactive<Record<ManualSyncModule, boolean>>({
  orders: false,
  returns: false,
  stock: false,
  ad_campaigns: false,
  ad_campaign_daily: false,
  ad_sku_daily: false,
});
const autoDraft = reactive<Record<ShopId, Record<AutoSyncModule, AutoDraft>>>({
  1: createAutoDraft(),
  2: createAutoDraft(),
});

let viewActive = false;
let historyRequestId = 0;
let autoRequestId = 0;
let exchangeRequestId = 0;
let autoSaveChain: Promise<void> = Promise.resolve();
const pollTimers = new Map<number, () => void>();

const selectedShopName = computed(() => {
  if (selectedShopId.value === 0) return "两店铺合并";
  return shopName(selectedShopId.value);
});
const manualShopHint = computed(() => selectedShopId.value === 0
  ? "请先在右上角选择一个店铺"
  : `当前店铺：${selectedShopName.value}`);
const manualActivePreset = computed<DatePreset | "">(() => findActivePreset(manualRange.value, moscowToday()));
const exchangeActivePreset = computed<DatePreset | "">(() => findActivePreset(exchangeRange.value, beijingToday()));
const enabledCount = computed(() => autoSettings.value.filter((row) => Boolean(row.enabled)).length);
const failedCount = computed(() => syncRuns.value.filter((row) => row.status === "failed").length);
const lastSuccess = computed(() => syncRuns.value.find((row) => row.status === "success") ?? null);
const summaryLoading = computed(() => historyLoading.value || autoLoading.value || exchangeLoading.value);
const summaryReady = computed(() => Boolean(syncRuns.value.length || autoSettings.value.length || exchange.value));
const summaryCards = computed<Array<{ icon: IconName; label: string; value: string; note: string; tone: SummaryTone }>>(() => {
  if (!summaryReady.value) return [];
  return [
  {
    icon: "sync",
    label: "自动拉取配置",
    value: `${enabledCount.value} / 10 项启用`,
    note: "两店铺五大模块独立定时调度",
    tone: "azure" as SummaryTone,
  },
  {
    icon: "checkCircle",
    label: "最近成功拉取",
    value: lastSuccess.value ? `${formatInteger(lastSuccess.value.records)} 条记录` : "暂无记录",
    note: lastSuccess.value
      ? `${lastSuccess.value.shop_name} · ${moduleLabel(lastSuccess.value.module)} · ${formatBeijingDateTime(lastSuccess.value.started_at)}`
      : "等待同步完成",
    tone: "mint" as SummaryTone,
  },
  {
    icon: "trendingUp",
    label: "用于销售汇率",
    value: `${rateValue("USD", "sales_exchange_rate")} USD/RUB`,
    note: `CNY/RUB ${rateValue("CNY", "sales_exchange_rate")}`,
    tone: "lavender" as SummaryTone,
  },
  {
    icon: failedCount.value > 0 ? "alertTriangle" : "shieldCheck",
    label: "同步异常与告警",
    value: failedCount.value > 0 ? `${failedCount.value} 次失败` : "运行健康",
    note: failedCount.value > 0 ? "发生同步异常时自动推送钉钉告警" : "最近 10 次拉取任务运行正常",
    tone: failedCount.value > 0 ? "peach" as SummaryTone : "azure" as SummaryTone,
  },
  ];
});
const exchangeLastSuccess = computed(() => exchangeLoading.value ? "加载中…" : formatBeijingDateTime(exchange.value?.last_success_at));
const exchangeDataThrough = computed(() => exchangeLoading.value ? "加载中…" : formatBeijingDateTime(exchange.value?.data_through));
const historyEmptyDescription = computed(() => {
  if (historyLoading.value) return "拉取记录加载中…";
  if (historyError.value) return "拉取记录加载失败";
  return "暂无拉取记录";
});

const historyColumns: DataTableColumns<SyncRun> = [
  {
    title: "所属店铺",
    key: "shop_name",
    width: 150,
    render: (row) => h("div", { class: "sync-history-shop" }, [
      h(MorphIcon, { icon: "store", size: "15", strokeWidth: "1.8" }),
      h("strong", row.shop_name),
    ]),
  },
  {
    title: "同步模块与来源",
    key: "module",
    width: 190,
    render: (row) => h("div", { class: "sync-history-module" }, [
      h("strong", moduleLabel(row.module)),
      renderStatusTag(row.run_source === "auto" ? "自动" : "手动", row.run_source === "auto" ? "mint" : "", "small"),
    ]),
  },
  {
    title: "状态与分段进度",
    key: "status",
    width: 270,
    render: renderRunStatus,
  },
  {
    title: "开始时间",
    key: "started_at",
    width: 150,
    render: (row) => h("span", { class: "sync-history-time" }, formatBeijingDateTime(row.started_at)),
  },
  {
    title: "执行详情 / 错误",
    key: "error",
    width: 220,
    render: (row) => h("span", {
      class: row.error ? "sync-history-error" : "sync-history-detail",
      title: row.error ?? undefined,
    }, row.error || successDetail(row)),
  },
];

function findActivePreset(range: DateRange, today: string): DatePreset | "" {
  return datePresets.find((preset) => {
    const candidate = standardDatePresetRange(preset.key, today);
    return candidate[0] === range[0] && candidate[1] === range[1];
  })?.key ?? "";
}

function createAutoDraft(): Record<AutoSyncModule, AutoDraft> {
  return {
    orders: { enabled: false, interval_hours: 24, range_days: 1 },
    returns: { enabled: false, interval_hours: 24, range_days: 1 },
    stock: { enabled: false, interval_hours: 24, range_days: 1 },
    ad_campaign_daily: { enabled: false, interval_hours: 24, range_days: 1 },
    ad_sku_daily: { enabled: false, interval_hours: 24, range_days: 1 },
  };
}

function shopName(shopId: ShopId | 0): string {
  return shops.value.find((shop) => shop.id === shopId)?.name ?? `店铺 ${shopId}`;
}

function moduleLabel(module: string): string {
  return syncNames[module as ManualSyncModule] ?? module;
}

function rateValue(
  currency: "USD" | "CNY",
  kind: "service_penalty_exchange_rate" | "sales_exchange_rate" = "sales_exchange_rate",
): string {
  const raw = exchange.value?.rates[currency]?.[kind];
  if (raw == null || raw === "") return "暂无";
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? formatNumber(value, 4) : "暂无";
}

function successDetail(row: SyncRun): string {
  return row.status === "success" ? `共拉取 ${formatInteger(row.records)} 条记录` : "—";
}

function runStatusTone(status: string): MacaronTone | "" {
  if (status === "success") return "mint";
  if (status === "failed") return "peach";
  if (status === "running") return "lavender";
  return "";
}

// Macaron tone mapping (DESIGN.md §colors.tones): mint = 成功/自动调度,
// peach = 失败, lavender = 进行中; no shell = 描述性标签.
function renderStatusTag(label: string, tone: MacaronTone | "", size: "small" | "medium" = "medium"): VNodeChild {
  return h(NTag, {
    size,
    bordered: false,
    type: "default",
    class: tone ? `sync-tone-tag--${tone}` : "",
  }, { default: () => label });
}

function renderRunStatus(row: SyncRun): VNodeChild {
  const label = row.status === "success" ? "成功" : row.status === "failed" ? "失败" : "进行中";
  if (row.status !== "running") {
    return renderStatusTag(label, runStatusTone(row.status));
  }
  const total = Math.max(1, row.progress_total);
  const done = Math.max(0, Math.min(row.progress_done, total));
  const percentage = Math.round((done / total) * 100);
  return h("div", { class: "sync-history-running" }, [
    renderStatusTag(label, "lavender"),
    h("span", { class: "sync-progress-count" }, `${row.progress_done} / ${row.progress_total}`),
    h("span", { class: "sync-progress-records" }, `${formatInteger(row.records)} 条记录`),
    h(NProgress, {
      type: "line",
      percentage,
      showIndicator: false,
      processing: true,
      class: "sync-history-progress",
    }),
    row.current_from
      ? h("small", { class: "sync-current-range" }, `当前：${row.current_from.slice(0, 10)} — ${(row.current_to ?? "").slice(0, 10)}`)
      : null,
  ]);
}

function handleManualRangeChange(value: string | DateRange | null): void {
  if (Array.isArray(value) && value.length === 2) {
    manualRange.value = parseValidDateRange(value[0], value[1], manualRange.value);
  }
}

function handleExchangeRangeChange(value: string | DateRange | null): void {
  if (Array.isArray(value) && value.length === 2) {
    exchangeRange.value = parseValidDateRange(value[0], value[1], exchangeRange.value);
  }
}

function selectManualPreset(preset: DatePreset): void {
  manualRange.value = standardDatePresetRange(preset, moscowToday());
}

function selectExchangePreset(preset: DatePreset): void {
  exchangeRange.value = standardDatePresetRange(preset, beijingToday());
}

async function loadSyncRuns(isPolling = false): Promise<void> {
  const requestId = ++historyRequestId;
  if (!isPolling) {
    historyLoading.value = true;
    historyError.value = "";
  }
  try {
    const rows = await getSyncRuns();
    if (!viewActive || requestId !== historyRequestId) return;
    syncRuns.value = rows;
  } catch (cause) {
    if (!viewActive || requestId !== historyRequestId) return;
    if (!isPolling) historyError.value = getErrorMessage(cause);
  } finally {
    if (viewActive && !isPolling && requestId === historyRequestId) historyLoading.value = false;
  }
}

function applyAutoSettings(rows: AutoSyncSetting[]): void {
  autoSettings.value = rows;
  for (const shopId of shopIds) {
    for (const { module } of autoModules) {
      const row = rows.find((item) => item.shop_id === shopId && item.module === module);
      autoDraft[shopId][module] = {
        enabled: Boolean(row?.enabled),
        interval_hours: row?.interval_hours ?? 24,
        range_days: row?.range_days ?? 1,
      };
    }
  }
}

async function loadAutoSettings(): Promise<void> {
  const requestId = ++autoRequestId;
  autoLoading.value = true;
  autoError.value = "";
  try {
    const rows = await getAutoSyncSettings();
    if (!viewActive || requestId !== autoRequestId) return;
    applyAutoSettings(rows);
  } catch (cause) {
    if (viewActive && requestId === autoRequestId) autoError.value = getErrorMessage(cause);
  } finally {
    if (viewActive && requestId === autoRequestId) autoLoading.value = false;
  }
}

async function loadExchangeStatus(): Promise<void> {
  const requestId = ++exchangeRequestId;
  exchangeLoading.value = true;
  exchangeError.value = "";
  try {
    const status = await getExchangeRateStatus();
    if (!viewActive || requestId !== exchangeRequestId) return;
    exchange.value = status;
  } catch (cause) {
    if (viewActive && requestId === exchangeRequestId) exchangeError.value = getErrorMessage(cause);
  } finally {
    if (viewActive && requestId === exchangeRequestId) exchangeLoading.value = false;
  }
}

function buildAutoPayload(): AutoSyncSettingsPayload {
  return Object.fromEntries(shopIds.map((shopId) => [
    String(shopId),
    Object.fromEntries(autoModules.map(({ module }) => {
      const draft = autoDraft[shopId][module];
      return [module, {
        enabled: draft.enabled,
        interval_hours: draft.interval_hours,
        range_days: module === "stock" ? 1 : Math.min(365, Math.max(1, Math.trunc(draft.range_days || 1))),
      }];
    })),
  ])) as AutoSyncSettingsPayload;
}

function saveAutoSettings(): void {
  autoSaveChain = autoSaveChain.catch(() => undefined).then(async () => {
    if (!viewActive) return;
    autoSaving.value = true;
    autoError.value = "";
    try {
      await updateAutoSyncSettings(buildAutoPayload());
      if (viewActive) message.success("自动同步设置已保存");
    } catch (cause) {
      if (!viewActive) return;
      const saveError = getErrorMessage(cause);
      autoError.value = saveError;
      message.error(autoError.value);
      await loadAutoSettings();
      if (viewActive) autoError.value = `${saveError}（已重新读取服务端配置）`;
    } finally {
      if (viewActive) autoSaving.value = false;
    }
  });
}

function updateAutoEnabled(shopId: ShopId, module: AutoSyncModule, enabled: boolean): void {
  autoDraft[shopId][module].enabled = enabled;
  saveAutoSettings();
}

function updateAutoInterval(shopId: ShopId, module: AutoSyncModule, value: string | number | null): void {
  const hours = Number(value);
  if (intervalOptions.some((option) => option.value === hours)) {
    autoDraft[shopId][module].interval_hours = hours;
    saveAutoSettings();
  }
}

function updateAutoRange(shopId: ShopId, module: AutoSyncModule, value: number | null): void {
  if (value != null) autoDraft[shopId][module].range_days = value;
}

function confirmFullSync(module: ManualSyncModule, shopId: ShopId): void {
  const range: DateRange = [...manualRange.value];
  dialog.warning({
    title: "确认开始全量拉取？",
    content: "整个时段将按自然月逐段拉取，耗时可能较长。确认开始？",
    positiveText: "确认开始",
    negativeText: "取消",
    onPositiveClick: () => {
      void runManualSync(module, shopId, range);
      return true;
    },
  });
}

function startManualSync(module: ManualSyncModule): void {
  if (selectedShopId.value === 0) {
    message.error("请先在右上角选择一个店铺");
    return;
  }
  if (manualSyncing[module]) return;
  const shopId = selectedShopId.value;
  const range: DateRange = [...manualRange.value];
  if (manualActivePreset.value === "all") {
    confirmFullSync(module, shopId);
    return;
  }
  void runManualSync(module, shopId, range);
}

async function runManualSync(module: ManualSyncModule, shopId: ShopId, range: DateRange): Promise<void> {
  if (manualSyncing[module]) return;
  manualSyncing[module] = true;
  try {
    if (module === "ad_campaigns") {
      const result = await syncPerformanceCampaigns(shopId);
      message.success(`${syncNames[module]}拉取完成：${formatInteger(result.inserted_or_updated ?? result.fetched)} 条`);
      await loadSyncRuns(true);
      return;
    }
    if (module === "ad_campaign_daily" || module === "ad_sku_daily") {
      const result = await syncPerformanceStatistics(shopId, range[0], range[1], module);
      const saved = module === "ad_campaign_daily"
        ? result.campaign_daily.inserted_or_updated
        : result.sku.inserted_or_updated;
      message.success(`${syncNames[module]}拉取完成：${formatInteger(saved ?? result.inserted_or_updated)} 条`);
      await loadSyncRuns(true);
      return;
    }
    const task = await startSync(module, shopId, range[0], range[1]);
    await loadSyncRuns(true);
    await waitForSync(task.run_id, module);
  } catch (cause) {
    if (viewActive) message.error(getErrorMessage(cause));
  } finally {
    if (viewActive) manualSyncing[module] = false;
  }
}

function waitForNextPoll(): Promise<boolean> {
  if (!viewActive) return Promise.resolve(false);
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      pollTimers.delete(timer);
      resolve(true);
    }, 1000);
    pollTimers.set(timer, () => {
      pollTimers.delete(timer);
      resolve(false);
    });
  });
}

async function waitForSync(runId: number, module: ManualSyncModule): Promise<void> {
  while (viewActive) {
    try {
      const run = await getSyncRun(runId);
      if (!viewActive) return;
      await loadSyncRuns(true);
      if (!viewActive) return;
      if (run.status !== "running") {
        if (run.status === "success") {
          message.success(`${syncNames[module]}拉取完成：${formatInteger(run.records)} 条`);
        } else {
          message.error(run.error || `${syncNames[module]}拉取失败`);
        }
        return;
      }
      if (!(await waitForNextPoll())) return;
    } catch (cause) {
      if (viewActive) message.error(getErrorMessage(cause));
      return;
    }
  }
}

async function syncExchange(): Promise<void> {
  if (exchangeSyncing.value) return;
  exchangeSyncing.value = true;
  exchangeError.value = "";
  try {
    const result = await syncExchangeRates(exchangeRange.value[0], exchangeRange.value[1]);
    if (viewActive) message.success(`汇率拉取完成：${formatInteger(result.records)} 条`);
    await loadExchangeStatus();
  } catch (cause) {
    if (viewActive) {
      exchangeError.value = getErrorMessage(cause);
      message.error(exchangeError.value);
    }
  } finally {
    if (viewActive) exchangeSyncing.value = false;
  }
}

onMounted(() => {
  viewActive = true;
  void Promise.allSettled([loadSyncRuns(), loadAutoSettings(), loadExchangeStatus()]);
});

onBeforeUnmount(() => {
  viewActive = false;
  historyRequestId += 1;
  autoRequestId += 1;
  exchangeRequestId += 1;
  for (const [timer, cancel] of pollTimers) {
    window.clearTimeout(timer);
    cancel();
  }
  pollTimers.clear();
});
</script>

<template>
  <section class="sync-view">
    <SyncSummaryCards :items="summaryCards" :loading="summaryLoading" />

    <div class="sync-main-grid">
      <NCard :bordered="false" class="analytics-table-card">
        <template #header>
          <div class="analytics-panel-heading">
            <div>
              <h2><morph-icon icon="sync" size="18" stroke-width="1.8" />手动数据同步</h2>
              <span>选择单个店铺后执行一次性拉取，普通订单类任务会显示实时分段进度。自动调度使用北京时间 · 手动订单日期使用莫斯科时间。</span>
            </div>
            <NTag :bordered="false" :class="selectedShopId === 0 ? 'sync-tone-tag--butter' : 'sync-tone-tag--azure'">
              {{ manualShopHint }}
            </NTag>
          </div>
        </template>
        <div class="sync-date-controls">
          <span class="sync-control-label">同步日期</span>
          <NDatePicker
            :formatted-value="manualRange"
            type="daterange"
            value-format="yyyy-MM-dd"
            separator="至"
            :clearable="false"
            class="sync-date-picker"
            aria-label="手动同步日期范围"
            @update:formatted-value="handleManualRangeChange"
          />
          <DatePresetPills class="sync-date-presets" aria-label="手动同步日期快捷范围" :options="datePresets" :active-key="manualActivePreset" @select="selectManualPreset" />
        </div>
        <p class="sync-date-note"><morph-icon icon="clock" size="14" stroke-width="1.8" />手动订单、退货日期按 Europe/Moscow 计算；库存与广告接口按后端规则执行。</p>
        <NAlert v-if="selectedShopId === 0" type="warning" :bordered="false" class="sync-shop-alert">
          请先在右上角选择一个店铺，店铺合并视图不可直接发起手动同步。
        </NAlert>
        <div class="sync-manual-grid">
          <article v-for="item in manualModules" :key="item.module" class="sync-manual-item">
            <div class="sync-module-icon"><morph-icon :icon="item.icon" size="17" stroke-width="1.8" /></div>
            <div class="sync-module-copy">
              <strong>{{ item.label }}</strong>
              <span>{{ item.description }}</span>
              <small>{{ item.hint }}</small>
            </div>
            <NButton
              size="small"
              :type="manualSyncing[item.module] ? 'primary' : 'default'"
              :loading="manualSyncing[item.module]"
              :disabled="selectedShopId === 0 || manualSyncing[item.module]"
              @click="startManualSync(item.module)"
            >
              {{ manualSyncing[item.module] ? '同步中…' : item.module === 'ad_campaigns' ? '同步 Campaign' : '开始同步' }}
            </NButton>
          </article>
        </div>
      </NCard>

      <NCard :bordered="false" class="analytics-table-card">
        <template #header>
          <div class="analytics-panel-heading">
            <div>
            <h2><morph-icon icon="coins" size="18" stroke-width="1.8" />Ozon 汇率</h2>
              <span>独立于 Profit 测算汇率，状态来自 `/api/exchange-rates`。</span>
            </div>
            <NSpin v-if="exchangeLoading" size="small" />
          </div>
        </template>
        <div class="sync-date-controls">
          <span class="sync-control-label">汇率日期</span>
          <NDatePicker
            :formatted-value="exchangeRange"
            type="daterange"
            value-format="yyyy-MM-dd"
            separator="至"
            :clearable="false"
            class="sync-date-picker"
            aria-label="汇率同步日期范围"
            @update:formatted-value="handleExchangeRangeChange"
          />
          <DatePresetPills class="sync-date-presets" aria-label="汇率日期快捷范围" :options="datePresets" :active-key="exchangeActivePreset" @select="selectExchangePreset" />
        </div>
        <NAlert v-if="exchangeError" type="error" :bordered="false" class="sync-error-alert">
          汇率状态加载失败：{{ exchangeError }}
        </NAlert>
        <div class="sync-exchange-status">
          <div class="sync-status-tile">
            <span>最近成功</span>
            <strong>{{ exchangeLastSuccess }}</strong>
            <small>官方接口最后一次成功抓取</small>
          </div>
          <div class="sync-status-tile">
            <span>数据覆盖至</span>
            <strong>{{ exchangeDataThrough }}</strong>
            <small>数据库中的有效期上界</small>
          </div>
          <section class="sync-rate-group">
            <h3 class="sync-rate-group-heading">针对服务和罚款</h3>
            <div class="sync-rate-pair">
              <div class="sync-rate-tile">
                <span>USD / RUB</span>
                <strong>{{ rateValue('USD', 'service_penalty_exchange_rate') }}</strong>
              </div>
              <div class="sync-rate-tile">
                <span>CNY / RUB</span>
                <strong>{{ rateValue('CNY', 'service_penalty_exchange_rate') }}</strong>
              </div>
            </div>
          </section>
          <section class="sync-rate-group">
            <h3 class="sync-rate-group-heading">用于销售</h3>
            <div class="sync-rate-pair">
              <div class="sync-rate-tile">
                <span>USD / RUB</span>
                <strong>{{ rateValue('USD', 'sales_exchange_rate') }}</strong>
              </div>
              <div class="sync-rate-tile">
                <span>CNY / RUB</span>
                <strong>{{ rateValue('CNY', 'sales_exchange_rate') }}</strong>
              </div>
            </div>
          </section>
        </div>
        <div class="sync-exchange-actions">
          <span>汇率范围与手动同步日期相互独立，当前按北京时间显示状态。</span>
          <NButton type="primary" :loading="exchangeSyncing" @click="syncExchange">
            <template #icon><morph-icon icon="sync" size="15" stroke-width="1.9" /></template>
            {{ exchangeSyncing ? '拉取中…' : '立即同步汇率' }}
          </NButton>
        </div>
      </NCard>
    </div>

    <NCard :bordered="false" class="analytics-table-card">
      <template #header>
        <div class="analytics-panel-heading">
          <div>
            <h2><morph-icon icon="calendar" size="18" stroke-width="1.8" />自动同步配置</h2>
            <span>后端负责北京时间调度、同槽位去重、运行去重与失败冷却；这里仅保存每店铺每模块的配置。</span>
          </div>
          <NSpin v-if="autoLoading" size="small" />
        </div>
      </template>
      <NAlert v-if="autoError" type="error" :bordered="false" class="sync-error-alert">
        自动同步配置加载或保存失败：{{ autoError }}
      </NAlert>
      <div class="sync-auto-shop-grid">
        <section v-for="shopId in shopIds" :key="shopId" class="sync-auto-shop">
          <div class="sync-auto-shop-heading">
            <div>
              <span class="sync-section-kicker">SHOP {{ shopId }}</span>
              <h3><morph-icon icon="store" size="16" stroke-width="1.8" />{{ shopName(shopId) }}</h3>
            </div>
            <NTag size="small" :bordered="false" class="sync-tone-tag--azure">5 个模块</NTag>
          </div>
          <div class="sync-auto-list">
            <article v-for="item in autoModules" :key="item.module" class="sync-auto-row">
              <div class="sync-auto-module">
                <morph-icon :icon="item.icon" size="15" stroke-width="1.8" />
                <strong>{{ item.label }}</strong>
              </div>
              <NSwitch
                :value="autoDraft[shopId][item.module].enabled"
                :disabled="autoLoading || autoSaving"
                size="small"
                @update:value="updateAutoEnabled(shopId, item.module, $event)"
              />
              <NSelect
                :value="autoDraft[shopId][item.module].interval_hours"
                :options="intervalOptions"
                :disabled="autoLoading || autoSaving || !autoDraft[shopId][item.module].enabled"
                size="small"
                class="sync-auto-interval"
                @update:value="updateAutoInterval(shopId, item.module, $event)"
              />
              <div v-if="item.module === 'stock'" class="sync-auto-realtime">实时快照</div>
              <NInputNumber
                v-else
                :value="autoDraft[shopId][item.module].range_days"
                :min="1"
                :max="365"
                :step="1"
                :show-button="false"
                :disabled="autoLoading || autoSaving || !autoDraft[shopId][item.module].enabled"
                size="small"
                class="sync-auto-range"
                @update:value="updateAutoRange(shopId, item.module, $event)"
                @blur="saveAutoSettings"
              />
              <span v-if="item.module !== 'stock'" class="sync-auto-unit">天范围</span>
            </article>
          </div>
        </section>
      </div>
    </NCard>

    <NCard :bordered="false" class="analytics-table-card">
      <template #header>
        <div class="analytics-panel-heading">
          <div>
            <h2><morph-icon icon="clock" size="18" stroke-width="1.8" />最近同步记录</h2>
            <span>后端按最新 10 条记录返回；进行中的任务会在同步期间刷新。</span>
          </div>
          <NSpin v-if="historyLoading && syncRuns.length" size="small" />
        </div>
      </template>
      <NAlert v-if="historyError" type="error" :bordered="false" class="sync-error-alert">
        拉取记录加载失败：{{ historyError }}
      </NAlert>
      <NDataTable
        class="analytics-table"
        :columns="historyColumns"
        :data="syncRuns"
        :row-key="(row) => row.id"
        :scroll-x="980"
        table-layout="fixed"
        :loading="historyLoading"
      >
        <template #empty>
          <EmptyState :title="historyEmptyDescription" icon="clock" />
        </template>
      </NDataTable>
    </NCard>
  </section>
</template>
