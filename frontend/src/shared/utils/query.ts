import type { LocationQuery, LocationQueryValue } from "vue-router";
import type { ShopSelection } from "../types/common";

export function firstQueryValue(value: LocationQueryValue | LocationQueryValue[] | undefined): string {
  return Array.isArray(value) ? String(value[0] ?? "") : value ?? "";
}

export function queryValue(query: LocationQuery, key: string): string {
  return firstQueryValue(query[key]);
}

export function queryMatches(query: LocationQuery, expected: Record<string, string>): boolean {
  const keys = new Set([...Object.keys(query), ...Object.keys(expected)]);
  return [...keys].every((key) => queryValue(query, key) === (expected[key] ?? ""));
}

export function positiveInteger(value: string, fallback: number): number {
  if (!/^\d+$/.test(value)) return fallback;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : fallback;
}

export function isShopSelection(value: string): value is "0" | "1" | "2" {
  return value === "0" || value === "1" || value === "2";
}

export function shopSelectionFromQuery(query: LocationQuery, fallbackShop: ShopSelection): ShopSelection {
  const value = queryValue(query, "shop_id");
  return isShopSelection(value) ? Number(value) as ShopSelection : fallbackShop;
}
