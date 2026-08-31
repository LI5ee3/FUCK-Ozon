<script setup lang="ts">
import ChannelTag from "../../shared/components/ChannelTag.vue";
import SearchField from "../../shared/components/SearchField.vue";
import DatePresetPills from "../../shared/components/DatePresetPills.vue";
import "./orders.css";
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch, type VNodeChild } from "vue";
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
  NPagination,
  NSelect,
  NSkeleton,
  NTag,
  useMessage,
} from "naive-ui";
import EmptyState from "../../shared/components/EmptyState.vue";
import type { DataTableColumns } from "naive-ui";
import { getErrorMessage } from "../../shared/api/client";
import { listOrders } from "./api";
import { useShop } from "../../shared/composables/useShop";
import type {
  Order,
  OrderStatusCounts,
  OrderStatusFilter,
} from "./types";
import type { Channel, ShopSelection } from "../../shared/types/common";
import { formatBeijingDateTime, formatInteger, formatMoney, formatNumber } from "../../shared/utils/format";
import { beijingThreeMonthRange, parseValidDateRange, standardDatePresetRange, type DateRange, type StandardDatePreset } from "../../shared/utils/date";
import { positiveInteger, queryMatches, queryValue, shopSelectionFromQuery } from "../../shared/utils/query";
import OrderDetailPanel from "./components/OrderDetailPanel.vue";

type DatePreset = StandardDatePreset;
type ToneName = "azure" | "lavender" | "mint" | "peach" | "butter";
type OrderFilters = {
  shopId: ShopSelection;
  channel: Channel | "";
  status: OrderStatusFilter;
  search: string;
  page: number;
  from: string;
  to: string;
};
type TagType = "default" | "info" | "success" | "warning" | "error";

const PAGE_SIZE = 30;
const route = useRoute();
const router = useRouter();
const message = useMessage();
const { selectedShopId, selectShop } = useShop();
const initialFilters = parseFilters(route.query, selectedShopId.value);
const filters = reactive<OrderFilters>(initialFilters);
const searchDraft = ref(initialFilters.search);
const orders = ref<Order[]>([]);
const total = ref(0);
const statusCounts = ref<OrderStatusCounts | null>(null);
const loading = ref(false);
const error = ref("");
const expandedRowKeys = ref<Array<string | number>>([]);
let requestId = 0;
let routeReady = false;
let ignoreNextShopChange = false;

const channelOptions = [
  { label: "全部渠道", value: "" },
  { label: "FBP", value: "FBP" },
  { label: "realFBS", value: "realFBS" },
  { label: "WHD", value: "WHD" },
];
// Tone roles per DESIGN.md: azure=primary, lavender=pending, mint=fulfillment, peach=cancellations.
const statusCards: ReadonlyArray<{
  key: OrderStatusFilter;
  label: string;
  icon: IconName;
  tone: ToneName;
  countKey: keyof OrderStatusCounts;
  noteKey: keyof OrderStatusCounts | "share";
}> = [
  { key: "", label: "全部订单", icon: "layers", tone: "azure", countKey: "all", noteKey: "anomaly" },
  { key: "pending", label: "待备货", icon: "box", tone: "lavender", countKey: "pending", noteKey: "share" },
  { key: "shipping", label: "运输中", icon: "truck", tone: "butter", countKey: "shipping", noteKey: "share" },
  { key: "delivered", label: "已签收", icon: "checkCircle", tone: "mint", countKey: "delivered", noteKey: "share" },
  { key: "cancelled", label: "已取消", icon: "alertTriangle", tone: "peach", countKey: "cancelled", noteKey: "cancelled_shipped" },
];
const datePresets: ReadonlyArray<{ key: DatePreset; label: string }> = [
  { key: "today", label: "今天" },
  { key: "3days", label: "3天内" },
  { key: "7days", label: "7天内" },
  { key: "3months", label: "近三个月" },
  { key: "all", label: "全部时间" },
];
const dateRange = computed<DateRange>(() => [filters.from, filters.to]);
const activePreset = computed<DatePreset | "">(() => {
  for (const preset of datePresets) {
    const [from, to] = standardDatePresetRange(preset.key);
    if (filters.from === from && filters.to === to) return preset.key;
  }
  return "";
});
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)));

function isChannel(value: string): value is Channel {
  return value === "FBP" || value === "realFBS" || value === "WHD";
}

function isStatusFilter(value: string): value is Exclude<OrderStatusFilter, ""> {
  return value === "pending" || value === "shipping" || value === "delivered" || value === "cancelled";
}

function parseDateRange(from: string, to: string): DateRange {
  return parseValidDateRange(from, to, beijingThreeMonthRange());
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): OrderFilters {
  const status = queryValue(query, "status");
  const channel = queryValue(query, "channel");
  const [from, to] = parseDateRange(queryValue(query, "from"), queryValue(query, "to"));
  return {
    shopId: shopSelectionFromQuery(query, fallbackShop),
    channel: isChannel(channel) ? channel : "",
    status: isStatusFilter(status) ? status : "",
    search: queryValue(query, "q"),
    page: positiveInteger(queryValue(query, "page"), 1),
    from,
    to,
  };
}

function queryFor(filtersValue: OrderFilters): Record<string, string> {
  const defaultRange = beijingThreeMonthRange();
  const query: Record<string, string> = { shop_id: String(filtersValue.shopId) };
  if (filtersValue.page !== 1) query.page = String(filtersValue.page);
  if (filtersValue.channel) query.channel = filtersValue.channel;
  if (filtersValue.status) query.status = filtersValue.status;
  if (filtersValue.search) query.q = filtersValue.search;
  if (filtersValue.from !== defaultRange[0] || filtersValue.to !== defaultRange[1]) {
    query.from = filtersValue.from;
    query.to = filtersValue.to;
  }
  return query;
}

function applyRouteQuery(query: LocationQuery, fallbackShop: ShopSelection): OrderFilters {
  const next = parseFilters(query, fallbackShop);
  Object.assign(filters, next);
  searchDraft.value = next.search;
  if (selectedShopId.value !== next.shopId) {
    ignoreNextShopChange = true;
    selectShop(next.shopId);
  }
  return next;
}

function updateRoute(next: OrderFilters, replace = false): void {
  Object.assign(filters, next);
  searchDraft.value = next.search;
  if (queryMatches(route.query, queryFor(next))) {
    void loadOrders(next);
    return;
  }
  const navigation = replace ? router.replace({ query: queryFor(next) }) : router.push({ query: queryFor(next) });
  void navigation;
}

function currentFilters(): OrderFilters {
  const next = { ...filters, search: searchDraft.value.trim() };
  if (!queryValue(route.query, "from") && !queryValue(route.query, "to")) {
    [next.from, next.to] = beijingThreeMonthRange();
  }
  return next;
}

function updateFilters(overrides: Partial<OrderFilters>, replace = false): void {
  updateRoute({ ...currentFilters(), ...overrides }, replace);
}

async function loadOrders(queryFilters: OrderFilters): Promise<void> {
  const currentRequest = ++requestId;
  loading.value = true;
  error.value = "";
  orders.value = [];
  total.value = 0;
  statusCounts.value = null;
  expandedRowKeys.value = [];
  try {
    const data = await listOrders({
      shopId: queryFilters.shopId,
      channel: queryFilters.channel || undefined,
      status: queryFilters.status || undefined,
      search: queryFilters.search || undefined,
      page: queryFilters.page,
      size: PAGE_SIZE,
      from: queryFilters.from,
      to: queryFilters.to,
    });
    if (currentRequest !== requestId) return;
    const responsePageCount = Math.max(1, Math.ceil(data.total / (data.size || PAGE_SIZE)));
    if (queryFilters.page > responsePageCount) {
      if (queryMatches(queryFor(currentFilters()), queryFor(queryFilters))) {
        await router.replace({ query: queryFor({ ...queryFilters, page: responsePageCount }) });
      }
      return;
    }
    orders.value = data.items;
    total.value = data.total;
    statusCounts.value = data.status_counts;
  } catch (cause) {
    if (currentRequest !== requestId) return;
    error.value = getErrorMessage(cause);
    message.error(error.value);
  } finally {
    if (currentRequest === requestId) loading.value = false;
  }
}

function retry(): void {
  const next = currentFilters();
  Object.assign(filters, next);
  void loadOrders(next);
}

function submitSearch(): void {
  updateFilters({ page: 1, search: searchDraft.value.trim() });
}

function handleChannelChange(value: string | number | null): void {
  updateFilters({ channel: typeof value === "string" && isChannel(value) ? value : "", page: 1 });
}

function handleStatusChange(status: OrderStatusFilter): void {
  updateFilters({ status, page: 1 });
}

function handleDateRangeChange(value: string | DateRange | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  const [from, to] = parseValidDateRange(value[0], value[1], beijingThreeMonthRange());
  if (from !== value[0] || to !== value[1]) return;
  updateFilters({ from, to, page: 1 });
}

function selectPreset(preset: DatePreset): void {
  const [from, to] = standardDatePresetRange(preset);
  updateFilters({ from, to, page: 1 });
}

function changePage(page: number): void {
  if (page !== filters.page) updateFilters({ page });
}

async function copyValue(value: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    message.success(`已复制：${value}`);
  } catch {
    message.error("复制失败");
  }
}

function orderKey(order: Order): string {
  return `${order.shop_id}:${order.posting_number}`;
}

function tagType(order: Order): TagType {
  if (order.status_raw === "已取消" || order.data_anomaly) return "error";
  if (order.status_raw === "已签收") return "success";
  if (/运输|配送|发货|待取件/.test(order.status_raw)) return "info";
  return "warning";
}

function statusIcon(order: Order): IconName {
  if (order.status_raw === "已取消" || order.data_anomaly) return "alertTriangle";
  if (order.status_raw === "已签收") return "checkCircle";
  if (/运输|配送|发货|待取件/.test(order.status_raw)) return "truck";
  return "box";
}

function renderTag(label: string, type: TagType, className = "", icon: IconName | "" = ""): VNodeChild {
  return h(NTag, { bordered: false, round: true, size: "small", type, class: className }, {
    default: () => icon
      ? h("span", { class: "orders-tag-content" }, [h(MorphIcon, { icon, size: "13", strokeWidth: "2" }), label])
      : label,
  });
}

function renderCopyButton(value: string, title: string, className = ""): VNodeChild {
  return h("button", {
    type: "button",
    class: `orders-copy-value ${className}`,
    title,
    onClick: (event: MouseEvent) => {
      event.stopPropagation();
      void copyValue(value);
    },
  }, value);
}

function renderMetaChip(label: string, value: string | null | undefined): VNodeChild {
  return h("span", { class: "orders-meta-chip" }, [
    `${label} `,
    value ? renderCopyButton(value, `点击复制${label}`) : h("b", { class: "orders-null" }, "暂无"),
  ]);
}

function renderOrderCell(order: Order): VNodeChild {
  return h("div", { class: "orders-order-cell" }, [
    renderCopyButton(order.posting_number, "点击复制订单号", "orders-order-number"),
    h("div", { class: "orders-order-tags" }, [
      h("span", { class: "orders-shop-badge" }, order.shop_name),
      h(ChannelTag, { channel: order.channel }),
      order.status_raw === "已取消" ? renderTag(order.shipped ? "发货后取消" : "发货前取消", "error") : null,
      order.data_anomaly ? renderTag("数据异常", "error") : null,
    ]),
  ]);
}

function renderProductCell(order: Order): VNodeChild {
  const first = order.items[0];
  if (!first) return h("div", { class: "orders-product-cell" }, h("strong", "商品信息暂无"));
  const extra = Math.max(0, order.sku_types - 1);
  return h("div", { class: "orders-product-cell" }, [
    h("div", { class: "orders-product-main" }, [
      h("strong", { class: "orders-product-title", title: first.product_name_raw ?? "" }, first.product_name_raw || "商品信息暂无"),
      first.product_name_original && first.product_name_raw !== first.product_name_original
        ? h("span", { class: "orders-product-original", title: first.product_name_original }, first.product_name_original)
        : null,
    ]),
    h("div", { class: "orders-product-meta" }, [
      renderMetaChip("SKU", first.sku),
      renderMetaChip("货号", first.offer_id),
      h("span", { class: "orders-meta-chip orders-meta-chip--quantity" }, `× ${formatInteger(first.quantity)}`),
      extra > 0 ? h("span", { class: "orders-meta-extra" }, `+${extra} 种其他商品`) : null,
    ]),
    order.cancel_reason_raw
      ? h("div", { class: "orders-cancel-reason", title: order.cancel_reason_raw }, [
          h(MorphIcon, { icon: "alertTriangle", size: "12", strokeWidth: "2" }),
          order.cancel_reason_raw,
        ])
      : null,
  ]);
}

function renderStatusCell(order: Order): VNodeChild {
  return h("div", { class: "orders-status-cell" }, [
    renderTag(order.status_raw || "未知状态", tagType(order), "orders-status-tag", statusIcon(order)),
    h("span", { class: "orders-time-stamp" }, [
      h(MorphIcon, { icon: "clock", size: "12", strokeWidth: "1.8" }),
      formatBeijingDateTime(order.created_at),
    ]),
    h("small", { class: "orders-count-meta" }, `${formatInteger(order.sku_types)} 种 SKU · 共 ${formatInteger(order.pieces)} 件`),
  ]);
}

function renderAmountCell(order: Order): VNodeChild {
  return h("div", { class: "orders-amount-cell" }, [
    h("strong", { class: "orders-amount" }, formatMoney(order.amount_original, order.amount_currency ?? "")),
    h("span", { class: "orders-expand-hint" }, expandedRowKeys.value.includes(orderKey(order)) ? "收起详情" : "展开详情"),
  ]);
}

function renderExpandIcon({ expanded }: { expanded: boolean }): VNodeChild {
  const label = expanded ? "收起订单详情" : "展开订单详情";
  return h(NButton, { quaternary: true, circle: true, size: "tiny", "aria-label": label, title: label, "aria-expanded": expanded }, {
    icon: () => h(MorphIcon, { icon: expanded ? "chevronDown" : "chevronRight", size: 14 }),
  });
}

const columns = computed<DataTableColumns<Order>>(() => [
  {
    type: "expand",
    width: 48,
    renderExpand: (order) => h(OrderDetailPanel, { order, copyValue }),
  },
  { key: "order", title: "订单", width: 210, render: renderOrderCell },
  { key: "product", title: "商品信息", width: 330, render: renderProductCell },
  { key: "status", title: "状态与时间", width: 190, render: renderStatusCell },
  { key: "amount", title: "金额", width: 150, align: "right", render: renderAmountCell },
]);

function statusValue(countKey: keyof OrderStatusCounts): string {
  const counts = statusCounts.value;
  return counts ? formatInteger(counts[countKey]) : "—";
}

function statusCardNote(card: (typeof statusCards)[number]): string {
  const counts = statusCounts.value;
  if (!counts) return "—";
  if (card.noteKey === "share") {
    return counts.all > 0 ? `占全部 ${Math.round((counts[card.countKey] / counts.all) * 100)}%` : "—";
  }
  const label = card.noteKey === "anomaly" ? "数据异常" : "发货后取消";
  return `${label} ${formatInteger(counts[card.noteKey])} 单`;
}

function updateExpandedRowKeys(keys: Array<string | number>): void {
  expandedRowKeys.value = keys;
}

watch(() => route.fullPath, () => {
  if (!routeReady) return;
  const next = applyRouteQuery(route.query, 0);
  void loadOrders(next);
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
    void loadOrders(next);
  }
});

onBeforeUnmount(() => {
  requestId += 1;
});
</script>

<template>
  <section class="orders-view">
    <form class="orders-toolbar" @submit.prevent="submitSearch">
      <div class="orders-filter-row">
        <SearchField
          v-model:value="searchDraft"
          type="text"
          class="orders-search"
          aria-label="搜索订单"
          placeholder="搜索订单号、SKU、货号或商品名称…"
          @keydown.enter.prevent="submitSearch"
        />
        <NSelect
          :value="filters.channel"
          :options="channelOptions"
          class="orders-channel-select"
          aria-label="履约渠道"
          @update:value="handleChannelChange"
        />
        <div class="orders-date-control">
          <span>统计日期</span>
          <NDatePicker
            :formatted-value="dateRange"
            type="daterange"
            value-format="yyyy-MM-dd"
            separator="至"
            :clearable="false"
            class="orders-date-picker"
            aria-label="订单日期范围"
            @update:formatted-value="handleDateRangeChange"
          />
          <DatePresetPills class="orders-date-presets" aria-label="日期快捷范围" :options="datePresets" :active-key="activePreset" @select="selectPreset" />
        </div>
        <NButton type="primary" attr-type="submit" :loading="loading" class="orders-search-button">
          <template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>
          查询
        </NButton>
      </div>
    </form>

    <div v-if="loading && !statusCounts" class="orders-kpi-grid" aria-hidden="true">
      <NCard v-for="i in 5" :key="i" :bordered="false" class="orders-kpi-card">
        <NSkeleton text width="55%" />
        <NSkeleton text width="72%" class="orders-kpi-skeleton-value" />
        <NSkeleton text width="42%" />
      </NCard>
    </div>
    <div v-else-if="statusCounts" class="orders-kpi-grid" role="tablist" aria-label="订单状态筛选">
      <NCard
        v-for="card in statusCards"
        :key="card.key || 'all'"
        :bordered="false"
        class="orders-kpi-card"
        :class="[`tone-${card.tone}`, { 'is-selected': filters.status === card.key }]"
        role="tab"
        tabindex="0"
        :aria-selected="filters.status === card.key"
        @click="handleStatusChange(card.key)"
        @keydown.enter.prevent="handleStatusChange(card.key)"
        @keydown.space.prevent="handleStatusChange(card.key)"
      >
        <div class="orders-kpi-head">
          <span>{{ card.label }}</span>
          <span class="orders-icon-badge tone-badge"><morph-icon :icon="card.icon" size="18" stroke-width="1.8" /></span>
        </div>
        <strong class="orders-kpi-value tone-value">{{ statusValue(card.countKey) }}</strong>
        <small>{{ statusCardNote(card) }}</small>
      </NCard>
    </div>

    <NAlert v-if="error" type="error" class="orders-error" :title="error">
      <div class="orders-error-content">
        <span>订单列表未更新，请重试。</span>
        <NButton size="small" @click="retry">重试</NButton>
      </div>
    </NAlert>

    <div class="orders-table-meta">
      <span>共 {{ formatNumber(total, 0) }} 个订单</span>
      <span v-if="loading" class="orders-loading-label">正在加载…</span>
    </div>

    <NDataTable
      class="orders-table"
      :columns="columns"
      :data="orders"
      :loading="loading"
      :pagination="false"
      :remote="true"
      :scroll-x="928"
      table-layout="fixed"
      :row-key="orderKey"
      :expanded-row-keys="expandedRowKeys"
      :render-expand-icon="renderExpandIcon"
      @update:expanded-row-keys="updateExpandedRowKeys"
    >
      <template #empty>
        <EmptyState :title="error ? '订单加载失败' : '当前筛选范围内没有找到符合条件的订单'" icon="orders" />
      </template>
    </NDataTable>

    <div class="orders-pager">
      <span>第 {{ filters.page }} / {{ pageCount }} 页，共 {{ formatNumber(total, 0) }} 个订单</span>
      <NPagination
        :page="filters.page"
        :page-count="pageCount"
        :page-size="PAGE_SIZE"
        :disabled="loading"
        :page-slot="7"
        @update:page="changePage"
      />
    </div>
  </section>
</template>
