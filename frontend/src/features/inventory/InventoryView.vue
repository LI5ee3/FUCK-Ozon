<script setup lang="ts">
import ChannelTag from "../../shared/components/ChannelTag.vue";
import SearchField from "../../shared/components/SearchField.vue";
import "../../styles/analytics.css";
import "./inventory.css";
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch, type VNodeChild } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import type { IconName } from "../../shared/icons/tabler";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NPagination,
  NSelect,
  NSkeleton,
  NTag,
  useMessage,
} from "naive-ui";
import EmptyState from "../../shared/components/EmptyState.vue";
import type { DataTableColumns } from "naive-ui";
import { getErrorMessage } from "../../shared/api/client";
import { copyText } from "../../shared/utils/clipboard";
import { listInventory } from "./api";
import { useShop } from "../../shared/composables/useShop";
import type {
  InventoryChannelStock,
  InventoryResponse,
  InventoryRiskCode,
  InventoryRiskFilter,
  InventoryRow,
  InventorySort,
  SortOrder,
} from "./types";
import type { Channel, ShopSelection } from "../../shared/types/common";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../../shared/utils/format";

type InventorySortKey = Exclude<InventorySort, "">;
type MacaronTone = "azure" | "lavender" | "mint" | "peach" | "butter";
type InventoryFilters = {
  shopId: ShopSelection;
  sku: string;
  offerId: string;
  productName: string;
  channel: Channel | "";
  risk: InventoryRiskFilter;
  page: number;
  sortBy: InventorySort;
  sortOrder: SortOrder;
};

const PAGE_SIZE = 50;
const { selectedShopId } = useShop();
const message = useMessage();
const filters = reactive<InventoryFilters>({
  shopId: selectedShopId.value,
  sku: "",
  offerId: "",
  productName: "",
  channel: "",
  risk: "attention",
  page: 1,
  sortBy: "",
  sortOrder: "desc",
});
const response = ref<InventoryResponse | null>(null);
const items = ref<InventoryRow[]>([]);
const total = ref(0);
const loading = ref(false);
const error = ref("");
let requestId = 0;

const summary = computed(() => response.value?.summary ?? null);
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)));
const hasActiveFilters = computed(() => Boolean(
  filters.sku || filters.offerId || filters.productName || filters.channel || filters.risk !== "attention",
));
const emptyDescription = computed(() => {
  if (error.value) return "库存加载失败";
  if (hasActiveFilters.value) return "当前筛选条件下没有库存或近期销量记录";
  return "当前店铺暂无库存或近期销量记录；库存为 0 的 SKU 会正常显示。";
});
const summaryCards = computed<Array<{ icon: IconName; label: string; value: string; note: string; tone: string }>>(() => {
  const value = summary.value;
  if (!value) return [];
  return [
    { icon: "alertTriangle", label: "需要补货 SKU", value: `${formatInteger(value.need_replenishment_skus)} 款`, note: "缺货、紧急补货或需要补货", tone: value.need_replenishment_skus ? "butter" : "mint" },
    { icon: "clock", label: "到货前可能缺货", value: `${formatInteger(value.stockout_before_arrival_skus)} 款`, note: "可售天数小于补货交期", tone: value.stockout_before_arrival_skus ? "peach" : "mint" },
    { icon: "calendar", label: "预计缺货 SKU", value: `${formatInteger(value.expected_stockout_skus)} 款`, note: "有正预测日销且可计算缺货日期", tone: value.expected_stockout_skus ? "butter" : "mint" },
    { icon: "shoppingBag", label: "FBP建议补货总件数", value: `${formatInteger(value.recommended_replenishment_total)} 件`, note: "按 FBP 库存与到货后目标计算", tone: value.recommended_replenishment_total ? "azure" : "mint" },
    { icon: "box", label: "FBP有效库存", value: `${formatInteger(value.effective_stock)} 件`, note: "仅用于补货计算；预留单独展示", tone: "mint" },
  ];
});

const channelOptions = [
  { label: "默认（FBP 补货口径）", value: "" },
  { label: "FBP 参考口径", value: "FBP" },
  { label: "realFBS 参考口径", value: "realFBS" },
  { label: "WHD 参考口径", value: "WHD" },
];
const riskOptions = [
  { label: "需要关注", value: "attention" },
  { label: "全部风险", value: "" },
  { label: "缺货", value: "out_of_stock" },
  { label: "紧急补货", value: "urgent_replenishment" },
  { label: "需要补货", value: "replenish" },
  { label: "库存充足", value: "sufficient" },
  { label: "库存偏高", value: "overstock" },
  { label: "无近期销量", value: "no_recent_sales" },
];

function isChannel(value: string | number | null): value is Channel {
  return value === "FBP" || value === "realFBS" || value === "WHD";
}

function isRisk(value: string | number | null): value is InventoryRiskFilter {
  return value === "" || value === "attention" || value === "out_of_stock" || value === "urgent_replenishment"
    || value === "replenish" || value === "sufficient" || value === "overstock" || value === "no_recent_sales";
}

function formatOptional(value: number | null | undefined, digits = 2): string {
  return value == null ? "—" : formatNumber(value, digits);
}

function formatShare(value: number | null): string {
  return value == null ? "—" : `${formatNumber(value * 100, 1)}%`;
}

async function loadInventory(): Promise<void> {
  const currentRequest = ++requestId;
  loading.value = true;
  error.value = "";
  response.value = null;
  items.value = [];
  total.value = 0;
  try {
    const data = await listInventory({
      shopId: filters.shopId,
      page: filters.page,
      size: PAGE_SIZE,
      sku: filters.sku.trim() || undefined,
      offerId: filters.offerId.trim() || undefined,
      productName: filters.productName.trim() || undefined,
      channel: filters.channel || undefined,
      risk: filters.risk || undefined,
      sortBy: filters.sortBy || undefined,
      sortOrder: filters.sortOrder,
    });
    if (currentRequest !== requestId) return;
    const nextPageCount = Math.max(1, Math.ceil(data.total / (data.size || PAGE_SIZE)));
    if (filters.page > nextPageCount) {
      filters.page = nextPageCount;
      void loadInventory();
      return;
    }
    response.value = data;
    items.value = data.items;
    total.value = data.total;
  } catch (cause) {
    if (currentRequest !== requestId) return;
    error.value = getErrorMessage(cause);
    message.error(error.value);
  } finally {
    if (currentRequest === requestId) loading.value = false;
  }
}

function submitFilters(): void {
  filters.page = 1;
  void loadInventory();
}

function resetFilters(): void {
  filters.sku = "";
  filters.offerId = "";
  filters.productName = "";
  filters.channel = "";
  filters.risk = "attention";
  filters.page = 1;
  void loadInventory();
}

function updateChannel(value: string | number | null): void {
  filters.channel = isChannel(value) ? value : "";
  filters.page = 1;
  void loadInventory();
}

function updateRisk(value: string | number | null): void {
  if (!isRisk(value)) return;
  filters.risk = value;
  filters.page = 1;
  void loadInventory();
}

function changePage(page: number): void {
  if (page === filters.page) return;
  filters.page = page;
  void loadInventory();
}

function toggleSort(key: InventorySortKey): void {
  filters.sortOrder = filters.sortBy === key && filters.sortOrder === "desc" ? "asc" : "desc";
  filters.sortBy = key;
  filters.page = 1;
  void loadInventory();
}

async function copyValue(value: string): Promise<void> {
  try {
    await copyText(value);
    message.success(`已复制：${value}`);
  } catch {
    message.error("复制失败");
  }
}

function rowKey(row: InventoryRow): string {
  return `${row.shop_id}:${row.sku}`;
}

function channelStock(row: InventoryRow, channel: Channel): InventoryChannelStock | undefined {
  return row.channels.find((item) => item.channel === channel);
}

function riskTone(risk: InventoryRiskCode): MacaronTone | "" {
  if (risk === "out_of_stock" || risk === "urgent_replenishment") return "peach";
  if (risk === "replenish" || risk === "overstock") return "butter";
  if (risk === "sufficient") return "mint";
  return "";
}

function riskIcon(risk: InventoryRiskCode): IconName {
  if (risk === "out_of_stock" || risk === "urgent_replenishment") return "alertTriangle";
  if (risk === "replenish") return "shoppingBag";
  if (risk === "sufficient") return "check";
  if (risk === "overstock") return "clock";
  return "helpCircle";
}

function renderCopyValue(value: string, label: string): VNodeChild {
  return value
    ? h("button", {
        type: "button",
        class: "inventory-copy-value",
        title: `点击复制${label}`,
        onClick: (event: MouseEvent) => {
          event.stopPropagation();
          void copyValue(value);
        },
      }, value)
    : h("b", { class: "inventory-null" }, "暂无");
}

function renderProductCell(row: InventoryRow): VNodeChild {
  return h("div", { class: "inventory-product-cell" }, [
    h("strong", { class: "inventory-product-name", title: row.display_name }, row.display_name),
    row.short_name && row.product_name_raw
      ? h("small", { class: "inventory-raw-name", title: row.product_name_raw }, `原名 ${row.product_name_raw}`)
      : null,
    h("div", { class: "inventory-meta-chips" }, [
      h("span", { class: "analytics-shop-badge" }, row.shop_name),
      h("span", { class: "inventory-meta-chip" }, [h("span", { class: "inventory-meta-label" }, "SKU"), renderCopyValue(row.sku, "SKU")]),
      h("span", { class: "inventory-meta-chip" }, [h("span", { class: "inventory-meta-label" }, "货号"), renderCopyValue(row.offer_id, "货号")]),
    ]),
    h("details", { class: "inventory-forecast-details" }, [
      h("summary", "查看计算"),
      h("div", `7日均销 ${formatOptional(row.daily_7)} · 15日均销 ${formatOptional(row.daily_15)} · 30日均销 ${formatOptional(row.daily_30)}`),
      h("div", `使用窗口：${row.forecast_windows_used.join(" / ") || "无"} 天${row.forecast_adjusted_for_stockout ? " · 已按确认缺货日修正" : " · 未确认全天缺货，不修正"}`),
      h("div", `备货交期 ${formatInteger(row.lead_time_days)} 天 · 到货后${formatInteger(row.target_cover_days)}天需求 ${formatOptional(row.target_stock_after_arrival)} 件`),
      h("div", `广告订单占比 ${formatShare(row.ad_order_share)}`),
    ]),
  ]);
}

function renderChannelCell(row: InventoryRow, channel: Channel): VNodeChild {
  const stock = channelStock(row, channel);
  return h("div", { class: "inventory-channel-cell" }, [
    h("strong", { class: stock?.present ? "inventory-channel-value" : "inventory-channel-value is-zero" }, stock ? formatInteger(stock.present) : "—"),
    h("small", { class: "inventory-channel-sub" }, stock
      ? ["预留 ", h("b", formatInteger(stock.reserved))]
      : "API未返回"),
  ]);
}

function renderEffectiveStock(row: InventoryRow): VNodeChild {
  return h("div", { class: "inventory-metric-cell" }, [
    h("strong", formatInteger(row.current_stock)),
    h("small", ["预留 ", h("b", formatInteger(row.reserved_stock)), " · FBP补货基准"]),
  ]);
}

function renderSales(row: InventoryRow): VNodeChild {
  return h("div", { class: "inventory-sales-list" }, [
    h("span", ["7天 ", h("b", `${formatInteger(row.sales_7)} 件`)]),
    h("span", ["15天 ", h("b", `${formatInteger(row.sales_15)} 件`)]),
    h("span", ["30天 ", h("b", `${formatInteger(row.sales_30)} 件`)]),
  ]);
}

function renderForecast(row: InventoryRow): VNodeChild {
  const daysClass = row.days_cover !== null && row.days_cover < row.lead_time_days
    ? "is-danger"
    : row.days_cover !== null && row.days_cover < 90
      ? "is-warning"
      : "";
  return h("div", { class: "inventory-metric-cell" }, [
    h("strong", [row.risk_code === "no_recent_sales" ? "—" : formatOptional(row.forecast_daily), h("small", " 件/天")]),
    h("small", { class: `inventory-days-cover ${daysClass}` }, `FBP可售 ${formatOptional(row.days_cover, 1)} 天`),
  ]);
}

function renderStockout(row: InventoryRow): VNodeChild {
  return h("div", { class: "inventory-metric-cell" }, [
    h("strong", row.expected_stockout_date ?? "—"),
    h("small", `到货时 FBP ${formatOptional(row.projected_stock_at_arrival)} 件`),
  ]);
}

function renderDecision(row: InventoryRow): VNodeChild {
  const tone = riskTone(row.risk_code);
  return h("div", { class: "inventory-decision-cell" }, [
    h(NTag, {
      bordered: false,
      round: true,
      size: "small",
      type: "default",
      class: tone ? `inventory-risk-tag inventory-tone-tag--${tone}` : "inventory-risk-tag",
    }, {
      default: () => h("span", { class: "inventory-tag-content" }, [
        h(MorphIcon, { icon: riskIcon(row.risk_code), size: "12", strokeWidth: "2" }),
        row.risk_status,
      ]),
    }),
    h("span", { class: "inventory-replenishment" }, ["FBP建议补货 ", h("b", `${formatInteger(row.recommended_replenishment)} 件`)]),
    h("small", { class: "inventory-observed-at" }, `更新：${formatBeijingDateTime(row.observed_at)}`),
  ]);
}

function sortTitle(label: string, key: InventorySortKey, channel?: Channel): VNodeChild {
  const active = filters.sortBy === key;
  const icon = active ? (filters.sortOrder === "asc" ? "arrowUp" : "arrowDown") : "sortUpDown";
  return h("button", {
    type: "button",
    class: "inventory-sort-button",
    "aria-label": `按${label}排序`,
    "aria-pressed": active,
    onClick: () => toggleSort(key),
  }, [
    channel ? h(ChannelTag, { channel }, { default: () => label }) : h("span", label),
    h(MorphIcon, { icon, size: "13", strokeWidth: "1.7" }),
  ]);
}

const columns = computed<DataTableColumns<InventoryRow>>(() => [
  { key: "product", title: "商品 / SKU", width: 360, fixed: "left", render: renderProductCell },
  { key: "fbp", title: () => sortTitle("FBP", "fbp", "FBP"), width: 132, align: "right", render: (row) => renderChannelCell(row, "FBP") },
  { key: "realfbs", title: () => sortTitle("realFBS", "realfbs", "realFBS"), width: 132, align: "right", render: (row) => renderChannelCell(row, "realFBS") },
  { key: "whd", title: () => sortTitle("WHD", "whd", "WHD"), width: 132, align: "right", render: (row) => renderChannelCell(row, "WHD") },
  { key: "effective_stock", title: "FBP有效库存", width: 150, align: "right", render: renderEffectiveStock },
  { key: "sales", title: "7 / 15 / 30 天销量", width: 150, align: "right", render: renderSales },
  { key: "forecast", title: () => sortTitle("预测日销 / FBP可售天数", "forecast"), width: 180, align: "right", render: renderForecast },
  { key: "stockout", title: "FBP预计缺货 / 到货时FBP库存", width: 210, align: "right", render: renderStockout },
  { key: "replenishment", title: () => sortTitle("FBP风险 / FBP建议补货", "replenishment"), width: 190, align: "center", render: renderDecision },
]);

watch(selectedShopId, (shopId) => {
  filters.shopId = shopId;
  filters.page = 1;
  void loadInventory();
});

onMounted(() => {
  filters.shopId = selectedShopId.value;
  void loadInventory();
});

onBeforeUnmount(() => {
  requestId += 1;
});
</script>

<template>
  <section class="inventory-view">
    <div v-if="summaryCards.length || loading" class="inventory-kpi-grid">
      <template v-if="summaryCards.length">
        <NCard v-for="card in summaryCards" :key="card.label" :bordered="false" class="analytics-kpi-card" :class="`tone-${card.tone}`">
          <div class="analytics-kpi-head"><span>{{ card.label }}</span><span class="analytics-icon-badge tone-badge"><morph-icon :icon="card.icon" size="18" stroke-width="1.8" /></span></div>
          <strong class="analytics-kpi-value tone-value">{{ card.value }}</strong>
          <small>{{ card.note }}</small>
        </NCard>
      </template>
      <template v-else>
        <NCard v-for="i in 5" :key="i" :bordered="false" class="analytics-kpi-card">
          <NSkeleton text width="55%" />
          <NSkeleton text width="72%" class="kpi-skeleton-value" />
          <NSkeleton text width="42%" />
        </NCard>
      </template>
    </div>

    <NAlert v-if="error" type="error" class="analytics-error" :title="error">
      <div class="analytics-error-content"><span>库存列表未更新，请重试。</span><NButton size="small" @click="loadInventory">重试</NButton></div>
    </NAlert>

    <NCard :bordered="false" class="analytics-table-card">
      <template #header>
        <div class="analytics-panel-heading">
          <div>
            <h2><morph-icon icon="stock" size="18" stroke-width="1.8" />库存预测与补货建议</h2>
            <span>预测销量 = FBP + realFBS；补货库存仅使用 FBP；WHD 不参与预测｜销量截至昨日完整自然日｜未计入在途库存</span>
          </div>
          <span class="analytics-data-through">
            <span class="analytics-data-dot" aria-hidden="true" />库存更新至
            <strong>{{ response ? formatBeijingDateTime(response.data_through) : "暂无" }}</strong>
            <span>｜销量截至 {{ response?.sales_window_end ?? "昨日" }}（完整自然日）</span>
          </span>
        </div>
      </template>

      <form class="inventory-filter" @submit.prevent="submitFilters">
        <SearchField v-model:value="filters.sku" placeholder="搜索 SKU…" aria-label="筛选SKU" @keydown.enter.prevent="submitFilters" />
        <SearchField v-model:value="filters.offerId" placeholder="搜索货号…" aria-label="筛选货号" @keydown.enter.prevent="submitFilters" />
        <SearchField v-model:value="filters.productName" class="inventory-product-search" placeholder="搜索商品名称或中文短名称…" aria-label="筛选产品名称" @keydown.enter.prevent="submitFilters" />
        <label class="inventory-select-label"><span>库存参考口径</span><NSelect :value="filters.channel" :options="channelOptions" aria-label="库存参考口径" @update:value="updateChannel" /></label>
        <label class="inventory-select-label"><span>风险</span><NSelect :value="filters.risk" :options="riskOptions" aria-label="库存预测风险筛选" @update:value="updateRisk" /></label>
        <div class="inventory-filter-actions">
          <NButton type="primary" attr-type="submit" :loading="loading"><template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>查询</NButton>
          <NButton attr-type="button" @click="resetFilters"><template #icon><morph-icon icon="rotateCcw" size="14" stroke-width="2" /></template>重置</NButton>
        </div>
      </form>

      <div class="analytics-table-meta"><span>共 {{ formatInteger(total) }} 个 SKU</span><span v-if="loading" class="analytics-loading-label">正在加载…</span></div>
      <NDataTable
        class="analytics-table"
        :columns="columns"
        :data="items"
        :loading="loading"
        :pagination="false"
        :remote="true"
        :scroll-x="1636"
        table-layout="fixed"
        :row-key="rowKey"
      >
        <template #empty><EmptyState :title="emptyDescription" icon="stock" /></template>
      </NDataTable>

      <div class="analytics-pager">
        <span>第 {{ filters.page }} / {{ pageCount }} 页，共 {{ formatInteger(total) }} 个 SKU</span>
        <NPagination :page="filters.page" :page-count="pageCount" :page-size="PAGE_SIZE" :disabled="loading" :page-slot="7" @update:page="changePage" />
      </div>
    </NCard>
  </section>
</template>
