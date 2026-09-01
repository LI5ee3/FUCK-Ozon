import test from "node:test";
import assert from "node:assert/strict";
import {
  calculateCrossBorderShippingCny,
  calculateHongKongCrossBorderShippingCny,
} from "../frontend/src/shared/utils/shipping-cost.ts";

function assertClose(actual, expected) {
  assert.ok(Math.abs(actual - expected) < 1e-10, `${actual} is not close to ${expected}`);
}

test("深圳跨境运费按店铺售价和重量分档", () => {
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

  const fbpShipping = calculateCrossBorderShippingCny(2, 700, 100);
  const realFbsShenzhenShipping = calculateCrossBorderShippingCny(2, 700, 100);
  assert.deepEqual(realFbsShenzhenShipping, fbpShipping);
});

test("深圳跨境运费缺失或非法输入返回 missing_input", () => {
  for (const values of [
    [1, null, 100], [1, 10, null], [1, 10, undefined], [1, 10, ""],
    [1, 10, 0], [1, 10, -1], [1, 10, "invalid"], [1, 10, Number.NaN],
    [1, 10, Number.POSITIVE_INFINITY], [1, 10, true], [3, 10, 100],
  ]) {
    assert.equal(calculateCrossBorderShippingCny(...values).status, "missing_input");
  }
});

test("香港跨境运费按实重或体积重并按100g向上计费", () => {
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
  assertClose(calculateHongKongCrossBorderShippingCny(400, 20, 20, 20).value, 57.4);
});

test("香港跨境运费严格执行尺寸重量限制并区分缺失输入", () => {
  assert.equal(calculateHongKongCrossBorderShippingCny(400, 150, 100, 50).status, "implemented");
  assert.equal(calculateHongKongCrossBorderShippingCny(400, 150.01, 100, 49).status, "data_unavailable");
  assert.equal(calculateHongKongCrossBorderShippingCny(400, 150, 100, 59.999).status, "implemented");
  assert.equal(calculateHongKongCrossBorderShippingCny(400, 150, 100, 60).status, "data_unavailable");
  assert.equal(calculateHongKongCrossBorderShippingCny(25000, 20, 20, 20).status, "implemented");
  assert.equal(calculateHongKongCrossBorderShippingCny(25000.01, 20, 20, 20).status, "data_unavailable");

  for (const values of [
    [null, 20, 20, 20], [undefined, 20, 20, 20], [400, null, 20, 20],
    [400, 20, null, 20], [400, 20, 20, null], [0, 20, 20, 20],
    [-1, 20, 20, 20], [400, 0, 20, 20], [400, 20, 20, "invalid"],
    [400, 20, 20, Number.NaN], [400, 20, 20, Number.POSITIVE_INFINITY],
  ]) {
    assert.equal(calculateHongKongCrossBorderShippingCny(...values).status, "missing_input");
  }
});
