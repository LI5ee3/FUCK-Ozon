<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { init, use, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { NDrawer, NDrawerContent, NTag } from "naive-ui";
import { getErrorMessage } from "../../shared/api/client";
import { useTheme } from "../../shared/composables/useTheme";
import type { Channel } from "../../shared/types/common";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../../shared/utils/format";
import { macaronTokens } from "../../theme/tokens";
import { getPricingStrategy } from "./api";
import type {
  PricingEventImpact,
  PricingHistoryChangeValue,
  PricingHistoryEvent,
  PricingItem,
  PricingMarketSource,
  PricingStrategyResponse,
  PricingStrategySignal,
} from "./types";
import "./pricing-strategy.css";

use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  show: boolean;
  item: PricingItem | null;
  channel: Channel;
  targetMarginPct: number;
}>();
const emit = defineEmits<{ "update:show": [value: boolean] }>();

const response = ref<PricingStrategyResponse | null>(null);
const loading = ref(false);
const error = ref("");
let requestId = 0;

const { isDark } = useTheme();
const palette = computed(() => (isDark.value ? macaronTokens.dark : macaronTokens.light));
const chartElement = ref<HTMLDivElement | null>(null);
let chart: ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;

const sourceLabels: Record<"ozon" | "external" | "self_marketplace", string> = {
  ozon: "Ozon",
  external: "External",
  self_marketplace: "Self marketplace",
};
const priceFields = new Set(["effective_price", "base_price", "marketing_seller_price", "min_price"]);

const strategy = computed(() => response.value?.strategy ?? null);
const history = computed(() => response.value?.history ?? null);
const marketSources = computed(() => {
  const sources = strategy.value?.market_sources;
  if (!sources) return [];
  return (Object.keys(sourceLabels) as Array<keyof typeof sourceLabels>).map((key) => ({
    key,
    label: sourceLabels[key],
    source: sources[key],
  }));
});
const recentEvents = computed(() => [...(history.value?.events ?? [])].reverse());

function reset(): void {
  requestId += 1;
  loading.value = false;
  error.value = "";
  response.value = null;
  disposeChart();
}

async function load(): Promise<void> {
  const item = props.item;
  if (!item) return;
  const currentRequest = ++requestId;
  loading.value = true;
  error.value = "";
  response.value = null;
  try {
    const data = await getPricingStrategy({
      shopId: item.shop_id,
      snapshotKey: item.snapshot_key,
      channel: props.channel,
      targetMarginPct: props.targetMarginPct,
      historyDays: 90,
    });
    if (currentRequest === requestId) response.value = data;
  } catch (cause) {
    if (currentRequest === requestId) error.value = getErrorMessage(cause);
  } finally {
    if (currentRequest === requestId) loading.value = false;
  }
}

watch(
  [() => props.show, () => props.item?.shop_id, () => props.item?.snapshot_key, () => props.channel, () => props.targetMarginPct],
  ([show]) => { if (show) void load(); else reset(); },
  { immediate: true },
);

function formatPrice(value: string | null, currency: string | null = null): string {
  if (value === null || value.trim() === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  const formatted = new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(parsed);
  return currency ? `${formatted} ${currency}` : formatted;
}

function formatPct(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatSignedInteger(value: number | null): string {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${formatInteger(value)}`;
}

function signalLabel(value: PricingStrategySignal): string {
  return {
    raise: "raise",
    reduce: "reduce",
    hold: "hold",
    margin_market_conflict: "margin_market_conflict",
    insufficient_data: "insufficient_data",
  }[value];
}

function signalDescription(value: PricingStrategySignal): string {
  return {
    raise: "低于目标毛利线",
    reduce: "存在向市场参考靠近的价格空间",
    hold: "当前处于价格观察区间内",
    margin_market_conflict: "目标毛利线高于市场价格锚点",
    insufficient_data: "核心价格数据不足",
  }[value];
}

function signalTone(value: PricingStrategySignal): string {
  if (value === "hold") return "mint";
  if (value === "raise") return "butter";
  if (value === "insufficient_data") return "lavender";
  return "peach";
}

function sourceStatusLabel(value: PricingMarketSource["status"]): string {
  return {
    available: "可用",
    missing_price: "缺少价格",
    missing_currency: "缺少币种",
    missing_exchange_rate: "缺少汇率",
  }[value];
}

function warningLabel(value: string): string {
  return {
    partial_market_reference: "部分市场参考数据不可用",
    market_reference_currency_missing: "市场参考币种缺失",
    market_reference_exchange_rate_missing: "市场参考汇率缺失",
  }[value] ?? value;
}

function reasonLabel(value: string): string {
  return {
    missing_current_price: "缺当前测算售价",
    missing_target_margin_price: "缺目标毛利价",
    missing_market_reference: "缺市场参考",
    current_below_break_even: "当前价格低于基础保本价",
    current_below_target_margin: "当前价格低于目标毛利价",
    current_above_market_reference: "当前价格高于市场参考",
    within_observation_range: "当前处于价格观察区间",
    target_margin_above_market: "目标毛利价高于市场参考",
  }[value] ?? value;
}

function changeLabel(value: string): string {
  return {
    effective_price: "有效售价",
    base_price: "基础售价",
    marketing_seller_price: "卖家促销价",
    min_price: "最低售价",
    auto_action_enabled: "自动动作",
    price_index_color: "价格指数颜色",
    currency: "币种",
    ozon_reference: "Ozon 市场参考",
    external_reference: "External 市场参考",
    self_marketplace_reference: "Self marketplace 市场参考",
  }[value] ?? value;
}

function formatChangeValue(value: PricingHistoryChangeValue, field: string, event: PricingHistoryEvent, side: "from" | "to"): string {
  if (typeof value === "boolean") return value ? "启用" : "停用";
  if (value === null) return "—";
  if (typeof value === "object") return formatPrice(value.price, value.currency);
  if (priceFields.has(field)) return formatPrice(value, side === "from" ? event.previous_currency : event.currency);
  return value;
}

function eventHasPriceChange(event: PricingHistoryEvent): boolean {
  return event.types.includes("effective_price_changed");
}

function revenueComparable(impact: PricingEventImpact): boolean {
  return Boolean(impact.before && impact.after
    && impact.before.sold_price_status === "available"
    && impact.after.sold_price_status === "available"
    && impact.before.currency === impact.after.currency);
}

function comparableWarning(impact: PricingEventImpact): string {
  if (!impact.before || !impact.after) return "";
  if (impact.before.currency !== impact.after.currency
      || impact.before.sold_price_status === "currency_mismatch"
      || impact.after.sold_price_status === "currency_mismatch"
      || impact.before.sold_price_status === "missing_currency"
      || impact.after.sold_price_status === "missing_currency") {
    return "销售额不可直接比较";
  }
  return "销售额暂无可比数据";
}

function weightedPriceComparable(impact: PricingEventImpact): boolean {
  return revenueComparable(impact);
}

function weightedPriceWarning(impact: PricingEventImpact): string {
  return weightedPriceComparable(impact) ? "" : "成交均价不可直接比较";
}

function tooltipHtml(params: unknown): string {
  const first = Array.isArray(params) ? params[0] : params;
  if (!first || typeof first !== "object" || !("dataIndex" in first)) return "";
  const index = typeof first.dataIndex === "number" ? first.dataIndex : -1;
  const point = history.value?.points[index];
  if (!point) return "";
  return `<div class="pricing-strategy-chart-tooltip"><strong>${escapeHtml(formatBeijingDateTime(point.observed_at))}</strong><div>有效售价 <b>${escapeHtml(formatPrice(point.effective_price, point.currency))}</b></div><div>币种 <b>${escapeHtml(point.currency ?? "—")}</b></div></div>`;
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ?? character);
}

function chartOption() {
  const colors = palette.value;
  const points = history.value?.points ?? [];
  const currencies = [...new Set(points.map((point) => point.currency ?? "币种未知"))];
  const changedAt = new Set((history.value?.events ?? [])
    .filter((event) => eventHasPriceChange(event) || event.types.includes("currency_changed"))
    .map((event) => event.observed_at));
  return {
    animationDuration: 0,
    grid: { left: 12, right: 18, top: 18, bottom: 24, containLabel: true },
    tooltip: {
      trigger: "axis", confine: true, backgroundColor: colors.panelSolid, borderColor: colors.line,
      textStyle: { color: colors.text, fontFamily: macaronTokens.fontFamily },
      formatter: tooltipHtml,
    },
    legend: { top: 0, right: 0, itemWidth: 12, itemHeight: 8, textStyle: { color: colors.muted, fontFamily: macaronTokens.fontFamily } },
    xAxis: {
      type: "category", boundaryGap: false, data: points.map((point) => point.observed_at.slice(5, 10)),
      axisLine: { lineStyle: { color: colors.line } }, axisTick: { show: false }, axisLabel: { color: colors.muted },
    },
    yAxis: {
      type: "value", min: 0, splitNumber: 3, axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: colors.muted, formatter: (value: number) => formatNumber(value) },
      splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
    },
    series: currencies.map((currency) => ({
      type: "line", name: `有效售价 ${currency}`, connectNulls: false, showSymbol: true, symbol: "circle", symbolSize: 6,
      lineStyle: { width: 2, color: colors.primary }, itemStyle: { color: colors.primary },
      data: points.map((point) => {
        const sameCurrency = (point.currency ?? "币种未知") === currency;
        const value = point.effective_price === null ? NaN : Number(point.effective_price);
        if (!sameCurrency || !Number.isFinite(value)) return null;
        return { value, symbol: changedAt.has(point.observed_at) ? "diamond" : "circle", symbolSize: changedAt.has(point.observed_at) ? 10 : 6 };
      }),
    })),
  };
}

function disposeChart(): void {
  resizeObserver?.disconnect();
  resizeObserver = null;
  chart?.dispose();
  chart = null;
}

async function renderChart(): Promise<void> {
  await nextTick();
  if (!chartElement.value || !history.value?.points.length) {
    disposeChart();
    return;
  }
  if (!chart) {
    chart = init(chartElement.value);
    resizeObserver = new ResizeObserver(() => chart?.resize());
    resizeObserver.observe(chartElement.value);
  }
  chart.setOption(chartOption(), true);
}

watch([response, isDark], () => { void renderChart(); }, { deep: true });
onBeforeUnmount(disposeChart);
</script>

<template>
  <NDrawer :show="props.show" placement="right" :width="720" @update:show="emit('update:show', $event)">
    <NDrawerContent closable>
      <template #header>
        <div class="pricing-strategy-header">
          <strong>价格策略与历史</strong>
          <span v-if="props.item">{{ props.item.product.display_name }} · {{ props.item.shop_name }}</span>
        </div>
      </template>

      <div class="pricing-strategy-drawer">
        <div v-if="loading" class="pricing-strategy-state" aria-live="polite">正在加载策略分析…</div>
        <div v-else-if="error" class="pricing-strategy-state pricing-strategy-state--error" role="alert">{{ error }}</div>
        <div v-else-if="!response" class="pricing-strategy-state">暂无策略分析</div>

        <template v-else>
          <div class="pricing-strategy-identity">
            <span>SKU {{ response.product.sku ?? "未明确" }}</span>
            <span>Offer ID {{ response.product.offer_id ?? "—" }}</span>
            <span>参考履约模式 {{ response.reference_channel }}</span>
          </div>

          <section class="pricing-strategy-section pricing-strategy-signal">
            <div class="pricing-strategy-section-heading"><h3>策略状态</h3><NTag :bordered="false" round size="small" :class="`pricing-tone-tag--${signalTone(response.strategy.signal)}`">{{ signalLabel(response.strategy.signal) }}</NTag></div>
            <p>{{ signalDescription(response.strategy.signal) }}</p>
            <div v-if="response.strategy.reason_codes.length" class="pricing-strategy-reasons">{{ response.strategy.reason_codes.map(reasonLabel).join(" · ") }}</div>
          </section>

          <section class="pricing-strategy-section">
            <div class="pricing-strategy-section-heading"><h3>价格锚点</h3><span>{{ response.strategy.currency }}</span></div>
            <div class="pricing-strategy-anchor-grid">
              <div><small>当前测算售价</small><strong>{{ formatPrice(response.strategy.current_price, response.strategy.currency) }}</strong></div>
              <div><small>基础保本价</small><strong>{{ formatPrice(response.strategy.break_even_price, response.strategy.currency) }}</strong></div>
              <div><small>目标毛利价</small><strong>{{ formatPrice(response.strategy.target_margin_price, response.strategy.currency) }}</strong></div>
              <div><small>市场参考</small><strong>{{ formatPrice(response.strategy.market_reference_price, response.strategy.currency) }}</strong></div>
              <div><small>30天成交均价</small><strong>{{ formatPrice(response.strategy.sold_price_30, response.strategy.currency) }}</strong></div>
            </div>
          </section>

          <section class="pricing-strategy-section">
            <div class="pricing-strategy-section-heading"><h3>价格观察区间</h3><span v-if="response.strategy.observation_range.status === 'available'">合理观察区间</span></div>
            <div v-if="response.strategy.observation_range.status === 'available'" class="pricing-strategy-range">
              <div class="pricing-strategy-range-track"><span /></div>
              <div class="pricing-strategy-range-labels"><span>{{ formatPrice(response.strategy.observation_range.lower, response.strategy.currency) }}</span><span>{{ formatPrice(response.strategy.observation_range.upper, response.strategy.currency) }}</span></div>
              <p>当前测算售价：{{ formatPrice(response.strategy.current_price, response.strategy.currency) }}</p>
            </div>
            <p v-else-if="response.strategy.observation_range.status === 'conflict'" class="pricing-strategy-conflict">目标毛利价高于当前市场价格锚点，暂无兼顾目标毛利与当前市场参考的价格观察区间。</p>
            <p v-else class="pricing-strategy-muted">缺少目标毛利价或市场参考，暂无法形成价格观察区间。</p>
          </section>

          <section class="pricing-strategy-section">
            <div class="pricing-strategy-section-heading"><h3>市场参考来源</h3><span v-if="response.strategy.warnings.includes('partial_market_reference')">部分市场参考数据不可用</span></div>
            <div class="pricing-strategy-market-list">
              <div v-for="entry in marketSources" :key="entry.key" class="pricing-strategy-market-row">
                <strong>{{ entry.label }}</strong>
                <span>原始 {{ formatPrice(entry.source.price, entry.source.currency) }}</span>
                <span>转换 {{ formatPrice(entry.source.converted_price, entry.source.converted_currency) }}</span>
                <NTag :bordered="false" round size="small" :class="`pricing-tone-tag--${entry.source.status === 'available' ? 'mint' : 'butter'}`">{{ sourceStatusLabel(entry.source.status) }}</NTag>
              </div>
            </div>
            <div v-if="response.strategy.warnings.length" class="pricing-strategy-warnings">{{ response.strategy.warnings.map(warningLabel).join(" · ") }}</div>
          </section>

          <section class="pricing-strategy-section">
            <div class="pricing-strategy-section-heading"><h3>价格历史</h3><span>{{ response.history.snapshot_count }} 个快照 · {{ response.history.price_change_count }} 次有效售价变化</span></div>
            <div v-if="response.history.points.length" ref="chartElement" class="pricing-strategy-chart" role="img" aria-label="有效售价历史折线图" />
            <div v-else class="pricing-strategy-muted">暂无历史价格快照</div>
            <div v-if="recentEvents.length" class="pricing-strategy-events">
              <article v-for="event in recentEvents" :key="`${event.observed_at}-${event.previous_observed_at}`" class="pricing-strategy-event">
                <div class="pricing-strategy-event-heading"><strong>{{ event.event_day ?? formatBeijingDateTime(event.observed_at) }}</strong><span>{{ formatBeijingDateTime(event.observed_at) }}</span></div>
                <div class="pricing-strategy-event-changes">
                  <span v-for="(change, field) in event.changes" :key="field">{{ changeLabel(field) }} {{ formatChangeValue(change.from, field, event, 'from') }} → {{ formatChangeValue(change.to, field, event, 'to') }}</span>
                  <span v-if="eventHasPriceChange(event)" class="pricing-strategy-event-change-pct">{{ formatPct(event.effective_price_change_pct) }}</span>
                </div>
                <div v-if="event.impact?.status === 'pending'" class="pricing-strategy-impact-note">后 7 日观察窗口尚未完成</div>
                <div v-else-if="event.impact?.status === 'unavailable'" class="pricing-strategy-impact-note">销售回看不可用：{{ event.impact.reason ?? "匹配事实不足" }}</div>
                <div v-else-if="event.impact?.status === 'available'" class="pricing-strategy-impact">
                  <div class="pricing-strategy-impact-windows">
                    <div><small>改价前 7 天</small><strong>{{ formatInteger(event.impact.before?.units) }} 件</strong><span>日均 {{ formatNumber(event.impact.before?.avg_daily_units) }} 件</span><span>销售额 {{ formatPrice(event.impact.before?.revenue ?? null, event.impact.before?.currency) }}</span><span>成交均价 {{ formatPrice(event.impact.before?.weighted_avg_price ?? null, event.impact.before?.currency) }}</span></div>
                    <div><small>改价后 7 天</small><strong>{{ formatInteger(event.impact.after?.units) }} 件</strong><span>日均 {{ formatNumber(event.impact.after?.avg_daily_units) }} 件</span><span>销售额 {{ formatPrice(event.impact.after?.revenue ?? null, event.impact.after?.currency) }}</span><span>成交均价 {{ formatPrice(event.impact.after?.weighted_avg_price ?? null, event.impact.after?.currency) }}</span></div>
                  </div>
                  <div class="pricing-strategy-impact-changes"><span>销量 {{ formatSignedInteger(event.impact.units_delta) }}（{{ formatPct(event.impact.units_change_pct) }}）</span><span v-if="revenueComparable(event.impact)">销售额 {{ formatPrice(event.impact.revenue_delta, event.impact.before?.currency ?? null) }}（{{ formatPct(event.impact.revenue_change_pct) }}）</span><span v-else>{{ comparableWarning(event.impact) }}</span><span v-if="weightedPriceComparable(event.impact)">成交均价 {{ formatPct(event.impact.weighted_avg_price_change_pct) }}</span><span v-else>{{ weightedPriceWarning(event.impact) }}</span></div>
                </div>
              </article>
            </div>
            <div v-else class="pricing-strategy-muted">暂无价格事件</div>
          </section>
        </template>

        <footer class="pricing-strategy-disclaimers">
          <p>策略结果仅用于经营决策辅助，不会自动修改 Ozon 商品价格。</p>
          <p>价格事件前后销售变化仅为历史事实对比，不代表价格变化与销量变化存在因果关系。</p>
        </footer>
      </div>
    </NDrawerContent>
  </NDrawer>
</template>
