<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch, type VNodeChild } from "vue";
import type { LocationQuery } from "vue-router";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NInputNumber,
  NPagination,
  NSelect,
  NTag,
} from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import EmptyState from "../../shared/components/EmptyState.vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import SearchField from "../../shared/components/SearchField.vue";
import "../../styles/analytics.css";
import "./pricing.css";
import { getErrorMessage } from "../../shared/api/client";
import { useShop } from "../../shared/composables/useShop";
import type { IconName } from "../../shared/icons/tabler";
import type { Channel, ShopSelection } from "../../shared/types/common";
import { formatBeijingDateTime, formatInteger } from "../../shared/utils/format";
import { positiveInteger, queryMatches, queryValue, shopSelectionFromQuery } from "../../shared/utils/query";
import { listPricing } from "./api";
import type {
  PricingHealth,
  PricingHealthFilter,
  PricingItem,
  PricingResponse,
  PricingSort,
  SortOrder,
} from "./types";

type PricingFilters = {
  shopId: ShopSelection;
  q: string;
  channel: Channel;
  health: PricingHealthFilter;
  targetMarginPct: number;
  sortBy: PricingSort;
  sortOrder: SortOrder;
  page: number;
};

const PAGE_SIZE = 50;
const route = useRoute();
const router = useRouter();
const { selectedShopId, selectShop } = useShop();
const filters = reactive<PricingFilters>(parseFilters(route.query, selectedShopId.value));
const searchDraft = ref(filters.q);
const response = ref<PricingResponse | null>(null);
const loading = ref(false);
const error = ref("");
let requestId = 0;
let routeReady = false;
let ignoreNextShopChange = false;

const channelOptions = [
  { label: "FBP", value: "FBP" },
  { label: "realFBS", value: "realFBS" },
  { label: "WHD", value: "WHD" },
];
const healthOptions = [
  { label: "全部状态", value: "" },
  { label: "数据不完整", value: "incomplete" },
  { label: "预计亏损", value: "loss" },
  { label: "低于目标毛利", value: "low_margin" },
  { label: "红色价格指数", value: "price_red" },
  { label: "黄色价格指数", value: "price_yellow" },
  { label: "暂无价格指数", value: "no_price_index" },
  { label: "健康", value: "healthy" },
];

function isChannel(value: string | number | null): value is Channel {
  return value === "FBP" || value === "realFBS" || value === "WHD";
}

function isHealth(value: string): value is PricingHealthFilter {
  return value === "" || value === "incomplete" || value === "loss" || value === "low_margin"
    || value === "price_red" || value === "price_yellow" || value === "no_price_index" || value === "healthy";
}

function isSort(value: string): value is PricingSort {
  return value === "" || value === "current_price" || value === "sold_price_30" || value === "price_vs_30d"
    || value === "projected_margin" || value === "break_even_price" || value === "target_margin_price"
    || value === "sales_30" || value === "effective_stock" || value === "price_index";
}

function targetMarginFromQuery(value: string): number {
  if (!value.trim()) return 20;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 80 ? parsed : 20;
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): PricingFilters {
  const channel = queryValue(query, "channel");
  const health = queryValue(query, "health");
  const sortBy = queryValue(query, "sort_by");
  return {
    shopId: shopSelectionFromQuery(query, fallbackShop),
    q: queryValue(query, "q").trim(),
    channel: isChannel(channel) ? channel : "FBP",
    health: isHealth(health) ? health : "",
    targetMarginPct: targetMarginFromQuery(queryValue(query, "target_margin_pct")),
    sortBy: isSort(sortBy) ? sortBy : "",
    sortOrder: queryValue(query, "sort_order") === "asc" ? "asc" : "desc",
    page: positiveInteger(queryValue(query, "page"), 1),
  };
}

function queryFor(value: PricingFilters): Record<string, string> {
  const query: Record<string, string> = {
    shop_id: String(value.shopId),
    channel: value.channel,
    target_margin_pct: String(value.targetMarginPct),
  };
  const search = value.q.trim();
  if (search) query.q = search;
  if (value.health) query.health = value.health;
  if (value.sortBy) {
    query.sort_by = value.sortBy;
    query.sort_order = value.sortOrder;
  }
  if (value.page !== 1) query.page = String(value.page);
  return query;
}

function applyRouteQuery(query: LocationQuery, fallbackShop: ShopSelection): PricingFilters {
  const next = parseFilters(query, fallbackShop);
  Object.assign(filters, next);
  searchDraft.value = next.q;
  if (selectedShopId.value !== next.shopId) {
    ignoreNextShopChange = true;
    selectShop(next.shopId);
  }
  return next;
}

function currentFilters(): PricingFilters {
  return { ...filters, q: searchDraft.value.trim() };
}

function updateRoute(next: PricingFilters, replace = false): void {
  const normalized = { ...next, q: next.q.trim() };
  Object.assign(filters, normalized);
  searchDraft.value = normalized.q;
  if (queryMatches(route.query, queryFor(normalized))) {
    void loadPricing(normalized);
    return;
  }
  void (replace ? router.replace({ query: queryFor(normalized) }) : router.push({ query: queryFor(normalized) }));
}

function updateFilters(overrides: Partial<PricingFilters>, replace = false): void {
  updateRoute({ ...currentFilters(), ...overrides }, replace);
}

async function loadPricing(queryFilters: PricingFilters): Promise<void> {
  const currentRequest = ++requestId;
  loading.value = true;
  error.value = "";
  response.value = null;
  try {
    const data = await listPricing({
      shopId: queryFilters.shopId,
      q: queryFilters.q || undefined,
      channel: queryFilters.channel,
      health: queryFilters.health || undefined,
      targetMarginPct: queryFilters.targetMarginPct,
      sortBy: queryFilters.sortBy || undefined,
      sortOrder: queryFilters.sortOrder,
      page: queryFilters.page,
      size: PAGE_SIZE,
    });
    if (currentRequest !== requestId) return;
    const nextPageCount = Math.max(1, Math.ceil(data.total / (data.size || PAGE_SIZE)));
    if (queryFilters.page > nextPageCount) {
      await router.replace({ query: queryFor({ ...queryFilters, page: nextPageCount }) });
      return;
    }
    response.value = data;
  } catch (cause) {
    if (currentRequest === requestId) error.value = getErrorMessage(cause);
  } finally {
    if (currentRequest === requestId) loading.value = false;
  }
}

function retry(): void {
  void loadPricing(currentFilters());
}

function submitSearch(): void {
  updateFilters({ q: searchDraft.value, page: 1 });
}

function clearSearch(): void {
  searchDraft.value = "";
  updateFilters({ q: "", page: 1 });
}

function changeChannel(value: string | number | null): void {
  if (isChannel(value)) updateFilters({ channel: value, page: 1 });
}

function changeHealth(value: string | number | null): void {
  if (typeof value === "string" && isHealth(value)) updateFilters({ health: value, page: 1 });
}

function changeTargetMargin(value: number | null): void {
  if (value !== null && Number.isFinite(value) && value >= 0 && value <= 80) {
    updateFilters({ targetMarginPct: value, page: 1 }, true);
  }
}

function changePage(page: number): void {
  if (page !== filters.page) updateFilters({ page });
}

function formatDecimal(value: string | null, currency: string | null = null): string {
  if (value === null || value.trim() === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  const number = new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(parsed);
  return currency ? `${number} ${currency}` : number;
}

function formatPercent(value: number | null): string {
  return value === null || !Number.isFinite(value) ? "—" : `${value.toFixed(1)}%`;
}

function formatChange(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function healthLabel(value: PricingHealth): string {
  return {
    incomplete: "数据不完整",
    loss: "预计亏损",
    low_margin: "低于目标毛利",
    price_red: "红色价格指数",
    price_yellow: "黄色价格指数",
    no_price_index: "暂无价格指数",
    healthy: "健康",
  }[value];
}

function healthTone(value: PricingHealth): string {
  if (value === "loss" || value === "price_red" || value === "incomplete") return "peach";
  if (value === "low_margin" || value === "price_yellow") return "butter";
  if (value === "healthy") return "mint";
  return "lavender";
}

function priceIndexLabel(value: string | null): string {
  return {
    GREEN: "价格有竞争力",
    YELLOW: "价格一般",
    RED: "价格偏高",
    WITHOUT_INDEX: "暂无指数",
  }[value?.toUpperCase() ?? ""] ?? value ?? "暂无指数";
}

const reasonLabels: Record<string, string> = {
  ambiguous_sku: "SKU 有歧义",
  missing_sku_mapping: "缺 SKU 映射",
  missing_erp_cost: "缺 ERP 成本",
  missing_current_price: "缺当前价格",
  missing_commission: "缺销售佣金",
  missing_acquiring: "缺收单手续费",
  missing_exchange_rate: "缺汇率",
  currency_mismatch: "成交币种不一致",
  break_even_denominator_non_positive: "保本价无有效解",
  target_margin_denominator_non_positive: "目标毛利价无有效解",
};

function formatReasons(reasons: string[]): string {
  return reasons.map((reason) => reasonLabels[reason] ?? reason).join(" · ") || "数据校验异常";
}

function renderProduct(row: PricingItem): VNodeChild {
  const product = row.product;
  return h("div", { class: "pricing-product-cell" }, [
    h("strong", { class: "pricing-product-name", title: product.display_name }, product.display_name || product.product_identity),
    product.sku
      ? h(RouterLink, {
          class: "pricing-sku-link",
          to: { name: "sku-detail", params: { sku: product.sku }, query: { shop_id: String(row.shop_id) } },
        }, { default: () => `SKU ${product.sku}` })
      : h("span", { class: "pricing-muted" }, "SKU 未明确"),
    h("span", { class: "pricing-meta" }, `Offer ID ${product.offer_id ?? "—"} · ${row.shop_name}`),
  ]);
}

function renderPrice(row: PricingItem): VNodeChild {
  const price = row.price;
  return h("div", { class: "pricing-metric-cell pricing-price-cell" }, [
    h("strong", formatDecimal(price.effective_price, price.currency)),
    h("small", `基础售价 ${formatDecimal(price.base_price, price.currency)}`),
    price.marketing_seller_price !== null && Number(price.marketing_seller_price) > 0
      ? h("small", { class: "pricing-promotion" }, `卖家促销价 ${formatDecimal(price.marketing_seller_price, price.currency)}`)
      : null,
    h("small", { class: "pricing-muted" }, `更新：${formatBeijingDateTime(price.observed_at)}`),
  ]);
}

function renderSoldPrice(row: PricingItem): VNodeChild {
  const sales = row.sales_30;
  return h("div", { class: "pricing-metric-cell" }, [
    h("strong", formatDecimal(sales.weighted_avg_price, sales.currency)),
    h("small", `${formatInteger(sales.units)} 件 · ${sales.sold_price_status === "currency_mismatch" ? "币种不一致" : "最近30个完整销售日"}`),
  ]);
}

function renderMargin(row: PricingItem): VNodeChild {
  const economics = row.economics;
  return h("div", { class: "pricing-metric-cell" }, [
    h("strong", { class: economics.projected_base_margin_pct !== null && economics.projected_base_margin_pct < 0 ? "is-negative" : "" }, formatPercent(economics.projected_base_margin_pct)),
    h("small", `预计基础利润 ${formatDecimal(economics.projected_base_profit, economics.currency)}`),
  ]);
}

function renderEconomicsPrice(value: string | null, currency: string): VNodeChild {
  return h("span", { class: "pricing-number" }, formatDecimal(value, currency));
}

function renderCompetitiveness(row: PricingItem): VNodeChild {
  const color = row.competitiveness.color_index?.toUpperCase() ?? "";
  const tone = color === "RED" ? "peach" : color === "YELLOW" ? "butter" : color === "GREEN" ? "mint" : "lavender";
  return h("div", { class: "pricing-competitiveness-cell" }, [
    h(NTag, { bordered: false, round: true, size: "small", class: `pricing-tone-tag--${tone}` }, {
      default: () => h("span", { title: color || "WITHOUT_INDEX" }, priceIndexLabel(color || null)),
    }),
    h("small", `Ozon index ${formatDecimal(row.competitiveness.ozon.index)}`),
    h("small", `External ${formatDecimal(row.competitiveness.external.index)}`),
    h("small", `Self ${formatDecimal(row.competitiveness.self_marketplace.index)}`),
  ]);
}

function renderStock(row: PricingItem): VNodeChild {
  const stock = row.stock;
  return h("div", { class: "pricing-metric-cell" }, [
    h("strong", stock.effective_stock === null ? "—" : formatInteger(stock.effective_stock)),
    h("small", stock.present === null ? "暂无库存快照" : `现货 ${formatInteger(stock.present)} · 预留 ${formatInteger(stock.reserved)}`),
    h("small", { class: "pricing-muted" }, stock.observed_at ? `更新：${formatBeijingDateTime(stock.observed_at)}` : ""),
  ]);
}

function renderHealth(row: PricingItem): VNodeChild {
  const primary = row.primary_health;
  return h("div", { class: "pricing-health-cell" }, [
    h(NTag, { bordered: false, round: true, size: "small", class: `pricing-tone-tag--${healthTone(primary)}` }, {
      default: () => healthLabel(primary),
    }),
    row.health_flags.length > 1
      ? h("small", { title: row.health_flags.map(healthLabel).join(" · ") }, `另有 ${row.health_flags.length - 1} 项状态`)
      : null,
    primary === "incomplete"
      ? h("small", { class: "pricing-reasons", title: formatReasons(row.economics.incomplete_reasons) }, formatReasons(row.economics.incomplete_reasons))
      : null,
  ]);
}

const columns: DataTableColumns<PricingItem> = [
  { key: "product", title: "商品", width: 260, fixed: "left", render: renderProduct },
  { key: "current_price", title: "当前测算售价", width: 190, align: "right", render: renderPrice },
  { key: "sold_price_30", title: "30天成交均价", width: 165, align: "right", render: renderSoldPrice },
  { key: "price_vs_30d", title: "价格变化", width: 120, align: "right", render: (row) => h("span", { class: ["pricing-number", { "is-negative": (row.sales_30.price_vs_30d_pct ?? 0) < 0 }] }, formatChange(row.sales_30.price_vs_30d_pct)) },
  { key: "projected_margin", title: "预计基础毛利率", width: 190, align: "right", render: renderMargin },
  { key: "break_even_price", title: "基础保本价", width: 160, align: "right", render: (row) => renderEconomicsPrice(row.economics.break_even_price, row.economics.currency) },
  { key: "target_margin_price", title: "目标毛利价", width: 160, align: "right", render: (row) => renderEconomicsPrice(row.economics.target_margin_price, row.economics.currency) },
  { key: "price_index", title: "价格竞争力", width: 185, render: renderCompetitiveness },
  { key: "sales_30", title: "30天销量", width: 110, align: "right", render: (row) => h("span", { class: "pricing-number" }, `${formatInteger(row.sales_30.units)} 件`) },
  { key: "effective_stock", title: "当前库存", width: 150, align: "right", render: renderStock },
  { key: "health", title: "状态", width: 180, render: renderHealth },
];

const summaryCards = computed<Array<{ icon: IconName; label: string; value: string; note: string; tone: string }>>(() => {
  const summary = response.value?.summary;
  if (!summary) return [];
  return [
    { icon: "tag", label: "价格商品", value: `${formatInteger(summary.products)} 款`, note: "当前完整价格批次中的商品", tone: "azure" },
    { icon: "alertTriangle", label: "预计亏损", value: `${formatInteger(summary.loss)} 款`, note: "预计基础利润小于 0", tone: summary.loss ? "peach" : "mint" },
    { icon: "percent", label: "低于目标毛利", value: `${formatInteger(summary.low_margin)} 款`, note: "预计基础毛利率低于当前目标", tone: summary.low_margin ? "butter" : "mint" },
    { icon: "activity", label: "红色价格指数", value: `${formatInteger(summary.price_red)} 款`, note: "保留 Ozon 原始颜色状态", tone: summary.price_red ? "peach" : "mint" },
    { icon: "alertCircle", label: "数据不完整", value: `${formatInteger(summary.incomplete)} 款`, note: "成本、佣金、汇率或映射缺失", tone: summary.incomplete ? "lavender" : "mint" },
  ];
});

const total = computed(() => response.value?.total ?? 0);
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)));
const emptyTitle = computed(() => {
  if (error.value) return "价格分析加载失败";
  if (response.value?.freshness.prices.status === "missing") return "暂无价格快照，请先在「数据同步中心」同步商品价格。";
  return "当前筛选条件下没有价格分析商品";
});

watch(() => route.fullPath, () => {
  if (!routeReady) return;
  const next = applyRouteQuery(route.query, selectedShopId.value);
  void loadPricing(next);
});

watch(selectedShopId, (shopId) => {
  if (ignoreNextShopChange) {
    ignoreNextShopChange = false;
    return;
  }
  if (!routeReady || filters.shopId === shopId) return;
  updateFilters({ shopId, page: 1 });
});

onMounted(() => {
  const next = applyRouteQuery(route.query, selectedShopId.value);
  routeReady = true;
  if (!queryMatches(route.query, queryFor(next))) {
    void router.replace({ query: queryFor(next) });
  } else {
    void loadPricing(next);
  }
});

onBeforeUnmount(() => { requestId += 1; });
</script>

<template>
  <section class="pricing-view">
    <div v-if="summaryCards.length" class="analytics-kpi-grid pricing-kpi-grid">
      <NCard v-for="card in summaryCards" :key="card.label" :bordered="false" class="analytics-kpi-card" :class="`tone-${card.tone}`">
        <div class="analytics-kpi-head"><span>{{ card.label }}</span><span class="analytics-icon-badge tone-badge"><morph-icon :icon="card.icon" size="18" stroke-width="1.8" /></span></div>
        <strong class="analytics-kpi-value tone-value">{{ card.value }}</strong>
        <small>{{ card.note }}</small>
      </NCard>
    </div>

    <NAlert v-if="error" type="error" class="analytics-error" :title="error">
      <div class="analytics-error-content"><span>价格分析未更新，请重试。</span><NButton size="small" @click="retry">重试</NButton></div>
    </NAlert>

    <NCard :bordered="false" class="analytics-table-card pricing-panel">
      <template #header>
        <div class="analytics-panel-heading">
          <div>
            <h2><morph-icon icon="percent" size="18" stroke-width="1.8" />价格分析中心</h2>
            <span>当前价格、30天成交、ERP 成本、基础利润、价格指数与库存的只读关联观察</span>
          </div>
          <span class="analytics-data-through"><span class="analytics-data-dot" aria-hidden="true" />分析至 <strong>{{ response ? formatBeijingDateTime(response.as_of) : "暂无" }}</strong></span>
        </div>
      </template>

      <p class="pricing-model-note">预计基础利润用于定价参考，不等于 Actual Profit 实际利润；当前仅计入 ERP 采购成本、销售佣金和最高收单手续费。</p>

      <form class="pricing-filter" role="search" @submit.prevent="submitSearch">
        <SearchField v-model:value="searchDraft" placeholder="搜索商品名称、SKU、Offer ID 或 Product ID…" aria-label="搜索价格分析商品" @keydown.enter.prevent="submitSearch" @clear="clearSearch" @debounced-change="submitSearch" />
        <label class="pricing-select-label"><span>参考履约模式</span><NSelect :value="filters.channel" :options="channelOptions" aria-label="参考履约模式" @update:value="changeChannel" /></label>
        <label class="pricing-number-label"><span>目标基础毛利率</span><NInputNumber :value="filters.targetMarginPct" :min="0" :max="80" :step="1" :precision="2" aria-label="目标基础毛利率" @update:value="changeTargetMargin" /></label>
        <label class="pricing-select-label"><span>健康状态</span><NSelect :value="filters.health" :options="healthOptions" aria-label="价格健康状态" @update:value="changeHealth" /></label>
        <NButton type="primary" attr-type="submit" :loading="loading"><template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>查询</NButton>
      </form>

      <div class="pricing-freshness">
        <span>参考模式：<strong>{{ response?.reference_channel ?? filters.channel }}</strong></span>
        <span>销售窗口：{{ response?.sales_window.from ?? "—" }} 至 {{ response?.sales_window.to ?? "—" }}（30 个完整销售日）</span>
        <span v-if="loading" class="analytics-loading-label">正在加载…</span>
      </div>

      <div class="analytics-table-meta"><span>共 {{ formatInteger(total) }} 个价格实体</span><span v-if="response" class="pricing-currency-note">金额按各店铺结算币种展示</span></div>
      <NDataTable
        class="analytics-table pricing-table"
        :columns="columns"
        :data="response?.items ?? []"
        :loading="loading"
        :pagination="false"
        :remote="true"
        :scroll-x="1860"
        table-layout="fixed"
        :row-key="(row: PricingItem) => row.row_key"
      >
        <template #empty><EmptyState :title="emptyTitle" :hint="error ? '请点击上方重试。' : undefined" icon="percent" /></template>
      </NDataTable>

      <div class="analytics-pager pricing-pager">
        <span>第 {{ filters.page }} / {{ pageCount }} 页，共 {{ formatInteger(total) }} 个价格实体</span>
        <NPagination :page="filters.page" :page-count="pageCount" :page-size="PAGE_SIZE" :disabled="loading" :page-slot="7" @update:page="changePage" />
      </div>
    </NCard>
  </section>
</template>
