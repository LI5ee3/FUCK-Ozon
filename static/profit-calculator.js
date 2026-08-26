const PROFIT_PRICE_CURRENCIES = Object.freeze({ 1: "USD", 2: "CNY" });
const PROFIT_COST_KEYS = Object.freeze([
  "purchase_cost",
  "hunchun_shipping",
  "cross_border_shipping",
  "last_mile_shipping",
  "warehouse_fee",
  "commission",
  "advertising",
  "international_logistics",
  "bank_fee",
  "insurance",
  "packing",
  "other_cost"
]);

function profitNumber(value) {
  if (value == null || String(value).trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function normalizeProfitPrice(shopId, original, usdCnyRate) {
  const currency = PROFIT_PRICE_CURRENCIES[Number(shopId)] || null;
  const priceOriginal = profitNumber(original);
  const rate = profitNumber(usdCnyRate);
  const hasRate = rate !== null && rate > 0;
  let priceUsd = null;
  let priceCny = null;

  if (currency === "USD" && priceOriginal !== null) {
    priceUsd = priceOriginal;
    if (hasRate) priceCny = priceOriginal * rate;
  }
  if (currency === "CNY" && priceOriginal !== null) {
    priceCny = priceOriginal;
    if (hasRate) priceUsd = priceOriginal / rate;
  }

  return {
    price_original: priceOriginal,
    price_currency: currency,
    price_usd: priceUsd,
    price_cny: priceCny
  };
}

function emptyProfitCosts(input = {}) {
  const purchasePriceUsd = profitNumber(input.purchasePriceUsd);
  const rate = profitNumber(input.usdCnyRate);
  const purchaseCost = purchasePriceUsd !== null && rate !== null && rate > 0
    ? purchasePriceUsd * rate
    : null;
  const costs = {};

  for (const key of PROFIT_COST_KEYS) {
    costs[key] = key === "purchase_cost"
      ? { value: purchaseCost, status: purchaseCost === null ? "missing_input" : "implemented" }
      : { value: null, status: "not_implemented" };
  }
  return costs;
}

function calculateFbpCosts(input) {
  const costs = emptyProfitCosts(input);
  costs.hunchun_shipping = { value: 10, status: "implemented" };
  return costs;
}

function calculateRealFbsHongKongCosts(input) {
  const costs = emptyProfitCosts(input);
  costs.hunchun_shipping = { value: null, status: "not_applicable" };
  return costs;
}

function calculateRealFbsShenzhenCosts(input) {
  const costs = emptyProfitCosts(input);
  costs.hunchun_shipping = { value: null, status: "not_applicable" };
  return costs;
}

function calculateProfit(input = {}) {
  const price = normalizeProfitPrice(input.shopId, input.priceOriginal, input.usdCnyRate);
  let costs;
  let fulfillmentPath;

  if (input.fulfillmentMode === "realFBS" && input.realFbsChannel === "shenzhen") {
    costs = calculateRealFbsShenzhenCosts(input);
    fulfillmentPath = "realFBS_shenzhen";
  } else if (input.fulfillmentMode === "realFBS") {
    costs = calculateRealFbsHongKongCosts(input);
    fulfillmentPath = "realFBS_hongkong";
  } else {
    costs = calculateFbpCosts(input);
    fulfillmentPath = "FBP";
  }

  const hasPurchaseCost = costs.purchase_cost.status === "implemented";
  const totalCostCny = hasPurchaseCost
    ? PROFIT_COST_KEYS.reduce((total, key) => total + (costs[key].status === "implemented" ? costs[key].value : 0), 0)
    : null;
  const profitCny = price.price_cny !== null && totalCostCny !== null
    ? price.price_cny - totalCostCny
    : null;

  return {
    ...price,
    costs,
    fulfillment_path: fulfillmentPath,
    revenue_cny: price.price_cny,
    total_cost_cny: totalCostCny,
    profit_cny: profitCny,
    net_margin: profitCny !== null && price.price_cny > 0 ? profitCny / price.price_cny : null
  };
}

const ProfitCalculator = {
  COST_KEYS: PROFIT_COST_KEYS,
  normalizeProfitPrice,
  calculateFbpCosts,
  calculateRealFbsHongKongCosts,
  calculateRealFbsShenzhenCosts,
  calculateProfit
};

globalThis.ProfitCalculator = ProfitCalculator;
if (typeof module !== "undefined" && module.exports) module.exports = ProfitCalculator;
