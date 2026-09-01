import { beforeEach, describe, expect, it, vi } from "vitest";
import { getErpCostImportHistory, importErpCosts } from "./api";

const request = vi.hoisted(() => vi.fn());
vi.mock("../../shared/api/client", () => ({ request }));

describe("ERP cost import API", () => {
  beforeEach(() => {
    request.mockReset().mockResolvedValue([]);
  });

  it("posts the raw XLSX file with an encoded filename", async () => {
    const file = new File(["xlsx"], "马帮 成本.xlsx");
    await importErpCosts(1, file);

    expect(request).toHaveBeenCalledWith(
      "/api/erp-costs/import?shop_id=1",
      expect.objectContaining({
        method: "POST",
        headers: { "X-Filename": encodeURIComponent(file.name) },
        body: file,
      }),
    );
    expect(request.mock.calls[0][1].body).toBe(file);
  });

  it("loads the unpaged ERP import history endpoint", async () => {
    await getErpCostImportHistory();

    expect(request).toHaveBeenCalledWith("/api/erp-costs/imports");
  });
});
