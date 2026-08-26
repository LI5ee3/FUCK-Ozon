const test = require("node:test");
const assert = require("node:assert/strict");
const {
  COST_KEYS,
  normalizeProfitPrice,
  calculateProfit
} = require("../static/profit-calculator.js");

function assertClose(actual, expected) {
  assert.ok(Math.abs(actual - expected) < 1e-10, `${actual} is not close to ${expected}`);
}

test("店铺1将 USD 售价标准化为 USD/CNY", () => {
  assert.deepEqual(normalizeProfitPrice(1, 100, 7.2), {
    price_original: 100,
    price_currency: "USD",
    price_usd: 100,
    price_cny: 720
  });
});

test("店铺2将 CNY 售价标准化为 USD/CNY", () => {
  assert.deepEqual(normalizeProfitPrice(2, 720, 7.2), {
    price_original: 720,
    price_currency: "CNY",
    price_usd: 100,
    price_cny: 720
  });
});

test("费用 key 完整重命名", () => {
  assert.ok(COST_KEYS.includes("international_transport_contract_service"));
  assert.ok(COST_KEYS.includes("bank_acquiring_fee"));
  assert.equal(COST_KEYS.includes(["insur", "ance"].join("")), false);
});

test("采购成本使用 USD 采购价乘测算汇率，并按履约路径分流", () => {
  const fbp = calculateProfit({
    shopId: 1,
    priceOriginal: 100,
    purchasePriceUsd: 40,
    usdCnyRate: 7.2,
    fulfillmentMode: "FBP"
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
    purchasePriceUsd: 40,
    usdCnyRate: 7.2,
    fulfillmentMode: "realFBS"
  };
  const hongKong = calculateProfit({...realFbsInput, realFbsChannel: "hongkong"});
  const shenzhen = calculateProfit({...realFbsInput, realFbsChannel: "shenzhen"});
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
    purchasePriceUsd: 40,
    usdCnyRate: 7.2,
    fulfillmentMode: "FBP"
  });
  assert.equal(shop2.price_cny, 720);
  assertClose(shop2.costs.international_transport_contract_service.value, 2.376);
  assertClose(shop2.costs.bank_acquiring_fee.value, 7.2);
  assertClose(shop2.total_cost_cny, 307.576);

  const missingPrice = calculateProfit({shopId: 1, usdCnyRate: 7.2, fulfillmentMode: "FBP"});
  const missingRate = calculateProfit({shopId: 1, priceOriginal: 100, usdCnyRate: 0, fulfillmentMode: "FBP"});
  for (const result of [missingPrice, missingRate]) {
    assert.equal(result.costs.international_transport_contract_service.value, null);
    assert.equal(result.costs.international_transport_contract_service.status, "missing_input");
    assert.equal(result.costs.bank_acquiring_fee.value, null);
    assert.equal(result.costs.bank_acquiring_fee.status, "missing_input");
  }
});
