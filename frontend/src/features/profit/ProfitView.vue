<script setup lang="ts">
import "../../styles/analytics.css";
import "./profit.css";
import { computed, ref } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import { NAlert, NCard, NInputNumber, NSelect, NTag } from "naive-ui";
import { useShop } from "../../shared/composables/useShop";
import {
  calculateProfit,
  PROFIT_COST_KEYS,
  type ProfitCostKey,
  type ProfitCostStatus,
  type ProfitFulfillmentMode,
  type ProfitPath,
  type ProfitRealFbsChannel,
  type ProfitShopId,
} from "./calculator";

const { shops } = useShop();
const profitShopId = ref<ProfitShopId>(1);
const fulfillmentMode = ref<ProfitFulfillmentMode>("FBP");
const realFbsChannel = ref<ProfitRealFbsChannel>("hongkong");
const priceOriginal = ref<number | null>(null);
const purchasePriceUsd = ref<number | null>(null);
const weightGrams = ref<number | null>(null);
const usdCnyRate = ref<number | null>(7.2);

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
  purchasePriceUsd: purchasePriceUsd.value,
  weightGrams: weightGrams.value,
  usdCnyRate: usdCnyRate.value,
  fulfillmentMode: fulfillmentMode.value,
  realFbsChannel: realFbsChannel.value,
}));

const priceCurrency = computed(() => result.value.price_currency ?? "—");
const pricePrefix = computed(() => result.value.price_currency === "CNY" ? "¥" : "$");
const priceUsdLabel = computed(() => result.value.price_currency === "CNY" ? "美元等值" : "美元售价");
const priceCnyLabel = computed(() => result.value.price_currency === "CNY" ? "人民币售价" : "人民币等值");
const showRealFbsChannel = computed(() => fulfillmentMode.value === "realFBS");
const configuredCostNames = computed(() => PROFIT_COST_KEYS
  .filter((key) => !["not_implemented", "not_applicable"].includes(result.value.costs[key].status))
  .map((key) => profitCostLabels[key]));
const profitNotice = computed(() => `当前已接入费用：${configuredCostNames.value.join("、") || "暂无"}；其他费用规则尚未接入。`);
const summaryNote = computed(() => result.value.profit_cny === null
  ? `请输入有效的平台售价、采购价格和测算汇率；${profitNotice.value}`
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
              <span>店铺币种固定，不能自由选择售价币种</span>
            </div>
          </div>
        </template>
        <div class="profit-fields-grid">
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
            <span>采购价格 <small>USD</small></span>
            <span class="profit-input-with-prefix"><b>$</b><NInputNumber v-model:value="purchasePriceUsd" :min="0" :step="0.01" :show-button="false" clearable placeholder="输入采购价" aria-label="采购价格 USD" /></span>
          </label>
          <label class="profit-field">
            <span>重量</span>
            <span class="profit-input-with-suffix"><NInputNumber v-model:value="weightGrams" :min="0" :step="1" :show-button="false" clearable placeholder="输入重量" aria-label="重量克数" /><b>g</b></span>
          </label>
          <label class="profit-field">
            <span>USD/CNY 测算汇率</span>
            <span class="profit-rate-input"><b>1 USD =</b><NInputNumber v-model:value="usdCnyRate" :min="0.0001" :step="0.01" :show-button="false" aria-label="USD CNY 测算汇率" /><b>CNY</b></span>
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
