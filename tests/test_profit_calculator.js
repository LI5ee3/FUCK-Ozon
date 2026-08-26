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
  assert.equal(fbp.fulfillment_path, "FBP");
  assert.equal(fbp.profit_cny, 432);
  assert.equal(calculateProfit({fulfillmentMode: "realFBS", realFbsChannel: "hongkong"}).fulfillment_path, "realFBS_hongkong");
  assert.equal(calculateProfit({fulfillmentMode: "realFBS", realFbsChannel: "shenzhen"}).fulfillment_path, "realFBS_shenzhen");
});
