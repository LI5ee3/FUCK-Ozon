import { describe, expect, it } from "vitest";
import { queryMatches, shopSelectionFromQuery } from "./query";

describe("query helpers", () => {
  it("requires an exact query match and keeps the first array value", () => {
    expect(queryMatches({ shop_id: "1", from: "2026-08-01" }, { shop_id: "1", from: "2026-08-01" })).toBe(true);
    expect(queryMatches({ shop_id: "1" }, { shop_id: "1", from: "2026-08-01" })).toBe(false);
    expect(queryMatches({ shop_id: "1", extra: "x" }, { shop_id: "1" })).toBe(false);
    expect(queryMatches({ shop_id: ["1", "2"] }, { shop_id: "1" })).toBe(true);
  });

  it("falls back for an invalid shop selection", () => {
    expect(shopSelectionFromQuery({ shop_id: "2" }, 0)).toBe(2);
    expect(shopSelectionFromQuery({ shop_id: "9" }, 1)).toBe(1);
  });
});
