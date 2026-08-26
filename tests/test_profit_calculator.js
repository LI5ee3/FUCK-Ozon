const test = require("node:test");
const assert = require("node:assert/strict");
const {
  normalizeProfitPrice,
  calculateProfit
} = require("../static/profit-calculator.js");

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
  assert.equal(fbp.total_cost_cny, 298);
  assert.equal(fbp.fulfillment_path, "FBP");
  assert.equal(fbp.profit_cny, 422);
  assert.equal(fbp.net_margin, 422 / 720);

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
  assert.equal(hongKong.total_cost_cny, 288);
  assert.equal(shenzhen.fulfillment_path, "realFBS_shenzhen");
  assert.equal(shenzhen.costs.hunchun_shipping.value, null);
  assert.equal(shenzhen.costs.hunchun_shipping.status, "not_applicable");
  assert.equal(shenzhen.total_cost_cny, 288);
});
