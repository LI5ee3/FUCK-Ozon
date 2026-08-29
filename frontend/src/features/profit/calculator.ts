export type ProfitShopId = 1 | 2;
export type ProfitPriceCurrency = "USD" | "CNY";
export type ProfitFulfillmentMode = "FBP" | "realFBS";
export type ProfitRealFbsChannel = "hongkong" | "shenzhen";
export type ProfitPath = "FBP" | "realFBS_hongkong" | "realFBS_shenzhen";
export type ProfitCostStatus = "implemented" | "missing_input" | "not_implemented" | "not_applicable";
export type ProfitCostKey =
  | "purchase_cost"
  | "hunchun_shipping"
  | "cross_border_shipping"
  | "last_mile_shipping"
  | "warehouse_fee"
  | "commission"
  | "advertising"
  | "international_transport_contract_service"
  | "bank_acquiring_fee"
  | "packing"
  | "other_cost";

type ProfitValue = number | string | null | undefined;

export interface ProfitInput {
  shopId?: ProfitShopId;
  priceOriginal?: ProfitValue;
  purchasePriceUsd?: ProfitValue;
  weightGrams?: ProfitValue;
  usdCnyRate?: ProfitValue;
  fulfillmentMode?: ProfitFulfillmentMode;
  realFbsChannel?: ProfitRealFbsChannel;
}

export interface ProfitPrice {
  price_original: number | null;
  price_currency: ProfitPriceCurrency | null;
  price_usd: number | null;
  price_cny: number | null;
}

export interface ProfitCostItem {
  value: number | null;
  status: ProfitCostStatus;
}

export type ProfitCosts = Record<ProfitCostKey, ProfitCostItem>;

export interface ProfitResult extends ProfitPrice {
  costs: ProfitCosts;
  fulfillment_path: ProfitPath;
  revenue_cny: number | null;
  total_cost_cny: number | null;
  profit_cny: number | null;
  net_margin: number | null;
}

export const PROFIT_COST_KEYS: readonly ProfitCostKey[] = [
  "purchase_cost",
  "hunchun_shipping",
  "cross_border_shipping",
  "last_mile_shipping",
  "warehouse_fee",
  "commission",
  "advertising",
  "international_transport_contract_service",
  "bank_acquiring_fee",
  "packing",
  "other_cost",
];

function profitNumber(value: ProfitValue): number | null {
  if (value == null || String(value).trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

export function normalizeProfitPrice(
  shopId: ProfitShopId | number | string | null | undefined,
  original: ProfitValue,
  usdCnyRate: ProfitValue,
): ProfitPrice {
  const shopNumber = Number(shopId);
  const currency: ProfitPriceCurrency | null = shopNumber === 1 ? "USD" : shopNumber === 2 ? "CNY" : null;
  const priceOriginal = profitNumber(original);
  const rate = profitNumber(usdCnyRate);
  const hasRate = rate !== null && rate > 0;
  let priceUsd: number | null = null;
  let priceCny: number | null = null;

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
    price_cny: priceCny,
  };
}

export function emptyProfitCosts(input: ProfitInput = {}): ProfitCosts {
  const purchasePriceUsd = profitNumber(input.purchasePriceUsd);
  const rate = profitNumber(input.usdCnyRate);
  const purchaseCost = purchasePriceUsd !== null && rate !== null && rate > 0
    ? purchasePriceUsd * rate
    : null;
  const costs = {} as ProfitCosts;

  for (const key of PROFIT_COST_KEYS) {
    costs[key] = key === "purchase_cost"
      ? { value: purchaseCost, status: purchaseCost === null ? "missing_input" : "implemented" }
      : { value: null, status: "not_implemented" };
  }
  return costs;
}

function contractServiceCost(price: ProfitPrice): ProfitCostItem {
  return price.price_cny !== null
    ? { value: price.price_cny * 0.0033, status: "implemented" }
    : { value: null, status: "missing_input" };
}

function acquiringFeeCost(price: ProfitPrice): ProfitCostItem {
  return price.price_cny !== null
    ? { value: price.price_cny * 0.01, status: "implemented" }
    : { value: null, status: "missing_input" };
}

export function calculateFbpCosts(input: ProfitInput = {}, price: ProfitPrice): ProfitCosts {
  const costs = emptyProfitCosts(input);
  costs.hunchun_shipping = { value: 10, status: "implemented" };
  costs.international_transport_contract_service = contractServiceCost(price);
  costs.bank_acquiring_fee = acquiringFeeCost(price);
  return costs;
}

export function calculateRealFbsHongKongCosts(input: ProfitInput = {}, price: ProfitPrice): ProfitCosts {
  const costs = emptyProfitCosts(input);
  costs.hunchun_shipping = { value: null, status: "not_applicable" };
  costs.international_transport_contract_service = contractServiceCost(price);
  costs.bank_acquiring_fee = acquiringFeeCost(price);
  return costs;
}

export function calculateRealFbsShenzhenCosts(input: ProfitInput = {}, price: ProfitPrice): ProfitCosts {
  const costs = emptyProfitCosts(input);
  costs.hunchun_shipping = { value: null, status: "not_applicable" };
  costs.international_transport_contract_service = contractServiceCost(price);
  costs.bank_acquiring_fee = acquiringFeeCost(price);
  return costs;
}

export function calculateProfit(input: ProfitInput = {}): ProfitResult {
  const price = normalizeProfitPrice(input.shopId, input.priceOriginal, input.usdCnyRate);
  let costs: ProfitCosts;
  let fulfillmentPath: ProfitPath;

  if (input.fulfillmentMode === "realFBS" && input.realFbsChannel === "shenzhen") {
    costs = calculateRealFbsShenzhenCosts(input, price);
    fulfillmentPath = "realFBS_shenzhen";
  } else if (input.fulfillmentMode === "realFBS") {
    costs = calculateRealFbsHongKongCosts(input, price);
    fulfillmentPath = "realFBS_hongkong";
  } else {
    costs = calculateFbpCosts(input, price);
    fulfillmentPath = "FBP";
  }

  const hasPurchaseCost = costs.purchase_cost.status === "implemented";
  const totalCostCny = hasPurchaseCost
    ? PROFIT_COST_KEYS.reduce(
        (total, key) => total + (costs[key].status === "implemented" ? costs[key].value ?? 0 : 0),
        0,
      )
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
    net_margin: profitCny !== null && price.price_cny !== null && price.price_cny > 0
      ? profitCny / price.price_cny
      : null,
  };
}
