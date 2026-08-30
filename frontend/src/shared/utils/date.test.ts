import { describe, expect, it } from "vitest";
import { beijingThreeMonthRange, standardDatePresetRange } from "./date";

describe("standard date ranges", () => {
  const end = "2024-05-31";

  it("keeps the Beijing three-month range and month-end rollover", () => {
    expect(beijingThreeMonthRange(end)).toEqual(["2024-02-29", end]);
  });

  it("builds each standard preset from the supplied end date", () => {
    expect(standardDatePresetRange("today", end)).toEqual([end, end]);
    expect(standardDatePresetRange("3days", end)).toEqual(["2024-05-29", end]);
    expect(standardDatePresetRange("7days", end)).toEqual(["2024-05-25", end]);
    expect(standardDatePresetRange("3months", end)).toEqual(["2024-02-29", end]);
    expect(standardDatePresetRange("all", end)).toEqual(["2020-01-01", end]);
  });
});
