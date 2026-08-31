<script setup lang="ts">
import "../../styles/analytics.css";
import "./profit.css";
import { computed, h, ref, watch, type VNodeChild } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import { NAlert, NButton, NCard, NInputNumber, NSelect, NTag } from "naive-ui";
import { useShop } from "../../shared/composables/useShop";
import { formatBeijingDateTime, formatNumber } from "../../shared/utils/format";
import { useRouter } from "vue-router";
import type { ProductCostRow, ProductForecastCost } from "../product-costs/types";
import {
  calculateProfit,
  PROFIT_COST_KEYS,
  type ProfitCostKey,
  type ProfitCostStatus,
  type ProfitFulfillmentMode,
  type ProfitPath,
  type ProfitPurchaseCurrency,
  type ProfitRealFbsChannel,
  type ProfitShopId,
} from "./calculator";
import { useProfitProduct } from "./useProfitProduct";

const { shops } = useShop();
const router = useRouter();
const { products, loading: productSearchLoading, error: productSearchError, search: searchProducts, clear: clearProductSearch } = useProfitProduct();
const profitShopId = ref<ProfitShopId>(1);
const fulfillmentMode = ref<ProfitFulfillmentMode>("FBP");
const realFbsChannel = ref<ProfitRealFbsChannel>("hongkong");
const priceOriginal = ref<number | null>(null);
const purchaseCost = ref<number | null>(null);
const purchaseCurrency = ref<ProfitPurchaseCurrency>("USD");
const weightGrams = ref<number | null>(null);
const packingCostCny = ref<number | null>(null);
const otherCostCny = ref<number | null>(null);
const usdCnyRate = ref<number | null>(7.2);
const selectedProduct = ref<ProductCostRow | null>(null);
const manualOverride = ref(false);

type ForecastParameters = {
  purchaseCost: number | null;
  purchaseCurrency: ProfitPurchaseCurrency;
  weightGrams: number | null;
  packingCostCny: number | null;
  otherCostCny: number | null;
};

type ProductOption = { label: string; value: string; row: ProductCostRow };

const purchaseCurrencyOptions = [
  { label: "USD · 美元", value: "USD" },
  { label: "CNY · 人民币", value: "CNY" },
];

function productKey(row: ProductCostRow): string {
  return row.product_identity || `conflict:${row.sku}:${row.offer_id}`;
}

function compactIdentifiers(values: string[]): string {
  if (!values.length) return "—";
  return values.length === 1 ? values[0] : `${values[0]} +${values.length - 1}`;
}

function renderProductLabel(option: { label?: unknown; row?: unknown }): VNodeChild {
  if (!option.row || typeof option.row !== "object") return String(option.label ?? "");
  const row = option.row as ProductCostRow;
  const offers = Array.isArray(row.offer_ids) ? row.offer_ids : [];
  const skus = Array.isArray(row.ozon_skus) ? row.ozon_skus : [];
  const suffix = row.conflict ? " · 规则冲突" : row.configured ? "" : " · 未配置成本";
  return h("div", { class: "profit-product-option" }, [
    h("strong", row.display_name),
    h("small", `${compactIdentifiers(offers)} · ${compactIdentifiers(skus)}${suffix}`),
  ]);
}

function validOptionalNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value) && value >= 0);
}

function isUsableForecastCost(value: unknown): value is ProductForecastCost {
  if (!value || typeof value !== "object") return false;
  const cost = value as Record<string, unknown>;
  return typeof cost.product_identity === "string"
    && typeof cost.purchase_cost === "number" && Number.isFinite(cost.purchase_cost) && cost.purchase_cost >= 0
    && (cost.purchase_currency === "USD" || cost.purchase_currency === "CNY")
    && ["weight_grams", "length_cm", "width_cm", "height_cm", "packing_cost_cny", "other_cost_cny"]
      .every((key) => validOptionalNumber(cost[key]))
    && typeof cost.note === "string" && typeof cost.updated_at === "string";
}

const selectedProductValue = computed(() => selectedProduct.value ? productKey(selectedProduct.value) : null);
const productOptions = computed<ProductOption[]>(() => {
  const rows = [...products.value];
  if (selectedProduct.value && !rows.some((row) => productKey(row) === productKey(selectedProduct.value!))) {
    rows.unshift(selectedProduct.value);
  }
  return rows.map((row) => ({ label: row.display_name, value: productKey(row), row }));
});
const selectedForecastCost = computed<ProductForecastCost | null>(() => {
  const row = selectedProduct.value;
  return row?.configured && isUsableForecastCost(row.forecast_cost) ? row.forecast_cost : null;
});
const forecastCostError = computed(() => {
  const row = selectedProduct.value;
  return row && !row.conflict && row.configured && !selectedForecastCost.value
    ? "SKU 成本数据异常，请先检查 SKU 成本页面；当前测算已回退为手工输入。"
    : "";
});

const currentForecastParameters = computed<ForecastParameters>(() => ({
  purchaseCost: purchaseCost.value,
  purchaseCurrency: purchaseCurrency.value,
  weightGrams: weightGrams.value,
  packingCostCny: packingCostCny.value,
  otherCostCny: otherCostCny.value,
}));
const automaticParameters = ref<ForecastParameters | null>(null);

function sameForecastParameters(left: ForecastParameters, right: ForecastParameters): boolean {
  return left.purchaseCost === right.purchaseCost
    && left.purchaseCurrency === right.purchaseCurrency
    && left.weightGrams === right.weightGrams
    && left.packingCostCny === right.packingCostCny
    && left.otherCostCny === right.otherCostCny;
}

watch(currentForecastParameters, (value) => {
  if (automaticParameters.value) manualOverride.value = !sameForecastParameters(value, automaticParameters.value);
}, { deep: true });

function resetForecastParameters(): void {
  automaticParameters.value = null;
  manualOverride.value = false;
  purchaseCost.value = null;
  purchaseCurrency.value = "USD";
  weightGrams.value = null;
  packingCostCny.value = null;
  otherCostCny.value = null;
}

function selectProduct(value: string | number | null): void {
  if (value === null || value === "") {
    clearProduct();
    return;
  }
  const option = productOptions.value.find((item) => item.value === String(value));
  if (!option) return;
  selectedProduct.value = option.row;
  resetForecastParameters();
  if (option.row.conflict || !option.row.configured || !isUsableForecastCost(option.row.forecast_cost)) return;
  const cost = option.row.forecast_cost;
  const parameters: ForecastParameters = {
    purchaseCost: cost.purchase_cost,
    purchaseCurrency: cost.purchase_currency,
    weightGrams: cost.weight_grams,
    packingCostCny: cost.packing_cost_cny,
    otherCostCny: cost.other_cost_cny,
  };
  automaticParameters.value = parameters;
  purchaseCost.value = parameters.purchaseCost;
  purchaseCurrency.value = parameters.purchaseCurrency;
  weightGrams.value = parameters.weightGrams;
  packingCostCny.value = parameters.packingCostCny;
  otherCostCny.value = parameters.otherCostCny;
}

function clearProduct(): void {
  selectedProduct.value = null;
  resetForecastParameters();
  clearProductSearch();
}

function updatePurchaseCurrency(value: string | number | null): void {
  if (value === "USD" || value === "CNY") purchaseCurrency.value = value;
}

function openProductCosts(): void {
  void router.push("/product-costs");
}

function formatProductSize(cost: ProductForecastCost): string {
  const values = [cost.length_cm, cost.width_cm, cost.height_cm];
  return values.every((value) => value === null)
    ? "尺寸未配置"
    : `${values.map((value) => value === null ? "—" : formatNumber(value, 1)).join(" × ")} cm`;
}

const parameterSourceLabel = computed(() => {
  const row = selectedProduct.value;
  if (!row) return "预测参数：纯手工测算";
  if (row.conflict) return "预测参数：不可用（商品匹配规则冲突）";
  if (forecastCostError.value) return "预测参数：数据异常，已回退手工输入";
  if (selectedForecastCost.value) {
    return manualOverride.value
      ? "预测参数：手工覆盖 · 基于 SKU 成本库"
      : `预测参数：SKU 成本库 · 更新于 ${formatBeijingDateTime(selectedForecastCost.value.updated_at)}`;
  }
  return "预测参数：未配置 · 手工输入";
});

const profitCostLabels: Record<ProfitCostKey, string> = {
  purchase_cost: "采购成本",
  hunchun_shipping: "发往珲春物流费",
  cross_border_shipping: "跨境运费",
  last_mile_shipping: "末端运费",
  warehouse_fee: "仓库处理费",
  commission: "平台佣金",
  advertising: "广告费用",
  international_transport_contract_service: "国际运输组织合同的签订服务",
  bank_acquiring_fee: "银行收单手续费",
  packing: "打包成本",
  other_cost: "其他费用",
};

const profitStatusLabels: Record<ProfitCostStatus, string> = {
  implemented: "已接入",
  missing_input: "待输入",
  not_implemented: "未接入规则",
  not_applicable: "不适用",
};

const profitPathLabels: Record<ProfitPath, string> = {
  FBP: "FBP",
  realFBS_hongkong: "realFBS · 香港",
  realFBS_shenzhen: "realFBS · 深圳",
};

const shopOptions = computed(() => {
  const available = shops.value.filter((shop) => shop.id === 1 || shop.id === 2);
  return (available.length ? available : [{ id: 1, name: "店铺1" }, { id: 2, name: "店铺2" }]).map((shop) => ({
    label: `${shop.name} · ${shop.id === 2 ? "CNY" : "USD"}`,
    value: shop.id,
  }));
});

const result = computed(() => calculateProfit({
  shopId: profitShopId.value,
  priceOriginal: priceOriginal.value,
  purchaseCost: purchaseCost.value,
  purchaseCurrency: purchaseCurrency.value,
  weightGrams: weightGrams.value,
  packingCostCny: packingCostCny.value,
  otherCostCny: otherCostCny.value,
  usdCnyRate: usdCnyRate.value,
  fulfillmentMode: fulfillmentMode.value,
  realFbsChannel: realFbsChannel.value,
}));

const priceCurrency = computed(() => result.value.price_currency ?? "—");
const pricePrefix = computed(() => result.value.price_currency === "CNY" ? "¥" : "$");
const purchasePrefix = computed(() => purchaseCurrency.value === "CNY" ? "¥" : "$");
const priceUsdLabel = computed(() => result.value.price_currency === "CNY" ? "美元等值" : "美元售价");
const priceCnyLabel = computed(() => result.value.price_currency === "CNY" ? "人民币售价" : "人民币等值");
const showRealFbsChannel = computed(() => fulfillmentMode.value === "realFBS");
const configuredCostNames = computed(() => PROFIT_COST_KEYS
  .filter((key) => !["not_implemented", "not_applicable"].includes(result.value.costs[key].status))
  .map((key) => profitCostLabels[key]));
const profitNotice = computed(() => `当前已接入费用：${configuredCostNames.value.join("、") || "暂无"}；其他费用规则尚未接入。`);
const summaryNote = computed(() => result.value.profit_cny === null
  ? `请输入有效的平台售价、采购成本以及所需的 USD/CNY 测算汇率；${profitNotice.value}`
  : profitNotice.value);

type MacaronTone = "azure" | "lavender" | "mint" | "peach" | "butter";

function updateShop(value: string | number | null): void {
  if (value === 1 || value === "1") profitShopId.value = 1;
  if (value === 2 || value === "2") profitShopId.value = 2;
}

function updateFulfillment(value: string | number | null): void {
  if (value === "FBP" || value === "realFBS") fulfillmentMode.value = value;
}

function updateChannel(value: string | number | null): void {
  if (value === "hongkong" || value === "shenzhen") realFbsChannel.value = value;
}

// Macaron tone mapping (DESIGN.md §colors.tones): mint = 已接入,
// butter = 待输入, descriptive statuses stay neutral.
function statusTone(status: ProfitCostStatus): MacaronTone | "" {
  if (status === "implemented") return "mint";
  if (status === "missing_input") return "butter";
  return "";
}

function formatProfitMoney(value: number | null, currency = "CNY"): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${currency === "USD" ? "$" : "¥"}${value.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatProfitPercent(value: number | null): string {
  return value === null || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(2)}%`;
}
</script>

<template>
  <section class="profit-view">
    <NCard :bordered="false" class="analytics-table-card profit-intro-panel">
      <div class="analytics-panel-heading">
        <div>
          <h2><morph-icon icon="trendingUp" size="18" stroke-width="1.8" />利润测算</h2>
          <span>按店铺定价币种换算，当前结果统一以人民币展示</span>
        </div>
        <NTag round>第一阶段框架</NTag>
      </div>
      <NAlert type="warning" class="profit-notice" role="status">
        <template #icon><morph-icon icon="alertCircle" size="15" stroke-width="1.8" /></template>
        {{ profitNotice }}
      </NAlert>
    </NCard>

    <div class="profit-input-grid">
      <NCard :bordered="false" class="analytics-table-card profit-input-panel">
        <template #header>
          <div class="analytics-panel-heading">
            <div>
              <h2><morph-icon icon="settings" size="18" stroke-width="1.8" />基础信息</h2>
              <span>店铺币种固定；商品预测参数可自动带入，也可手工覆盖</span>
            </div>
          </div>
        </template>
        <div class="profit-fields-grid">
          <label class="profit-field profit-product-field">
            <span>商品</span>
            <NSelect
              data-testid="profit-product-select"
              :value="selectedProductValue"
              :options="productOptions"
              filterable
              remote
              clearable
              :loading="productSearchLoading"
              placeholder="搜索商品名称、Ozon SKU 或货号…"
              :render-label="renderProductLabel"
              aria-label="利润测算商品"
              @search="searchProducts"
              @update:value="selectProduct"
              @clear="clearProduct"
            />
            <small class="profit-product-source">{{ parameterSourceLabel }}</small>
          </label>
          <div v-if="selectedProduct && !selectedProduct.conflict" class="profit-product-info" role="status">
            <div>
              <strong>{{ selectedProduct.display_name }}</strong>
              <span>货号：{{ compactIdentifiers(selectedProduct.offer_ids) }} · Ozon SKU：{{ compactIdentifiers(selectedProduct.ozon_skus) }}</span>
            </div>
            <small v-if="selectedForecastCost">
              最后更新：{{ formatBeijingDateTime(selectedForecastCost.updated_at) }} · 尺寸：{{ formatProductSize(selectedForecastCost) }}<span v-if="selectedForecastCost.note"> · 备注：{{ selectedForecastCost.note }}</span>
            </small>
          </div>
          <NAlert v-if="productSearchError" type="error" class="profit-product-alert">
            商品搜索失败：{{ productSearchError }}；仍可继续手工测算。
          </NAlert>
          <NAlert v-else-if="selectedProduct?.conflict" type="error" class="profit-product-alert">
            商品匹配规则存在冲突，请先处理商品匹配规则。
          </NAlert>
          <NAlert v-else-if="forecastCostError" type="error" class="profit-product-alert">
            {{ forecastCostError }}
          </NAlert>
          <NAlert v-else-if="selectedProduct && !selectedProduct.configured" type="warning" class="profit-product-alert">
            该商品尚未配置 SKU 预测成本，可继续手工输入，或 <NButton text type="primary" @click="openProductCosts">前往 SKU 成本</NButton>。
          </NAlert>
          <label class="profit-field">
            <span>店铺</span>
            <NSelect
              :value="profitShopId"
              :options="shopOptions"
              aria-label="利润测算店铺"
              @update:value="updateShop"
            />
          </label>
          <label class="profit-field">
            <span>履约模式</span>
            <NSelect
              :value="fulfillmentMode"
              :options="[{ label: 'FBP', value: 'FBP' }, { label: 'realFBS', value: 'realFBS' }]"
              aria-label="履约模式"
              @update:value="updateFulfillment"
            />
          </label>
          <label v-if="showRealFbsChannel" class="profit-field">
            <span>realFBS 发货渠道</span>
            <NSelect
              :value="realFbsChannel"
              :options="[{ label: '香港', value: 'hongkong' }, { label: '深圳', value: 'shenzhen' }]"
              aria-label="realFBS 发货渠道"
              @update:value="updateChannel"
            />
          </label>
          <label class="profit-field">
            <span>平台售价 <small>{{ priceCurrency }}</small></span>
            <span class="profit-input-with-prefix"><b>{{ pricePrefix }}</b><NInputNumber v-model:value="priceOriginal" :min="0" :step="0.01" :show-button="false" clearable placeholder="输入售价" aria-label="平台售价" /></span>
          </label>
          <label class="profit-field">
            <span>采购成本 <small>{{ purchaseCurrency }}</small></span>
            <span class="profit-input-with-prefix"><b>{{ purchasePrefix }}</b><NInputNumber v-model:value="purchaseCost" :min="0" :step="0.01" :show-button="false" clearable placeholder="输入采购成本" aria-label="采购成本" /></span>
          </label>
          <label class="profit-field">
            <span>采购币种</span>
            <NSelect :value="purchaseCurrency" :options="purchaseCurrencyOptions" aria-label="采购币种" @update:value="updatePurchaseCurrency" />
          </label>
          <label class="profit-field">
            <span>重量</span>
            <span class="profit-input-with-suffix"><NInputNumber v-model:value="weightGrams" :min="0" :step="1" :show-button="false" clearable placeholder="输入重量" aria-label="重量克数" /><b>g</b></span>
          </label>
          <label class="profit-field">
            <span>包装成本 <small>CNY</small></span>
            <span class="profit-input-with-prefix"><b>¥</b><NInputNumber v-model:value="packingCostCny" :min="0" :step="0.01" :show-button="false" clearable placeholder="可选" aria-label="包装成本 CNY" /></span>
          </label>
          <label class="profit-field">
            <span>其他成本 <small>CNY</small></span>
            <span class="profit-input-with-prefix"><b>¥</b><NInputNumber v-model:value="otherCostCny" :min="0" :step="0.01" :show-button="false" clearable placeholder="可选" aria-label="其他成本 CNY" /></span>
          </label>
          <label class="profit-field">
            <span>USD/CNY 测算汇率</span>
            <span class="profit-rate-input"><b>1 USD =</b><NInputNumber v-model:value="usdCnyRate" :min="0" :step="0.01" :show-button="false" clearable aria-label="USD CNY 测算汇率" /><b>CNY</b></span>
          </label>
        </div>
      </NCard>

      <NCard :bordered="false" class="analytics-table-card profit-price-panel">
        <template #header>
          <div class="analytics-panel-heading">
            <div>
              <h2><morph-icon icon="layers" size="18" stroke-width="1.8" />售价折算</h2>
              <span>输入变化后即时更新标准化价格</span>
            </div>
          </div>
        </template>
        <div class="profit-conversion-values">
          <div class="profit-conversion-item">
            <span>{{ priceUsdLabel }}</span>
            <strong>{{ formatProfitMoney(result.price_usd, "USD") }}</strong>
          </div>
          <div class="profit-conversion-item">
            <span>{{ priceCnyLabel }}</span>
            <strong>{{ formatProfitMoney(result.price_cny) }}</strong>
          </div>
        </div>
        <div class="profit-price-meta">
          <span>内部标准化字段</span>
          <code>price_original · price_currency · price_usd · price_cny</code>
        </div>
      </NCard>
    </div>

    <NCard :bordered="false" class="analytics-table-card profit-cost-panel">
      <template #header>
        <div class="analytics-panel-heading">
          <div>
            <h2><morph-icon icon="package" size="18" stroke-width="1.8" />费用明细</h2>
            <span>费用均以 CNY 核算；“—”表示规则尚未接入</span>
          </div>
          <NTag size="small" round class="profit-tone-tag--azure">{{ profitPathLabels[result.fulfillment_path] }}</NTag>
        </div>
      </template>
      <div class="profit-cost-list">
        <div v-for="key in PROFIT_COST_KEYS" :key="key" class="profit-cost-row">
          <div class="profit-cost-label">
            <strong>{{ profitCostLabels[key] }}</strong>
            <NTag size="small" round :bordered="false" type="default" :class="statusTone(result.costs[key].status) ? `profit-tone-tag--${statusTone(result.costs[key].status)}` : ''">
              {{ profitStatusLabels[result.costs[key].status] }}
            </NTag>
          </div>
          <strong class="profit-cost-value" :class="{ 'is-pending': result.costs[key].status !== 'implemented' }">
            {{ result.costs[key].status === "implemented" ? formatProfitMoney(result.costs[key].value) : "—" }}
          </strong>
        </div>
      </div>
    </NCard>

    <NCard :bordered="false" class="analytics-table-card profit-summary-panel">
      <template #header>
        <div class="analytics-panel-heading">
          <div>
            <h2><morph-icon icon="trendingUp" size="18" stroke-width="1.8" />利润汇总</h2>
            <span>基于当前已接入费用计算</span>
          </div>
        </div>
      </template>
      <div class="analytics-kpi-grid profit-summary-grid">
        <NCard :bordered="false" class="analytics-kpi-card tone-azure">
          <div class="analytics-kpi-head"><span>销售收入</span><span class="analytics-icon-badge tone-badge"><morph-icon icon="coins" size="18" stroke-width="1.8" /></span></div>
          <strong class="analytics-kpi-value tone-value">{{ formatProfitMoney(result.revenue_cny) }}</strong>
          <small>price_cny</small>
        </NCard>
        <NCard :bordered="false" class="analytics-kpi-card tone-peach">
          <div class="analytics-kpi-head"><span>总成本</span><span class="analytics-icon-badge tone-badge"><morph-icon icon="wallet" size="18" stroke-width="1.8" /></span></div>
          <strong class="analytics-kpi-value tone-value">{{ formatProfitMoney(result.total_cost_cny) }}</strong>
          <small>已接入费用之和</small>
        </NCard>
        <NCard :bordered="false" class="analytics-kpi-card tone-mint">
          <div class="analytics-kpi-head"><span>预计利润</span><span class="analytics-icon-badge tone-badge"><morph-icon icon="trendingUp" size="18" stroke-width="1.8" /></span></div>
          <strong class="analytics-kpi-value tone-value" :class="{ 'is-negative': result.profit_cny !== null && result.profit_cny < 0 }">{{ formatProfitMoney(result.profit_cny) }}</strong>
          <small>销售收入 − 当前总成本</small>
        </NCard>
        <NCard :bordered="false" class="analytics-kpi-card tone-lavender">
          <div class="analytics-kpi-head"><span>净利润率</span><span class="analytics-icon-badge tone-badge"><morph-icon icon="percent" size="18" stroke-width="1.8" /></span></div>
          <strong class="analytics-kpi-value tone-value" :class="{ 'is-negative': result.net_margin !== null && result.net_margin < 0 }">{{ formatProfitPercent(result.net_margin) }}</strong>
          <small>当前阶段性结果</small>
        </NCard>
      </div>
      <p class="profit-summary-note">{{ summaryNote }}</p>
    </NCard>
  </section>
</template>
