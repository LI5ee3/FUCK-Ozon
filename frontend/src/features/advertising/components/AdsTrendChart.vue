<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { BarChart } from "echarts/charts";
import { init, use, type ECharts } from "echarts/core";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { AdsTrendPoint } from "../types";
import { useTheme } from "../../../shared/composables/useTheme";
import { macaronTokens } from "../../../theme/tokens";
import { formatNumber } from "../../../shared/utils/format";

use([BarChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{ data: AdsTrendPoint[] }>();
const chartElement = ref<HTMLDivElement | null>(null);
const { isDark } = useTheme();
const palette = computed(() => (isDark.value ? macaronTokens.dark : macaronTokens.light));
let chart: ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
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

function formatAdsMoney(value: number | null | undefined): string {
  return value != null && Number.isFinite(value) ? `${formatNumber(value)} RUB` : "—";
}

function dataIndexOf(params: unknown): number | null {
  const item = Array.isArray(params) ? params.find(isRecord) : params;
  if (!isRecord(item) || typeof item.dataIndex !== "number") return null;
  return item.dataIndex;
}

function tooltipFormatter(params: unknown): string {
  const index = dataIndexOf(params);
  const point = index == null ? undefined : props.data[index];
  if (!point) return "";
  return `<div class="ads-chart-tooltip"><strong>${escapeHtml(point.date)}</strong><div><span>广告花费</span><b>${formatAdsMoney(point.spend_rub)}</b></div><div><span>广告销售额</span><b>${formatAdsMoney(point.revenue_rub)}</b></div></div>`;
}

function chartOption() {
  const colors = palette.value;
  const ink = (hue: keyof typeof macaronTokens.tones) => macaronTokens.tones[hue][isDark.value ? "dark" : "light"].text;
  return {
    animationDuration: 280,
    grid: { left: 12, right: 18, top: 32, bottom: 24, containLabel: true },
    legend: {
      top: 0,
      right: 0,
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: colors.muted, fontFamily: macaronTokens.fontFamily },
    },
    tooltip: {
      trigger: "axis",
      confine: true,
      backgroundColor: colors.panelSolid,
      borderColor: colors.line,
      borderWidth: 1,
      textStyle: { color: colors.text, fontFamily: macaronTokens.fontFamily },
      axisPointer: { type: "shadow" },
      formatter: tooltipFormatter,
    },
    xAxis: {
      type: "category",
      data: props.data.map((point) => point.date.slice(5)),
      axisLine: { lineStyle: { color: colors.line } },
      axisTick: { show: false },
      axisLabel: { color: colors.muted, interval: Math.max(0, Math.ceil(props.data.length / 8) - 1) },
    },
    yAxis: {
      type: "value",
      min: 0,
      splitNumber: 3,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: colors.muted, formatter: (value: number) => formatNumber(value) },
      splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
    },
    series: [
      {
        type: "bar",
        name: "广告花费",
        data: props.data.map((point) => point.spend_rub),
        barMaxWidth: 22,
        itemStyle: { color: ink("butter"), borderRadius: [5, 5, 0, 0] },
        emphasis: { focus: "series" },
      },
      {
        type: "bar",
        name: "广告销售额",
        data: props.data.map((point) => point.revenue_rub),
        barMaxWidth: 22,
        itemStyle: { color: ink("azure"), borderRadius: [5, 5, 0, 0] },
        emphasis: { focus: "series" },
      },
    ],
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
  <div ref="chartElement" class="ads-chart" role="img" aria-label="广告花费与广告销售额趋势图" />
</template>
