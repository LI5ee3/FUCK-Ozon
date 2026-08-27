<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch, type VNodeChild } from "vue";
import type { LocationQuery, LocationQueryValue } from "vue-router";
import { useRoute, useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NDataTable,
  NDatePicker,
  NEmpty,
  NInput,
  NPagination,
  NSelect,
  NTag,
  useMessage,
} from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { getErrorMessage } from "../api/client";
import { listOrders } from "../api/orders";
import { useShop } from "../composables/useShop";
import type {
  Channel,
  Order,
  OrderStatusCounts,
  OrderStatusFilter,
  ShopSelection,
} from "../types/api";
import { formatBeijingDateTime, formatInteger, formatMoney, formatNumber } from "../utils/format";
import OrderDetailPanel from "../components/orders/OrderDetailPanel.vue";

type DateRange = [string, string];
type DatePreset = "today" | "3days" | "7days" | "3months" | "all";
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
const today = beijingToday();
const defaultRange: DateRange = [subtractMonths(today, 3), today];
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
const statusFilters: ReadonlyArray<{ key: OrderStatusFilter; label: string; icon: string; countKey: keyof OrderStatusCounts }> = [
  { key: "", label: "全部订单", icon: "layers", countKey: "all" },
  { key: "pending", label: "待备货", icon: "box", countKey: "pending" },
  { key: "shipping", label: "运输中", icon: "truck", countKey: "shipping" },
  { key: "delivered", label: "已签收", icon: "checkCircle", countKey: "delivered" },
  { key: "cancelled", label: "已取消", icon: "alertTriangle", countKey: "cancelled" },
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
    const [from, to] = presetRange(preset.key);
    if (filters.from === from && filters.to === to) return preset.key;
  }
  return "";
});
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)));

function beijingToday(): string {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date()).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function dateParts(value: string): [number, number, number] {
  const [year, month, day] = value.split("-").map(Number);
  return [year, month, day];
}

function dateText(year: number, month: number, day: number): string {
  return `${year.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}-${day.toString().padStart(2, "0")}`;
}

function shiftDays(value: string, days: number): string {
  const [year, month, day] = dateParts(value);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  return dateText(shifted.getUTCFullYear(), shifted.getUTCMonth() + 1, shifted.getUTCDate());
}

function subtractMonths(value: string, months: number): string {
  const [year, month, day] = dateParts(value);
  const target = new Date(Date.UTC(year, month - 1 - months, 1));
  const lastDay = new Date(Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)).getUTCDate();
  return dateText(target.getUTCFullYear(), target.getUTCMonth() + 1, Math.min(day, lastDay));
}

function firstQueryValue(value: LocationQueryValue | LocationQueryValue[] | undefined): string {
  return Array.isArray(value) ? String(value[0] ?? "") : value ?? "";
}

function queryValue(query: LocationQuery, key: string): string {
  return firstQueryValue(query[key]);
}

function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = dateParts(value);
  if (year < 1) return false;
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}

function positiveInteger(value: string, fallback: number): number {
  if (!/^\d+$/.test(value)) return fallback;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function isShopSelection(value: string): value is "0" | "1" | "2" {
  return value === "0" || value === "1" || value === "2";
}

function isChannel(value: string): value is Channel {
  return value === "FBP" || value === "realFBS" || value === "WHD";
}

function isStatusFilter(value: string): value is Exclude<OrderStatusFilter, ""> {
  return value === "pending" || value === "shipping" || value === "delivered" || value === "cancelled";
}

function parseDateRange(from: string, to: string): DateRange {
  return validDate(from) && validDate(to) && from <= to ? [from, to] : [...defaultRange];
}

function parseFilters(query: LocationQuery, fallbackShop: ShopSelection): OrderFilters {
  const shop = queryValue(query, "shop_id");
  const status = queryValue(query, "status");
  const channel = queryValue(query, "channel");
  const [from, to] = parseDateRange(queryValue(query, "from"), queryValue(query, "to"));
  return {
    shopId: isShopSelection(shop) ? Number(shop) as ShopSelection : fallbackShop,
    channel: isChannel(channel) ? channel : "",
    status: isStatusFilter(status) ? status : "",
    search: queryValue(query, "q"),
    page: positiveInteger(queryValue(query, "page"), 1),
    from,
    to,
  };
}

function presetRange(preset: DatePreset): DateRange {
  if (preset === "today") return [today, today];
  if (preset === "3days") return [shiftDays(today, -2), today];
  if (preset === "7days") return [shiftDays(today, -6), today];
  if (preset === "all") return ["2020-01-01", today];
  return [...defaultRange];
}

function queryFor(filtersValue: OrderFilters): Record<string, string> {
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

function queryMatches(query: LocationQuery, filtersValue: OrderFilters): boolean {
  const expected = queryFor(filtersValue);
  const keys = new Set([...Object.keys(query), ...Object.keys(expected)]);
  return [...keys].every((key) => queryValue(query, key) === (expected[key] ?? ""));
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
  const navigation = replace ? router.replace({ query: queryFor(next) }) : router.push({ query: queryFor(next) });
  void navigation;
}

function updateFilters(overrides: Partial<OrderFilters>, replace = false): void {
  updateRoute({ ...filters, search: searchDraft.value, ...overrides }, replace);
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
      await router.replace({ query: queryFor({ ...queryFilters, page: responsePageCount }) });
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
  void loadOrders({ ...filters, search: searchDraft.value });
}

function submitSearch(): void {
  updateFilters({ page: 1, search: searchDraft.value });
}

function handleChannelChange(value: string | number | null): void {
  updateFilters({ channel: typeof value === "string" && isChannel(value) ? value : "", page: 1 });
}

function handleStatusChange(status: OrderStatusFilter): void {
  updateFilters({ status, page: 1 });
}

function handleDateRangeChange(value: string | DateRange | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  const [from, to] = parseDateRange(value[0], value[1]);
  if (from !== value[0] || to !== value[1]) return;
  updateFilters({ from, to, page: 1 });
}

function selectPreset(preset: DatePreset): void {
  const [from, to] = presetRange(preset);
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

function statusIcon(order: Order): string {
  if (order.status_raw === "已取消" || order.data_anomaly) return "alertTriangle";
  if (order.status_raw === "已签收") return "checkCircle";
  if (/运输|配送|发货|待取件/.test(order.status_raw)) return "truck";
  return "box";
}

function channelClass(channel: Channel): string {
  return channel === "FBP" ? "orders-channel-tag--fbp" : channel === "realFBS" ? "orders-channel-tag--fbs" : "orders-channel-tag--whd";
}

function renderTag(label: string, type: TagType, className = "", icon = ""): VNodeChild {
  return h(NTag, { bordered: false, round: true, size: "small", type, class: className }, {
    default: () => icon
      ? h("span", { class: "orders-tag-content" }, [h("morph-icon", { icon, size: "13", "stroke-width": "2" }), label])
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
      renderTag(order.channel, "default", `orders-channel-tag ${channelClass(order.channel)}`),
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
          h("morph-icon", { icon: "alertTriangle", size: "12", "stroke-width": "2" }),
          order.cancel_reason_raw,
        ])
      : null,
  ]);
}

function renderStatusCell(order: Order): VNodeChild {
  return h("div", { class: "orders-status-cell" }, [
    renderTag(order.status_raw || "未知状态", tagType(order), "orders-status-tag", statusIcon(order)),
    h("span", { class: "orders-time-stamp" }, [
      h("morph-icon", { icon: "clock", size: "12", "stroke-width": "1.8" }),
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

const columns = computed<DataTableColumns<Order>>(() => [
  {
    type: "expand",
    width: 48,
    renderExpand: (order) => h(OrderDetailPanel, { order, copyValue }),
  },
  { key: "order", title: "订单", minWidth: 210, render: renderOrderCell },
  { key: "product", title: "商品信息", minWidth: 330, render: renderProductCell },
  { key: "status", title: "状态与时间", width: 190, render: renderStatusCell },
  { key: "amount", title: "金额", width: 150, align: "right", render: renderAmountCell },
]);

function statusCount(countKey: keyof OrderStatusCounts): string | number {
  return statusCounts.value?.[countKey] ?? "—";
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
  if (!queryMatches(route.query, next)) {
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
        <NInput
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
          <div class="orders-date-presets" aria-label="日期快捷范围">
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
        <NButton type="primary" attr-type="submit" :loading="loading" class="orders-search-button">
          <template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>
          查询
        </NButton>
      </div>

      <div class="orders-status-filters" role="tablist" aria-label="订单状态快速筛选">
        <NButton
          v-for="item in statusFilters"
          :key="item.key || 'all'"
          size="small"
          :type="filters.status === item.key ? 'primary' : 'default'"
          :secondary="filters.status !== item.key"
          attr-type="button"
          role="tab"
          :aria-selected="filters.status === item.key"
          @click="handleStatusChange(item.key)"
        >
          <template #icon><morph-icon :icon="item.icon" size="13" stroke-width="2" /></template>
          {{ item.label }}
          <NTag size="tiny" round :bordered="false" :type="filters.status === item.key ? 'default' : 'info'">
            {{ statusCount(item.countKey) }}
          </NTag>
        </NButton>
      </div>
    </form>

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
      :scroll-x="980"
      :row-key="orderKey"
      :expanded-row-keys="expandedRowKeys"
      @update:expanded-row-keys="updateExpandedRowKeys"
    >
      <template #empty>
        <NEmpty :description="error ? '订单加载失败' : '当前筛选范围内没有找到符合条件的订单'" />
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
