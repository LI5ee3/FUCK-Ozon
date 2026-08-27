<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { init, use, type ECharts } from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { Channel, OrderTrend, TrendBucket } from "../../types/api";
import { useTheme } from "../../composables/useTheme";
import { macaronTokens } from "../../theme/tokens";
import { formatGmv, formatInteger } from "../../utils/format";
import { beijingToday } from "../../utils/date";

use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{ data: OrderTrend }>();
const chartElement = ref<HTMLDivElement | null>(null);
const { isDark } = useTheme();
const palette = computed(() => (isDark.value ? macaronTokens.dark : macaronTokens.light));
let chart: ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;

const channels: Channel[] = ["FBP", "realFBS", "WHD"];

function labelFor(bucket: TrendBucket, granularity: OrderTrend["granularity"]): string {
  return granularity === "month" ? bucket.from.slice(0, 7) : bucket.from.slice(5);
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character] ?? character);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function channelClass(channel: Channel): string {
  return channel === "FBP" ? "fbp" : channel === "realFBS" ? "fbs" : "whd";
}

function createTooltipFormatter(buckets: TrendBucket[]) {
  return (params: unknown): string => {
    const item = Array.isArray(params) ? params[0] : params;
    if (!isRecord(item) || typeof item.dataIndex !== "number") return "";
    const bucket = buckets[item.dataIndex];
    if (!bucket) return "";
    const date = bucket.from === bucket.to ? bucket.from : `${bucket.from} 至 ${bucket.to}`;
    const ongoing = bucket.orders === 0 && bucket.from === beijingToday();
    const channelRows = channels.map((channel) => {
      const row = bucket.channels[channel];
      return `<div class="dashboard-chart-tooltip-row"><span class="dashboard-chart-tooltip-dot dashboard-chart-tooltip-dot--${channelClass(channel)}"></span><span>${channel}</span><b>${formatInteger(row.orders)} 单</b><small>${escapeHtml(formatGmv(row.gmv))}</small></div>`;
    }).join("");
    return `<div class="dashboard-chart-tooltip"><div class="dashboard-chart-tooltip-date">${escapeHtml(date)}${ongoing ? ' <span class="dashboard-chart-tooltip-badge">进行中</span>' : ""}</div><div class="dashboard-chart-tooltip-main"><span>已订购 (有效订单)</span><b>${formatInteger(bucket.orders)} 单</b></div><div class="dashboard-chart-tooltip-gmv">${escapeHtml(formatGmv(bucket.gmv))}</div><div class="dashboard-chart-tooltip-divider"></div>${channelRows}</div>`;
  };
}

function chartOption() {
  const colors = palette.value;
  const buckets = props.data.buckets;
  return {
    animationDuration: 280,
    grid: { left: 12, right: 18, top: 18, bottom: 22, containLabel: true },
    tooltip: {
      trigger: "axis",
      confine: true,
      backgroundColor: colors.panelSolid,
      borderColor: colors.line,
      borderWidth: 1,
      textStyle: { color: colors.text, fontFamily: macaronTokens.fontFamily },
      axisPointer: { type: "line", lineStyle: { color: colors.primary, type: "dashed" } },
      formatter: createTooltipFormatter(buckets),
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: buckets.map((bucket) => labelFor(bucket, props.data.granularity)),
      axisLine: { lineStyle: { color: colors.line } },
      axisTick: { show: false },
      axisLabel: {
        color: colors.muted,
        interval: Math.max(0, Math.ceil(buckets.length / 7) - 1),
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      minInterval: 1,
      splitNumber: 2,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: colors.muted, formatter: (value: number) => formatInteger(value) },
      splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
    },
    series: [{
      type: "line",
      name: "有效订单",
      data: buckets.map((bucket) => bucket.orders),
      smooth: true,
      showSymbol: buckets.length <= 32,
      symbol: "circle",
      symbolSize: 7,
      lineStyle: { color: colors.primary, width: 2.5 },
      itemStyle: { color: colors.primary, borderColor: colors.panelSolid, borderWidth: 2 },
      areaStyle: { color: colors.primary, opacity: isDark.value ? 0.2 : 0.12 },
      emphasis: { focus: "series" },
    }],
  };
}

function render(): void {
  chart?.setOption(chartOption(), true);
}

watch([() => props.data, isDark], render, { deep: true });

onMounted(() => {
  if (!chartElement.value) return;
  chart = init(chartElement.value);
  resizeObserver = new ResizeObserver(() => chart?.resize());
  resizeObserver.observe(chartElement.value);
  render();
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  chart?.dispose();
  chart = null;
});
</script>

<template>
  <div ref="chartElement" class="dashboard-chart" role="img" aria-label="有效订单量趋势折线图" />
</template>
