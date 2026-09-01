export type ShippingCostStatus = "implemented" | "missing_input" | "data_unavailable";

export interface ShippingCostResult {
  value: number | null;
  status: ShippingCostStatus;
}

type ShippingCostValue = number | string | null | undefined;

function shippingNumber(value: ShippingCostValue): number | null {
  if (value == null || typeof value === "boolean" || (typeof value === "string" && value.trim() === "")) return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

export function calculateCrossBorderShippingCny(
  shopId: number | string | null | undefined,
  priceOriginal: ShippingCostValue,
  weightGrams: ShippingCostValue,
): ShippingCostResult {
  const price = shippingNumber(priceOriginal);
  const weight = shippingNumber(weightGrams);
  if (price === null || weight === null || weight <= 0) {
    return { value: null, status: "missing_input" };
  }

  const shopNumber = Number(shopId);
  let threshold: number;
  let lowBase: number;
  let highBase: number;
  if (shopNumber === 1) {
    if (price < 20) {
      threshold = 500;
      lowBase = 3.37;
      highBase = 25.83;
    } else if (price <= 90) {
      threshold = 2000;
      lowBase = 17.97;
      highBase = 40.44;
    } else {
      threshold = 5000;
      lowBase = 24.71;
      highBase = 69.64;
    }
  } else if (shopNumber === 2) {
    if (price < 150) {
      threshold = 500;
      lowBase = 3.37;
      highBase = 25.83;
    } else if (price <= 650) {
      threshold = 2000;
      lowBase = 17.97;
      highBase = 40.44;
    } else {
      threshold = 5000;
      lowBase = 24.71;
      highBase = 69.64;
    }
  } else {
    return { value: null, status: "missing_input" };
  }

  const lowWeight = weight < threshold;
  const value = (lowWeight ? lowBase : highBase) + (lowWeight ? 0.0505 : 0.0371) * weight;
  return Number.isFinite(value)
    ? { value, status: "implemented" }
    : { value: null, status: "data_unavailable" };
}

export function calculateHongKongCrossBorderShippingCny(
  weightGrams: ShippingCostValue,
  lengthCm: ShippingCostValue,
  widthCm: ShippingCostValue,
  heightCm: ShippingCostValue,
): ShippingCostResult {
  const actualWeight = shippingNumber(weightGrams);
  const length = shippingNumber(lengthCm);
  const width = shippingNumber(widthCm);
  const height = shippingNumber(heightCm);
  if (actualWeight === null || actualWeight <= 0
    || length === null || length <= 0
    || width === null || width <= 0
    || height === null || height <= 0) {
    return { value: null, status: "missing_input" };
  }

  const dimensionSum = length + width + height;
  if (actualWeight > 25000 || Math.max(length, width, height) > 150 || dimensionSum >= 310) {
    return { value: null, status: "data_unavailable" };
  }

  const billableWeight = dimensionSum <= 60 ? actualWeight : length * width * height / 6;
  const value = 19 + Math.ceil(billableWeight / 100) * 9.6;
  return Number.isFinite(value)
    ? { value, status: "implemented" }
    : { value: null, status: "data_unavailable" };
}
