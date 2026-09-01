import { request } from "../../shared/api/client";
import type { Channel, ShopId, ShopSelection } from "../../shared/types/common";

export type ImportKind = Channel;
export type ExportModule = "orders" | "risk" | "returns" | "complaints";

export interface ImportResult {
  batch_id: number;
  rows: number;
}

export interface ImportHistoryItem {
  id: number;
  shop_id: ShopId;
  kind: ImportKind;
  filename: string;
  imported_at: string;
  row_count: number;
  shop_name: string;
}

export interface ErpCostImportResult {
  batch_id: number;
  rows: number;
  parsed: number;
  inserted: number;
  updated: number;
  unchanged: number;
}

export interface ErpCostImportHistoryItem {
  id: number;
  shop_id: ShopId;
  filename: string;
  row_count: number;
  parsed_count: number;
  inserted_count: number;
  updated_count: number;
  unchanged_count: number;
  imported_at: string;
  shop_name: string;
}

export function getImportHistory(): Promise<ImportHistoryItem[]> {
  return request<ImportHistoryItem[]>("/api/imports");
}

export function importCsv(kind: ImportKind, shopId: ShopId, file: File): Promise<ImportResult> {
  const query = new URLSearchParams({ shop_id: String(shopId) });
  return request<ImportResult>(`/api/import/${kind}?${query}`, {
    method: "POST",
    headers: { "X-Filename": encodeURIComponent(file.name) },
    body: file,
  });
}

export function getErpCostImportHistory(): Promise<ErpCostImportHistoryItem[]> {
  return request<ErpCostImportHistoryItem[]>("/api/erp-costs/imports");
}

export function importErpCosts(shopId: ShopId, file: File): Promise<ErpCostImportResult> {
  const query = new URLSearchParams({ shop_id: String(shopId) });
  return request<ErpCostImportResult>(`/api/erp-costs/import?${query}`, {
    method: "POST",
    headers: { "X-Filename": encodeURIComponent(file.name) },
    body: file,
  });
}

export function buildExportUrl(
  module: ExportModule,
  shopId: ShopSelection,
  dateFrom: string,
  dateTo: string,
): string {
  const query = new URLSearchParams({
    shop_id: String(shopId),
    date_from: dateFrom,
    date_to: dateTo,
  });
  return `/api/export/${module}?${query}`;
}
