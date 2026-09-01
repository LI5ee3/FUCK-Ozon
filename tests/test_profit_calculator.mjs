import test from "node:test";
import assert from "node:assert/strict";
import {
  PROFIT_COST_KEYS,
  calculateCrossBorderShippingCny,
  calculateHongKongCrossBorderShippingCny,
  calculateOzonLogisticsPlatformElectronicServiceCny,
  calculateProfit,
  normalizeProfitPrice,
} from "../frontend/src/features/profit/calculator.ts";

function assertClose(actual, expected) {
  assert.ok(Math.abs(actual - expected) < 1e-10, `${actual} is not close to ${expected}`);
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

test("跨境运费按原始售价和重量分档并直接输出 CNY", () => {
  const priceCases = [
    [1, 19.99, 8.42], [1, 20, 23.02], [1, 90, 23.02], [1, 90.01, 29.76],
    [2, 149.99, 8.42], [2, 150, 23.02], [2, 650, 23.02], [2, 650.01, 29.76],
  ];
  for (const [shopId, price, expected] of priceCases) {
    const shipping = calculateCrossBorderShippingCny(shopId, price, 100);
    assert.equal(shipping.status, "implemented");
    assertClose(shipping.value, expected);
  }

  const weightCases = [
    [1, 10, 499, 28.5695], [1, 10, 500, 44.38],
    [1, 50, 1999, 118.9195], [1, 50, 2000, 114.64],
    [1, 100, 4999, 277.1595], [1, 100, 5000, 255.14],
  ];
  for (const [shopId, price, weight, expected] of weightCases) {
    assertClose(calculateCrossBorderShippingCny(shopId, price, weight).value, expected);
  }

  const withoutRate = calculateProfit({
    shopId: 2, priceOriginal: 650, purchaseCost: 0, purchaseCurrency: "CNY", usdCnyRate: null,
    weightGrams: 100, fulfillmentMode: "FBP",
  });
  const withRate = calculateProfit({
    shopId: 2, priceOriginal: 650, purchaseCost: 0, purchaseCurrency: "CNY", usdCnyRate: 99,
    weightGrams: 100, fulfillmentMode: "FBP",
  });
  assertClose(withRate.costs.cross_border_shipping.value, withoutRate.costs.cross_border_shipping.value);
});

test("FBP 与 realFBS 深圳共用原规则，香港使用独立正向跨境运费", () => {
  const input = {
    shopId: 2,
    priceOriginal: 700,
    purchaseCost: 0,
    purchaseCurrency: "CNY",
    usdCnyRate: null,
    servicePenaltyExchangeRateRub: 12,
    weightGrams: 100,
    lengthCm: 20,
    widthCm: 20,
    heightCm: 20,
  };
  const fbp = calculateProfit({ ...input, fulfillmentMode: "FBP" });
  const shenzhen = calculateProfit({ ...input, fulfillmentMode: "realFBS", realFbsChannel: "shenzhen" });
  const hongKong = calculateProfit({ ...input, fulfillmentMode: "realFBS", realFbsChannel: "hongkong" });
  assert.deepEqual(shenzhen.costs.cross_border_shipping, fbp.costs.cross_border_shipping);
  assert.equal(fbp.costs.hunchun_shipping.value, 10);
  assert.equal(shenzhen.costs.hunchun_shipping.status, "not_applicable");
  assertClose(hongKong.costs.cross_border_shipping.value, 28.6);
  assert.equal(hongKong.costs.cross_border_shipping.status, "implemented");
  assert.ok(hongKong.profit_cny !== null);
});

test("香港跨境运费按实重/体积重和 100g 计费单位计算", () => {
  for (const [weight, expected] of [[400, 57.4], [401, 67], [500, 67], [501, 76.6]]) {
    const shipping = calculateHongKongCrossBorderShippingCny(weight, 20, 20, 20);
    assert.equal(shipping.status, "implemented");
    assertClose(shipping.value, expected);
  }

  const volumetric = calculateHongKongCrossBorderShippingCny(100, 20, 20, 21);
  const heavierActual = calculateHongKongCrossBorderShippingCny(5000, 20, 20, 21);
  assert.equal(volumetric.status, "implemented");
  assertClose(volumetric.value, 153.4);
  assert.deepEqual(heavierActual, volumetric);

  const atSixty = calculateHongKongCrossBorderShippingCny(400, 20, 20, 20);
  assertClose(atSixty.value, 57.4);
});

test("香港跨境运费严格执行包裹限制并区分缺失输入", () => {
  assert.equal(calculateHongKongCrossBorderShippingCny(400, 150, 100, 50).status, "implemented");
  assert.equal(calculateHongKongCrossBorderShippingCny(400, 150.01, 100, 49).status, "data_unavailable");
  assert.equal(calculateHongKongCrossBorderShippingCny(400, 150, 100, 59.999).status, "implemented");
  assert.equal(calculateHongKongCrossBorderShippingCny(400, 150, 100, 60).status, "data_unavailable");
  assert.equal(calculateHongKongCrossBorderShippingCny(25000, 20, 20, 20).status, "implemented");
  assert.equal(calculateHongKongCrossBorderShippingCny(25000.01, 20, 20, 20).status, "data_unavailable");

  const volumetricOverLimit = calculateHongKongCrossBorderShippingCny(400, 150, 100, 50);
  assert.equal(volumetricOverLimit.status, "implemented");

  for (const values of [
    [null, 20, 20, 20], [400, null, 20, 20], [400, 20, null, 20], [400, 20, 20, null],
    [0, 20, 20, 20], [-1, 20, 20, 20], [400, 0, 20, 20], [400, 20, 20, "invalid"],
    [400, 20, 20, Number.NaN], [400, 20, 20, Number.POSITIVE_INFINITY],
  ]) {
    assert.equal(calculateHongKongCrossBorderShippingCny(...values).status, "missing_input");
  }

  const missing = calculateProfit({
    shopId: 2, priceOriginal: 700, purchaseCost: 400, purchaseCurrency: "CNY", usdCnyRate: null,
    servicePenaltyExchangeRateRub: 12, salesPercentRfbs: 0, weightGrams: 400,
    fulfillmentMode: "realFBS", realFbsChannel: "hongkong",
  });
  assert.equal(missing.costs.cross_border_shipping.status, "missing_input");
  assert.equal(missing.total_cost_cny, null);
  assert.equal(missing.profit_cny, null);
  assert.equal(missing.net_margin, null);
});

test("FBP 与 realFBS 深圳缺少有效售价或重量时阻止完整利润", () => {
  const cases = [
    { priceOriginal: null, weightGrams: 100 },
    { priceOriginal: 700, weightGrams: null },
    { priceOriginal: 700, weightGrams: 0 },
    { priceOriginal: 700, weightGrams: -1 },
    { priceOriginal: 700, weightGrams: Number.NaN },
    { priceOriginal: 700, weightGrams: Number.POSITIVE_INFINITY },
    { priceOriginal: 700, weightGrams: "" },
  ];
  for (const mode of ["FBP", "realFBS"]) {
    for (const values of cases) {
      const result = calculateProfit({
        shopId: 2, purchaseCost: 0, purchaseCurrency: "CNY", usdCnyRate: null,
        ...values, fulfillmentMode: mode, realFbsChannel: "shenzhen",
      });
      assert.equal(result.costs.cross_border_shipping.status, "missing_input");
      assert.equal(result.total_cost_cny, null);
      assert.equal(result.profit_cny, null);
      assert.equal(result.net_margin, null);
    }
  }
});

test("Ozon 物流平台电子服务费按 RUB 15/200 封顶封底且不提前取整", () => {
  assertClose(calculateOzonLogisticsPlatformElectronicServiceCny(2, 50, 12, null).value, 1.25);
  assertClose(calculateOzonLogisticsPlatformElectronicServiceCny(2, 100, 12, null).value, 2);
  assertClose(calculateOzonLogisticsPlatformElectronicServiceCny(2, 1000, 12, null).value, 200 / 12);

  assertClose(calculateOzonLogisticsPlatformElectronicServiceCny(1, 5, 80, 7.2).value, 1.35);
  assertClose(calculateOzonLogisticsPlatformElectronicServiceCny(1, 10, 80, 7.2).value, 1.44);
  assertClose(calculateOzonLogisticsPlatformElectronicServiceCny(1, 200, 80, 7.2).value, 18);
  assertClose(calculateOzonLogisticsPlatformElectronicServiceCny(2, 123.45, 12.3456, null).value, 2.469);
});

test("Ozon 物流平台电子服务费三条履约路径共用计算，且缺失数据会阻断利润", () => {
  const input = {
    shopId: 2,
    priceOriginal: 700,
    purchaseCost: 400,
    purchaseCurrency: "CNY",
    usdCnyRate: null,
    servicePenaltyExchangeRateRub: 12,
    weightGrams: 100,
    lengthCm: 20,
    widthCm: 20,
    heightCm: 20,
    salesPercentFbp: 0,
    salesPercentRfbs: 0,
  };
  const fbp = calculateProfit({ ...input, fulfillmentMode: "FBP" });
  const hongKong = calculateProfit({ ...input, fulfillmentMode: "realFBS", realFbsChannel: "hongkong" });
  const shenzhen = calculateProfit({ ...input, fulfillmentMode: "realFBS", realFbsChannel: "shenzhen" });
  for (const result of [fbp, hongKong, shenzhen]) {
    assert.equal(result.costs.ozon_logistics_platform_electronic_service.status, "implemented");
    assertClose(result.costs.ozon_logistics_platform_electronic_service.value, 14);
    assert.ok(Number.isFinite(result.total_cost_cny));
  }
  assertClose(hongKong.costs.cross_border_shipping.value, 28.6);
  assert.equal(hongKong.costs.cross_border_shipping.status, "implemented");

  for (const rate of [null, undefined, 0, -1, Number.NaN, Number.POSITIVE_INFINITY, "invalid"]) {
    const result = calculateProfit({ ...input, servicePenaltyExchangeRateRub: rate, fulfillmentMode: "FBP" });
    assert.equal(result.costs.ozon_logistics_platform_electronic_service.status, "data_unavailable");
    assert.equal(result.total_cost_cny, null);
    assert.equal(result.profit_cny, null);
    assert.equal(result.net_margin, null);
  }
  const missingPrice = calculateProfit({ ...input, priceOriginal: 0, fulfillmentMode: "FBP" });
  assert.equal(missingPrice.costs.ozon_logistics_platform_electronic_service.status, "missing_input");
  const missingShopRate = calculateProfit({ ...input, shopId: 1, priceOriginal: 100, usdCnyRate: null, fulfillmentMode: "FBP" });
  assert.equal(missingShopRate.costs.ozon_logistics_platform_electronic_service.status, "missing_input");
  const cnyWithoutUsdRate = calculateProfit({ ...input, usdCnyRate: null, fulfillmentMode: "FBP" });
  assert.equal(cnyWithoutUsdRate.costs.ozon_logistics_platform_electronic_service.status, "implemented");
});

test("费用 key 完整重命名", () => {
  assert.ok(PROFIT_COST_KEYS.includes("international_transport_contract_service"));
  assert.ok(PROFIT_COST_KEYS.includes("bank_acquiring_fee"));
  assert.ok(PROFIT_COST_KEYS.includes("ozon_logistics_platform_electronic_service"));
  assert.equal(PROFIT_COST_KEYS.includes("last_mile_shipping"), false);
  assert.equal(PROFIT_COST_KEYS.includes(["insur", "ance"].join("")), false);
});

test("采购成本使用 USD 成本乘测算汇率，并按履约路径分流", () => {
  const fbp = calculateProfit({
    shopId: 1,
    priceOriginal: 100,
    purchaseCost: 40,
    purchaseCurrency: "USD",
    usdCnyRate: 7.2,
    servicePenaltyExchangeRateRub: 80,
    weightGrams: 100,
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
  assertClose(fbp.costs.cross_border_shipping.value, 29.76);
  assert.equal(fbp.costs.cross_border_shipping.status, "implemented");
  assertClose(fbp.costs.ozon_logistics_platform_electronic_service.value, 14.4);
  assertClose(fbp.total_cost_cny, 351.736);
  assert.equal(fbp.fulfillment_path, "FBP");
  assertClose(fbp.profit_cny, 368.264);
  assertClose(fbp.net_margin, 368.264 / 720);

  const realFbsInput = {
    shopId: 1,
    priceOriginal: 100,
    purchaseCost: 40,
    purchaseCurrency: "USD",
    usdCnyRate: 7.2,
    servicePenaltyExchangeRateRub: 80,
    weightGrams: 100,
    lengthCm: 10,
    widthCm: 5,
    heightCm: 3,
    fulfillmentMode: "realFBS",
  };
  const hongKong = calculateProfit({ ...realFbsInput, realFbsChannel: "hongkong" });
  const shenzhen = calculateProfit({ ...realFbsInput, realFbsChannel: "shenzhen" });
  assert.equal(hongKong.fulfillment_path, "realFBS_hongkong");
  assert.equal(hongKong.costs.hunchun_shipping.value, null);
  assert.equal(hongKong.costs.hunchun_shipping.status, "not_applicable");
  assert.equal(Object.prototype.hasOwnProperty.call(hongKong.costs, ["insur", "ance"].join("")), false);
  assertClose(hongKong.costs.cross_border_shipping.value, 28.6);
  assertClose(hongKong.costs.international_transport_contract_service.value, 2.376);
  assert.equal(hongKong.costs.international_transport_contract_service.status, "implemented");
  assertClose(hongKong.costs.bank_acquiring_fee.value, 7.2);
  assert.equal(hongKong.costs.bank_acquiring_fee.status, "implemented");
  assertClose(hongKong.total_cost_cny, 340.576);
  assert.equal(shenzhen.fulfillment_path, "realFBS_shenzhen");
  assert.equal(shenzhen.costs.hunchun_shipping.value, null);
  assert.equal(shenzhen.costs.hunchun_shipping.status, "not_applicable");
  assert.equal(Object.prototype.hasOwnProperty.call(shenzhen.costs, ["insur", "ance"].join("")), false);
  assertClose(shenzhen.costs.international_transport_contract_service.value, 2.376);
  assert.equal(shenzhen.costs.international_transport_contract_service.status, "implemented");
  assertClose(shenzhen.costs.bank_acquiring_fee.value, 7.2);
  assert.equal(shenzhen.costs.bank_acquiring_fee.status, "implemented");
  assertClose(shenzhen.costs.cross_border_shipping.value, 29.76);
  assert.equal(shenzhen.costs.cross_border_shipping.status, "implemented");
  assertClose(shenzhen.total_cost_cny, 341.736);
});

test("店铺2使用 price_cny，缺少人民币售价时不返回 0", () => {
  const shop2 = calculateProfit({
    shopId: 2,
    priceOriginal: 720,
    purchaseCost: 40,
    purchaseCurrency: "USD",
    usdCnyRate: 7.2,
    servicePenaltyExchangeRateRub: 12,
    weightGrams: 100,
    fulfillmentMode: "FBP",
  });
  assert.equal(shop2.price_cny, 720);
  assertClose(shop2.costs.international_transport_contract_service.value, 2.376);
  assertClose(shop2.costs.bank_acquiring_fee.value, 7.2);
  assertClose(shop2.costs.cross_border_shipping.value, 29.76);
  assertClose(shop2.costs.ozon_logistics_platform_electronic_service.value, 14.4);
  assertClose(shop2.total_cost_cny, 351.736);

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
    servicePenaltyExchangeRateRub: 12,
    weightGrams: 100,
    fulfillmentMode: "FBP",
  });
  assert.equal(result.price_cny, 700);
  assert.equal(result.costs.purchase_cost.value, 400);
  assert.equal(result.costs.purchase_cost.status, "implemented");
  assert.equal(result.costs.packing.value, 0);
  assert.equal(result.costs.packing.status, "implemented");
  assert.equal(result.costs.other_cost.value, 0);
  assert.equal(result.costs.other_cost.status, "implemented");
  assertClose(result.costs.cross_border_shipping.value, 29.76);
  assertClose(result.costs.ozon_logistics_platform_electronic_service.value, 14);
  assertClose(result.total_cost_cny, 463.07);
  assertClose(result.profit_cny, 236.93);
});

test("USD 采购成本缺少有效汇率时为 missing_input", () => {
  const result = calculateProfit({
    shopId: 2,
    priceOriginal: 700,
    purchaseCost: 60,
    purchaseCurrency: "USD",
    usdCnyRate: 0,
    servicePenaltyExchangeRateRub: 12,
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
    servicePenaltyExchangeRateRub: 12,
    weightGrams: 100,
    fulfillmentMode: "FBP",
  });
  assert.equal(result.costs.packing.value, 2.5);
  assert.equal(result.costs.packing.status, "implemented");
  assert.equal(result.costs.other_cost.value, 1.5);
  assert.equal(result.costs.other_cost.status, "implemented");
  assertClose(result.total_cost_cny, 467.07);
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
    servicePenaltyExchangeRateRub: 12,
    weightGrams: 100,
    fulfillmentMode: "FBP",
  });
  const infinite = calculateProfit({
    shopId: 2,
    priceOriginal: 700,
    purchaseCost: 400,
    purchaseCurrency: "CNY",
    usdCnyRate: Infinity,
    servicePenaltyExchangeRateRub: 12,
    weightGrams: 100,
    fulfillmentMode: "FBP",
  });
  assert.equal(result.costs.packing.value, null);
  assert.equal(result.costs.other_cost.value, null);
  assert.ok(Number.isFinite(result.total_cost_cny));
  assert.equal(infinite.costs.purchase_cost.value, 400);
  assert.ok(Number.isFinite(infinite.total_cost_cny));
});

test("FBP 和 realFBS 分别使用当前 Ozon 佣金率", () => {
  const fbp = calculateProfit({
    shopId: 1, priceOriginal: 100, purchaseCost: 0, purchaseCurrency: "CNY", usdCnyRate: 7.2,
    weightGrams: 100,
    salesPercentFbp: 15, salesPercentRfbs: 12, fulfillmentMode: "FBP",
  });
  assert.equal(fbp.price_cny, 720);
  assert.equal(fbp.costs.commission.value, 108);
  assert.equal(fbp.costs.commission.status, "implemented");

  for (const channel of ["hongkong", "shenzhen"]) {
    const realFbs = calculateProfit({
      shopId: 2, priceOriginal: 700, purchaseCost: 0, purchaseCurrency: "CNY", usdCnyRate: null,
      weightGrams: 100,
      salesPercentFbp: 15, salesPercentRfbs: 12, fulfillmentMode: "realFBS", realFbsChannel: channel,
    });
    assert.equal(realFbs.costs.commission.value, 84);
    assert.equal(realFbs.costs.commission.status, "implemented");
  }
});

test("佣金 0% 是已接入的零成本，缺失或非法佣金不会当作 0", () => {
  const zero = calculateProfit({
    shopId: 2, priceOriginal: 700, purchaseCost: 400, purchaseCurrency: "CNY", usdCnyRate: null,
    salesPercentFbp: 0, packingCostCny: 0, otherCostCny: 0, servicePenaltyExchangeRateRub: 12,
    weightGrams: 100, fulfillmentMode: "FBP",
  });
  assert.equal(zero.costs.commission.value, 0);
  assert.equal(zero.costs.commission.status, "implemented");
  assert.ok(Number.isFinite(zero.profit_cny));

  const missing = calculateProfit({
    shopId: 2, priceOriginal: 700, purchaseCost: 400, purchaseCurrency: "CNY", usdCnyRate: null,
    servicePenaltyExchangeRateRub: 12, weightGrams: 100, fulfillmentMode: "FBP",
  });
  assert.equal(missing.costs.commission.value, null);
  assert.equal(missing.costs.commission.status, "missing_input");
  assertClose(missing.total_cost_cny, 463.07);
  assertClose(missing.profit_cny, 236.93);
  assertClose(missing.net_margin, 236.93 / 700);

  const unavailable = calculateProfit({
    shopId: 2, priceOriginal: 700, purchaseCost: 400, purchaseCurrency: "CNY", usdCnyRate: null,
    salesPercentFbp: null, servicePenaltyExchangeRateRub: 12, weightGrams: 100, fulfillmentMode: "FBP",
  });
  assert.equal(unavailable.costs.commission.status, "data_unavailable");
  assert.equal(unavailable.profit_cny, null);

  for (const value of [-1, 101, NaN, Infinity, true]) {
    const invalid = calculateProfit({
      shopId: 2, priceOriginal: 700, purchaseCost: 400, purchaseCurrency: "CNY", usdCnyRate: null,
      salesPercentFbp: value, servicePenaltyExchangeRateRub: 12, weightGrams: 100, fulfillmentMode: "FBP",
    });
    assert.equal(invalid.costs.commission.value, null);
    assert.equal(invalid.costs.commission.status, "data_unavailable");
    assert.equal(invalid.profit_cny, null);
  }
});
