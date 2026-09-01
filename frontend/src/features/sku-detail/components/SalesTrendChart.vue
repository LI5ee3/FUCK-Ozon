<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, use, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { formatNumber } from "../../../shared/utils/format";
import { macaronTokens } from "../../../theme/tokens";
import { useTheme } from "../../../shared/composables/useTheme";
import type { SkuSalesPoint } from "../types";

use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{ data: SkuSalesPoint[] }>();
const chartElement = ref<HTMLDivElement | null>(null);
const { isDark } = useTheme();
const palette = computed(() => (isDark.value ? macaronTokens.dark : macaronTokens.light));
let chart: ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;

const movingAverage = computed(() => props.data.map((_, index) => {
  const values = props.data.slice(Math.max(0, index - 6), index + 1).map((point) => point.units);
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}));

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ?? character);
}

function option() {
  const colors = palette.value;
  return {
    animationDuration: 240,
    grid: { left: 12, right: 18, top: 30, bottom: 24, containLabel: true },
    legend: { top: 0, right: 0, itemWidth: 12, itemHeight: 8, textStyle: { color: colors.muted, fontFamily: macaronTokens.fontFamily } },
    tooltip: {
      trigger: "axis", confine: true, backgroundColor: colors.panelSolid, borderColor: colors.line,
      textStyle: { color: colors.text, fontFamily: macaronTokens.fontFamily },
      formatter: (params: Array<{ dataIndex?: number }>) => {
        const index = params[0]?.dataIndex ?? 0;
        const point = props.data[index];
        return point ? `<div class="sku-detail-chart-tooltip"><strong>${escapeHtml(point.date)}</strong><div><span>日销量</span><b>${formatNumber(point.units, 0)} 件</b></div><div><span>7日移动平均</span><b>${formatNumber(movingAverage.value[index])} 件</b></div></div>` : "";
      },
    },
    xAxis: { type: "category", data: props.data.map((point) => point.date.slice(5)), axisLine: { lineStyle: { color: colors.line } }, axisTick: { show: false }, axisLabel: { color: colors.muted, interval: Math.max(0, Math.ceil(props.data.length / 8) - 1) } },
    yAxis: { type: "value", min: 0, splitNumber: 3, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: colors.muted, formatter: (value: number) => formatNumber(value, 0) }, splitLine: { lineStyle: { color: colors.line, type: "dashed" } } },
    series: [
      { type: "line", name: "日销量", data: props.data.map((point) => point.units), smooth: false, symbol: "none", lineStyle: { width: 2, color: macaronTokens.tones.azure[isDark.value ? "dark" : "light"].text }, areaStyle: { color: macaronTokens.tones.azure[isDark.value ? "dark" : "light"].bg, opacity: 0.45 } },
      { type: "line", name: "7日移动平均", data: movingAverage.value, smooth: true, symbol: "none", lineStyle: { width: 2, type: "dashed", color: macaronTokens.tones.mint[isDark.value ? "dark" : "light"].text } },
    ],
  };
}

function render(): void { chart?.setOption(option(), true); }

watch([() => props.data, isDark], render, { deep: true });
onMounted(() => {
  if (!chartElement.value) return;
  chart = init(chartElement.value);
  resizeObserver = new ResizeObserver(() => chart?.resize());
  resizeObserver.observe(chartElement.value);
  render();
});
onBeforeUnmount(() => { resizeObserver?.disconnect(); chart?.dispose(); chart = null; });
</script>

<template><div ref="chartElement" class="sku-detail-chart" role="img" aria-label="每日销量与七日移动平均趋势图" /></template>
