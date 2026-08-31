<script setup lang="ts">
import SearchField from "../../shared/components/SearchField.vue";
import EmptyState from "../../shared/components/EmptyState.vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import "../../styles/analytics.css";
import "./product-costs.css";
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, type VNodeChild } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NInput,
  NInputNumber,
  NModal,
  NPagination,
  NSelect,
  NSpin,
  NTag,
  useMessage,
} from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { getErrorMessage } from "../../shared/api/client";
import { formatBeijingDateTime, formatMoney, formatNumber } from "../../shared/utils/format";
import { listProductCostHistory, listProductCosts, saveProductCost } from "./api";
import type {
  ForecastCurrency,
  ProductCostHistoryResponse,
  ProductCostRow,
  ProductCostsResponse,
  ProductForecastCost,
  ProductForecastCostHistory,
  SaveProductForecastCostPayload,
} from "./types";

const PAGE_SIZE = 50;
const currencyOptions = [
  { label: "USD · 美元", value: "USD" },
  { label: "CNY · 人民币", value: "CNY" },
];

type CostForm = Omit<SaveProductForecastCostPayload, "sku" | "offer_id" | "purchase_cost"> & { purchase_cost: number | null };

const message = useMessage();
const response = ref<ProductCostsResponse | null>(null);
const loading = ref(false);
const error = ref("");
const searchDraft = ref("");
const search = ref("");
const page = ref(1);
const editingRow = ref<ProductCostRow | null>(null);
const editorVisible = ref(false);
const saving = ref(false);
const form = reactive<CostForm>(emptyForm());
const historyRow = ref<ProductCostRow | null>(null);
const historyVisible = ref(false);
const historyRows = ref<ProductForecastCostHistory[]>([]);
const historyLoading = ref(false);
const historyError = ref("");
let requestId = 0;
let historyRequestId = 0;

const items = computed(() => response.value?.items ?? []);
const total = computed(() => response.value?.total ?? 0);
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)));

function emptyForm(): CostForm {
  return {
    purchase_cost: null,
    purchase_currency: "USD",
    weight_grams: null,
    length_cm: null,
    width_cm: null,
    height_cm: null,
    packing_cost_cny: null,
    other_cost_cny: null,
    note: "",
    change_note: "",
  };
}

function formatOptional(value: number | null | undefined, digits = 1, suffix = ""): string {
  return value == null ? "—" : `${formatNumber(value, digits)}${suffix}`;
}

function formatSize(cost: Pick<ProductForecastCost, "length_cm" | "width_cm" | "height_cm"> | null): string {
  if (!cost || [cost.length_cm, cost.width_cm, cost.height_cm].every((value) => value == null)) return "—";
  return [cost.length_cm, cost.width_cm, cost.height_cm]
    .map((value) => value == null ? "—" : formatNumber(value, 1))
    .join(" × ") + " cm";
}

function productCell(row: ProductCostRow): VNodeChild {
  return h("div", { class: "product-costs-product-cell" }, [
    h("strong", { class: row.conflict ? "product-costs-conflict" : undefined, title: row.display_name }, row.display_name),
    h("small", row.product_identity ? `canonical · ${row.product_identity}` : row.conflict_message || "canonical identity 未确定"),
  ]);
}

function identifierCell(values: string[], label: string): VNodeChild {
  return h("div", { class: "product-costs-id-cell" }, [
    h("strong", values.join("、") || "—"),
    h("small", label),
  ]);
}

function numberCell(value: number | null | undefined, suffix = ""): VNodeChild {
  return h("div", { class: "product-costs-number-cell" }, [
    h("strong", formatOptional(value, 2, suffix)),
  ]);
}

function textCell(value: string | null | undefined): VNodeChild {
  return h("div", { class: "product-costs-number-cell" }, [h("strong", value || "—")]);
}

function purchaseCostCell(row: ProductCostRow): VNodeChild {
  if (!row.forecast_cost) return h("span", { class: "product-costs-unconfigured" }, "未配置");
  return h("div", { class: "product-costs-number-cell" }, [
    h("strong", formatMoney(row.forecast_cost.purchase_cost, row.forecast_cost.purchase_currency)),
  ]);
}

function actionCell(row: ProductCostRow): VNodeChild {
  if (row.conflict) {
    return h("div", { class: "product-costs-actions-cell" }, [
      h(NTag, { size: "small", bordered: false, class: "product-costs-conflict" }, { default: () => "规则冲突" }),
    ]);
  }
  return h("div", { class: "product-costs-actions-cell" }, [
    h("div", { class: "product-costs-table-actions" }, [
      h(NButton, {
        size: "small", text: true, type: "primary", onClick: () => openEditor(row),
      }, { default: () => [h(MorphIcon, { icon: "edit", size: "13", strokeWidth: "1.8" }), "编辑"] }),
      h(NButton, {
        size: "small", text: true, onClick: () => openHistory(row),
      }, { default: () => [h(MorphIcon, { icon: "clock", size: "13", strokeWidth: "1.8" }), "历史记录"] }),
    ]),
  ]);
}

const columns: DataTableColumns<ProductCostRow> = [
  { key: "display_name", title: "商品名称", width: 230, fixed: "left", render: productCell },
  { key: "offer_ids", title: "货号 / offer_id", width: 220, render: (row) => identifierCell(row.offer_ids, "货号 / offer_id") },
  { key: "ozon_skus", title: "Ozon SKU", width: 180, render: (row) => identifierCell(row.ozon_skus, "Ozon 数字 SKU") },
  { key: "purchase_cost", title: "当前采购成本", width: 150, align: "right", render: purchaseCostCell },
  { key: "purchase_currency", title: "币种", width: 90, align: "right", render: (row) => textCell(row.forecast_cost?.purchase_currency) },
  { key: "weight_grams", title: "重量", width: 110, align: "right", render: (row) => numberCell(row.forecast_cost?.weight_grams, " g") },
  { key: "packing_cost_cny", title: "包装成本", width: 130, align: "right", render: (row) => numberCell(row.forecast_cost?.packing_cost_cny, " CNY") },
  { key: "updated_at", title: "最后更新", width: 160, align: "right", render: (row) => h("span", { class: "product-costs-time" }, formatBeijingDateTime(row.updated_at)) },
  { key: "actions", title: "操作", width: 180, align: "right", render: actionCell },
];

const historyColumns: DataTableColumns<ProductForecastCostHistory> = [
  { key: "recorded_at", title: "记录时间", width: 160, render: (row) => h("span", { class: "product-costs-time" }, formatBeijingDateTime(row.recorded_at)) },
  { key: "purchase_cost", title: "采购成本", width: 140, align: "right", render: (row) => numberCell(row.purchase_cost) },
  { key: "purchase_currency", title: "币种", width: 90, align: "right", render: (row) => textCell(row.purchase_currency) },
  { key: "weight_grams", title: "重量", width: 100, align: "right", render: (row) => numberCell(row.weight_grams, " g") },
  { key: "size", title: "尺寸", width: 150, align: "right", render: (row) => h("span", { class: "product-costs-history-size" }, formatSize(row)) },
  { key: "packing_cost_cny", title: "包装成本", width: 130, align: "right", render: (row) => numberCell(row.packing_cost_cny, " CNY") },
  { key: "other_cost_cny", title: "其他成本", width: 130, align: "right", render: (row) => numberCell(row.other_cost_cny, " CNY") },
  { key: "note", title: "备注", width: 180, render: (row) => h("span", { class: "product-costs-history-note-cell" }, row.note || "—") },
  { key: "change_note", title: "变更备注", width: 180, render: (row) => h("span", { class: "product-costs-history-note-cell product-costs-history-change" }, row.change_note || "—") },
];

async function loadCosts(): Promise<void> {
  const currentRequest = ++requestId;
  loading.value = true;
  error.value = "";
  try {
    const result = await listProductCosts({ search: search.value, page: page.value, size: PAGE_SIZE });
    if (currentRequest === requestId) response.value = result;
  } catch (cause) {
    if (currentRequest === requestId) error.value = getErrorMessage(cause);
  } finally {
    if (currentRequest === requestId) loading.value = false;
  }
}

function submitSearch(): void {
  search.value = searchDraft.value.trim();
  page.value = 1;
  void loadCosts();
}

function clearSearch(): void {
  searchDraft.value = "";
  search.value = "";
  page.value = 1;
  void loadCosts();
}

function changePage(value: number): void {
  if (value === page.value) return;
  page.value = value;
  void loadCosts();
}

function openEditor(row: ProductCostRow): void {
  if (row.conflict) return;
  editingRow.value = row;
  const cost = row.forecast_cost;
  Object.assign(form, {
    purchase_cost: cost?.purchase_cost ?? null,
    purchase_currency: cost?.purchase_currency ?? "USD",
    weight_grams: cost?.weight_grams ?? null,
    length_cm: cost?.length_cm ?? null,
    width_cm: cost?.width_cm ?? null,
    height_cm: cost?.height_cm ?? null,
    packing_cost_cny: cost?.packing_cost_cny ?? null,
    other_cost_cny: cost?.other_cost_cny ?? null,
    note: cost?.note ?? "",
    change_note: "",
  });
  editorVisible.value = true;
}

function validNumber(value: number | null): boolean {
  return value === null || (Number.isFinite(value) && value >= 0);
}

async function submitEditor(): Promise<void> {
  const row = editingRow.value;
  if (!row || saving.value) return;
  if (form.purchase_cost === null || !Number.isFinite(form.purchase_cost) || form.purchase_cost < 0) {
    message.error("请输入有效的非负采购成本");
    return;
  }
  if (!validNumber(form.weight_grams) || !validNumber(form.length_cm) || !validNumber(form.width_cm)
      || !validNumber(form.height_cm) || !validNumber(form.packing_cost_cny) || !validNumber(form.other_cost_cny)) {
    message.error("重量、尺寸和其他成本必须为非负数字");
    return;
  }
  const payload: SaveProductForecastCostPayload = {
    sku: row.sku,
    offer_id: row.offer_id,
    purchase_cost: form.purchase_cost,
    purchase_currency: form.purchase_currency as ForecastCurrency,
    weight_grams: form.weight_grams,
    length_cm: form.length_cm,
    width_cm: form.width_cm,
    height_cm: form.height_cm,
    packing_cost_cny: form.packing_cost_cny,
    other_cost_cny: form.other_cost_cny,
    note: form.note.trim(),
    change_note: form.change_note.trim(),
  };
  saving.value = true;
  try {
    await saveProductCost(payload);
    message.success("预测成本已保存");
    editorVisible.value = false;
    await loadCosts();
  } catch (cause) {
    message.error(getErrorMessage(cause));
  } finally {
    saving.value = false;
  }
}

function openHistory(row: ProductCostRow): void {
  if (row.conflict) return;
  historyRow.value = row;
  historyVisible.value = true;
  historyRows.value = [];
  historyError.value = "";
  void loadHistory(row);
}

async function loadHistory(row: ProductCostRow): Promise<void> {
  const currentRequest = ++historyRequestId;
  historyLoading.value = true;
  historyError.value = "";
  try {
    const result: ProductCostHistoryResponse = await listProductCostHistory(row.sku, row.offer_id);
    if (currentRequest === historyRequestId) historyRows.value = result.items;
  } catch (cause) {
    if (currentRequest === historyRequestId) historyError.value = getErrorMessage(cause);
  } finally {
    if (currentRequest === historyRequestId) historyLoading.value = false;
  }
}

onMounted(() => { void loadCosts(); });
onBeforeUnmount(() => {
  requestId += 1;
  historyRequestId += 1;
});
</script>

<template>
  <section class="product-costs-view">
    <NAlert type="info" class="product-costs-notice">
      <template #icon><morph-icon icon="coins" size="16" stroke-width="1.8" /></template>
      这里保存的是用于未来利润预测的预测成本参数。历史记录仅表示预测参数的修改记录，不作为已产生订单的实际成本依据。
    </NAlert>

    <NAlert v-if="error" type="error" class="analytics-error" :title="error">
      <div class="analytics-error-content"><span>SKU 成本列表未更新，请重试。</span><NButton size="small" @click="loadCosts">重试</NButton></div>
    </NAlert>

    <NCard :bordered="false" class="analytics-table-card">
      <template #header>
        <div class="analytics-panel-heading">
          <div>
            <h2><morph-icon icon="coins" size="18" stroke-width="1.8" />SKU 成本</h2>
            <span>按现有订单商品与商品匹配规则维护 canonical product 的当前预测参数</span>
          </div>
          <NTag size="small" round :bordered="false" class="product-costs-forecast-tag">Forecast only</NTag>
        </div>
      </template>

      <form class="product-costs-search" role="search" @submit.prevent="submitSearch">
        <SearchField v-model:value="searchDraft" placeholder="搜索 Ozon SKU、货号或商品名称…" aria-label="搜索 SKU 成本商品" @keydown.enter.prevent="submitSearch" />
        <NButton type="primary" attr-type="submit" :loading="loading">
          <template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>
          查询
        </NButton>
        <NButton attr-type="button" @click="clearSearch">清除</NButton>
      </form>

      <div class="analytics-table-meta"><span>共 {{ total }} 个商品</span><span v-if="loading" class="analytics-loading-label">正在加载…</span></div>
      <NDataTable
        class="analytics-table product-costs-table"
        :columns="columns"
        :data="items"
        :loading="loading"
        :pagination="false"
        :remote="true"
        :scroll-x="1370"
        table-layout="fixed"
        :row-key="(row: ProductCostRow) => row.product_identity ?? `${row.sku}:${row.offer_id}`"
      >
        <template #empty>
          <EmptyState icon="coins" :title="error ? 'SKU 成本加载失败' : '暂无可维护商品'" :hint="error ? '请点击上方重试。' : '商品会随着现有订单数据自动出现，无需单独维护商品目录。'" />
        </template>
      </NDataTable>

      <div class="analytics-pager">
        <span>第 {{ page }} / {{ pageCount }} 页，共 {{ total }} 个商品</span>
        <NPagination :page="page" :page-count="pageCount" :page-size="PAGE_SIZE" :disabled="loading" :page-slot="7" @update:page="changePage" />
      </div>
    </NCard>

    <NModal v-model:show="editorVisible" preset="card" :style="{ width: 'min(640px, 92vw)' }" :mask-closable="!saving" title="编辑 SKU 预测成本">
      <p class="product-costs-history-note">canonical identity：{{ editingRow?.product_identity }} · Ozon SKU：{{ editingRow?.ozon_skus.join("、") }} · 货号：{{ editingRow?.offer_ids.join("、") }}</p>
      <form class="product-costs-form" @submit.prevent="submitEditor">
        <div class="product-costs-form-grid">
          <label class="product-costs-field"><span>当前采购成本</span><NInputNumber v-model:value="form.purchase_cost" :min="0" :step="0.01" :show-button="false" clearable placeholder="输入采购参考成本" /></label>
          <label class="product-costs-field"><span>采购币种</span><NSelect v-model:value="form.purchase_currency" :options="currencyOptions" /></label>
          <label class="product-costs-field"><span>重量 (g)</span><NInputNumber v-model:value="form.weight_grams" :min="0" :step="1" :show-button="false" clearable placeholder="克" /></label>
          <label class="product-costs-field"><span>长度 (cm)</span><NInputNumber v-model:value="form.length_cm" :min="0" :step="0.1" :show-button="false" clearable placeholder="厘米" /></label>
          <label class="product-costs-field"><span>宽度 (cm)</span><NInputNumber v-model:value="form.width_cm" :min="0" :step="0.1" :show-button="false" clearable placeholder="厘米" /></label>
          <label class="product-costs-field"><span>高度 (cm)</span><NInputNumber v-model:value="form.height_cm" :min="0" :step="0.1" :show-button="false" clearable placeholder="厘米" /></label>
          <label class="product-costs-field"><span>包装成本 (CNY)</span><NInputNumber v-model:value="form.packing_cost_cny" :min="0" :step="0.01" :show-button="false" clearable placeholder="人民币" /></label>
          <label class="product-costs-field"><span>其他成本 (CNY)</span><NInputNumber v-model:value="form.other_cost_cny" :min="0" :step="0.01" :show-button="false" clearable placeholder="人民币" /></label>
          <label class="product-costs-field product-costs-field--wide"><span>当前备注</span><NInput v-model:value="form.note" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" maxlength="500" show-count placeholder="当前预测成本备注…" /></label>
          <label class="product-costs-field product-costs-field--wide"><span>本次变更备注</span><NInput v-model:value="form.change_note" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" maxlength="500" placeholder="如：供应商涨价 / 修正重量 / 包材调整…" /></label>
        </div>
        <div class="product-costs-form-actions">
          <NButton type="primary" attr-type="submit" :loading="saving"><template #icon><morph-icon icon="check" size="14" stroke-width="2" /></template>保存</NButton>
          <NButton attr-type="button" :disabled="saving" @click="editorVisible = false">取消</NButton>
        </div>
      </form>
    </NModal>

    <NModal v-model:show="historyVisible" preset="card" :style="{ width: 'min(1180px, 96vw)' }" title="预测成本历史记录">
      <p class="product-costs-history-note">历史记录仅表示预测参数的修改记录，不作为已产生订单的实际成本依据。历史版本只读，按最新记录在前展示。</p>
      <div class="product-costs-history-meta">
        <span>canonical identity：{{ historyRow?.product_identity }}</span>
        <span v-if="historyLoading"><NSpin size="small" /> 加载中…</span>
      </div>
      <NAlert v-if="historyError" type="error" class="analytics-error" :title="historyError">历史记录加载失败，请关闭后重试。</NAlert>
      <NDataTable
        class="analytics-table product-costs-history-table"
        :columns="historyColumns"
        :data="historyRows"
        :loading="historyLoading"
        :pagination="false"
        :scroll-x="1260"
        table-layout="fixed"
      >
        <template #empty><EmptyState icon="clock" :title="historyError ? '历史记录加载失败' : '暂无历史记录'" hint="首次保存预测成本后会生成第一条完整快照。" /></template>
      </NDataTable>
    </NModal>
  </section>
</template>
