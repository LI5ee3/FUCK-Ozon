import test from "node:test";
import assert from "node:assert/strict";
import {
  PROFIT_COST_KEYS,
  calculateProfit as calculateProfitFunction,
  normalizeProfitPrice,
} from "../frontend/src/features/profit/calculator.ts";

function assertClose(actual, expected) {
  assert.ok(Math.abs(actual - expected) < 1e-10, `${actual} is not close to ${expected}`);
}

const zeroCommission = { salesPercentFbp: 0, salesPercentRfbs: 0 };
function calculateProfit(input = {}) {
  return calculateProfitFunction({ ...zeroCommission, ...input });
}

test("店铺1将 USD 售价标准化为 USD/CNY", () => {
  assert.deepEqual(normalizeProfitPrice(1, 100, 7.2), {
    price_original: 100,
    price_currency: "USD",
    price_usd: 100,
    price_cny: 720,
  });
});

test("店铺2将 CNY 售价标准化为 USD/CNY", () => {
  assert.deepEqual(normalizeProfitPrice(2, 720, 7.2), {
    price_original: 720,
    price_currency: "CNY",
    price_usd: 100,
    price_cny: 720,
  });
});

test("费用 key 完整重命名", () => {
  assert.ok(PROFIT_COST_KEYS.includes("international_transport_contract_service"));
  assert.ok(PROFIT_COST_KEYS.includes("bank_acquiring_fee"));
  assert.equal(PROFIT_COST_KEYS.includes(["insur", "ance"].join("")), false);
});

test("采购成本使用 USD 成本乘测算汇率，并按履约路径分流", () => {
  const fbp = calculateProfit({
    shopId: 1,
    priceOriginal: 100,
    purchaseCost: 40,
    purchaseCurrency: "USD",
    usdCnyRate: 7.2,
    fulfillmentMode: "FBP",
  });
  assert.equal(fbp.costs.purchase_cost.value, 288);
  assert.equal(fbp.costs.hunchun_shipping.value, 10);
  assert.equal(fbp.costs.hunchun_shipping.status, "implemented");
  assert.equal(Object.prototype.hasOwnProperty.call(fbp.costs, ["insur", "ance"].join("")), false);
  assertClose(fbp.costs.international_transport_contract_service.value, 2.376);
  assert.equal(fbp.costs.international_transport_contract_service.status, "implemented");
  assertClose(fbp.costs.bank_acquiring_fee.value, 7.2);
  assert.equal(fbp.costs.bank_acquiring_fee.status, "implemented");
  assertClose(fbp.total_cost_cny, 307.576);
  assert.equal(fbp.fulfillment_path, "FBP");
  assertClose(fbp.profit_cny, 412.424);
  assertClose(fbp.net_margin, 412.424 / 720);

  const realFbsInput = {
    shopId: 1,
    priceOriginal: 100,
    purchaseCost: 40,
    purchaseCurrency: "USD",
    usdCnyRate: 7.2,
    fulfillmentMode: "realFBS",
  };
  const hongKong = calculateProfit({ ...realFbsInput, realFbsChannel: "hongkong" });
  const shenzhen = calculateProfit({ ...realFbsInput, realFbsChannel: "shenzhen" });
  assert.equal(hongKong.fulfillment_path, "realFBS_hongkong");
  assert.equal(hongKong.costs.hunchun_shipping.value, null);
  assert.equal(hongKong.costs.hunchun_shipping.status, "not_applicable");
  assert.equal(Object.prototype.hasOwnProperty.call(hongKong.costs, ["insur", "ance"].join("")), false);
  assertClose(hongKong.costs.international_transport_contract_service.value, 2.376);
  assert.equal(hongKong.costs.international_transport_contract_service.status, "implemented");
  assertClose(hongKong.costs.bank_acquiring_fee.value, 7.2);
  assert.equal(hongKong.costs.bank_acquiring_fee.status, "implemented");
  assertClose(hongKong.total_cost_cny, 297.576);
  assert.equal(shenzhen.fulfillment_path, "realFBS_shenzhen");
  assert.equal(shenzhen.costs.hunchun_shipping.value, null);
  assert.equal(shenzhen.costs.hunchun_shipping.status, "not_applicable");
  assert.equal(Object.prototype.hasOwnProperty.call(shenzhen.costs, ["insur", "ance"].join("")), false);
  assertClose(shenzhen.costs.international_transport_contract_service.value, 2.376);
  assert.equal(shenzhen.costs.international_transport_contract_service.status, "implemented");
  assertClose(shenzhen.costs.bank_acquiring_fee.value, 7.2);
  assert.equal(shenzhen.costs.bank_acquiring_fee.status, "implemented");
  assertClose(shenzhen.total_cost_cny, 297.576);
});

test("店铺2使用 price_cny，缺少人民币售价时不返回 0", () => {
  const shop2 = calculateProfit({
    shopId: 2,
    priceOriginal: 720,
    purchaseCost: 40,
    purchaseCurrency: "USD",
    usdCnyRate: 7.2,
    fulfillmentMode: "FBP",
  });
  assert.equal(shop2.price_cny, 720);
  assertClose(shop2.costs.international_transport_contract_service.value, 2.376);
  assertClose(shop2.costs.bank_acquiring_fee.value, 7.2);
  assertClose(shop2.total_cost_cny, 307.576);

  const missingPrice = calculateProfit({ shopId: 1, usdCnyRate: 7.2, fulfillmentMode: "FBP" });
  const missingRate = calculateProfit({ shopId: 1, priceOriginal: 100, usdCnyRate: 0, fulfillmentMode: "FBP" });
  for (const result of [missingPrice, missingRate]) {
    assert.equal(result.costs.international_transport_contract_service.value, null);
    assert.equal(result.costs.international_transport_contract_service.status, "missing_input");
    assert.equal(result.costs.bank_acquiring_fee.value, null);
    assert.equal(result.costs.bank_acquiring_fee.status, "missing_input");
  }
});

test("CNY 采购成本不乘汇率，店铺2无汇率仍可计算", () => {
  const result = calculateProfit({
    shopId: 2,
    priceOriginal: 700,
    purchaseCost: 400,
    purchaseCurrency: "CNY",
    usdCnyRate: null,
    packingCostCny: 0,
    otherCostCny: 0,
    fulfillmentMode: "FBP",
  });
  assert.equal(result.price_cny, 700);
  assert.equal(result.costs.purchase_cost.value, 400);
  assert.equal(result.costs.purchase_cost.status, "implemented");
  assert.equal(result.costs.packing.value, 0);
  assert.equal(result.costs.packing.status, "implemented");
  assert.equal(result.costs.other_cost.value, 0);
  assert.equal(result.costs.other_cost.status, "implemented");
  assertClose(result.total_cost_cny, 419.31);
  assertClose(result.profit_cny, 280.69);
});

test("USD 采购成本缺少有效汇率时为 missing_input", () => {
  const result = calculateProfit({
    shopId: 2,
    priceOriginal: 700,
    purchaseCost: 60,
    purchaseCurrency: "USD",
    usdCnyRate: 0,
    fulfillmentMode: "FBP",
  });
  assert.equal(result.price_cny, 700);
  assert.equal(result.costs.purchase_cost.value, null);
  assert.equal(result.costs.purchase_cost.status, "missing_input");
  assert.equal(result.total_cost_cny, null);
  assert.equal(result.profit_cny, null);
});

test("店铺1缺少汇率时不能生成 CNY revenue 或 profit", () => {
  const result = calculateProfit({
    shopId: 1,
    priceOriginal: 100,
    purchaseCost: 400,
    purchaseCurrency: "CNY",
    usdCnyRate: null,
    fulfillmentMode: "FBP",
  });
  assert.equal(result.price_usd, 100);
  assert.equal(result.price_cny, null);
  assert.equal(result.revenue_cny, null);
  assert.equal(result.profit_cny, null);
});

test("采购币种与店铺售价币种解耦", () => {
  const shop1CnyPurchase = calculateProfit({
    shopId: 1, priceOriginal: 100, purchaseCost: 400, purchaseCurrency: "CNY", usdCnyRate: 7.2,
    fulfillmentMode: "FBP",
  });
  const shop2UsdPurchase = calculateProfit({
    shopId: 2, priceOriginal: 700, purchaseCost: 60, purchaseCurrency: "USD", usdCnyRate: 7.2,
    fulfillmentMode: "FBP",
  });
  assert.equal(shop1CnyPurchase.costs.purchase_cost.value, 400);
  assert.equal(shop2UsdPurchase.costs.purchase_cost.value, 432);
});

test("packing 和 other_cost 接收有效金额，零值仍为已接入", () => {
  const result = calculateProfit({
    shopId: 2,
    priceOriginal: 700,
    purchaseCost: 400,
    purchaseCurrency: "CNY",
    usdCnyRate: null,
    packingCostCny: 2.5,
    otherCostCny: 1.5,
    fulfillmentMode: "FBP",
  });
  assert.equal(result.costs.packing.value, 2.5);
  assert.equal(result.costs.packing.status, "implemented");
  assert.equal(result.costs.other_cost.value, 1.5);
  assert.equal(result.costs.other_cost.status, "implemented");
  assertClose(result.total_cost_cny, 423.31);
});

test("负数、NaN、Infinity 不参与计算", () => {
  const result = calculateProfit({
    shopId: 2,
    priceOriginal: 700,
    purchaseCost: 400,
    purchaseCurrency: "CNY",
    usdCnyRate: null,
    packingCostCny: NaN,
    otherCostCny: -1,
    fulfillmentMode: "FBP",
  });
  const infinite = calculateProfit({
    shopId: 2,
    priceOriginal: 700,
    purchaseCost: 400,
    purchaseCurrency: "CNY",
    usdCnyRate: Infinity,
    fulfillmentMode: "FBP",
  });
  assert.equal(result.costs.packing.value, null);
  assert.equal(result.costs.other_cost.value, null);
  assert.ok(Number.isFinite(result.total_cost_cny));
  assert.equal(infinite.costs.purchase_cost.value, 400);
  assert.ok(Number.isFinite(infinite.total_cost_cny));
});

test("FBP 和 realFBS 分别使用当前 Ozon 佣金率", () => {
  const fbp = calculateProfitFunction({
    shopId: 1, priceOriginal: 100, purchaseCost: 0, purchaseCurrency: "CNY", usdCnyRate: 7.2,
    salesPercentFbp: 15, salesPercentRfbs: 12, fulfillmentMode: "FBP",
  });
  assert.equal(fbp.price_cny, 720);
  assert.equal(fbp.costs.commission.value, 108);
  assert.equal(fbp.costs.commission.status, "implemented");

  for (const channel of ["hongkong", "shenzhen"]) {
    const realFbs = calculateProfitFunction({
      shopId: 2, priceOriginal: 700, purchaseCost: 0, purchaseCurrency: "CNY", usdCnyRate: null,
      salesPercentFbp: 15, salesPercentRfbs: 12, fulfillmentMode: "realFBS", realFbsChannel: channel,
    });
    assert.equal(realFbs.costs.commission.value, 84);
    assert.equal(realFbs.costs.commission.status, "implemented");
  }
});

test("佣金 0% 是已接入的零成本，缺失或非法佣金不会当作 0", () => {
  const zero = calculateProfitFunction({
    shopId: 2, priceOriginal: 700, purchaseCost: 400, purchaseCurrency: "CNY", usdCnyRate: null,
    salesPercentFbp: 0, packingCostCny: 0, otherCostCny: 0, fulfillmentMode: "FBP",
  });
  assert.equal(zero.costs.commission.value, 0);
  assert.equal(zero.costs.commission.status, "implemented");
  assert.ok(Number.isFinite(zero.profit_cny));

  const missing = calculateProfitFunction({
    shopId: 2, priceOriginal: 700, purchaseCost: 400, purchaseCurrency: "CNY", usdCnyRate: null,
    fulfillmentMode: "FBP",
  });
  assert.equal(missing.costs.commission.value, null);
  assert.equal(missing.costs.commission.status, "missing_input");
  assert.equal(missing.total_cost_cny, null);
  assert.equal(missing.profit_cny, null);

  const unavailable = calculateProfitFunction({
    shopId: 2, priceOriginal: 700, purchaseCost: 400, purchaseCurrency: "CNY", usdCnyRate: null,
    salesPercentFbp: null, fulfillmentMode: "FBP",
  });
  assert.equal(unavailable.costs.commission.status, "data_unavailable");
  assert.equal(unavailable.profit_cny, null);

  for (const value of [-1, 101, NaN, Infinity, true]) {
    const invalid = calculateProfitFunction({
      shopId: 2, priceOriginal: 700, purchaseCost: 400, purchaseCurrency: "CNY", usdCnyRate: null,
      salesPercentFbp: value, fulfillmentMode: "FBP",
    });
    assert.equal(invalid.costs.commission.value, null);
    assert.equal(invalid.costs.commission.status, "data_unavailable");
    assert.equal(invalid.profit_cny, null);
  }
});
