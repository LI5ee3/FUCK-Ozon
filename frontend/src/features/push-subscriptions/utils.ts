import type { PushEventType, PushSubscription } from "./types";

export const PUSH_EVENT_FALLBACK_TYPES: PushEventType[] = [
  "TYPE_NEW_POSTING",
  "TYPE_POSTING_CANCELLED",
  "TYPE_STATE_CHANGED",
  "TYPE_FBO_POSTING_NEW",
  "TYPE_FBO_POSTING_CANCELLED",
  "TYPE_FBO_POSTING_STATE_CHANGED",
  "TYPE_STOCKS_CHANGED",
  "TYPE_FBO_STOCKS_CHANGED",
  "TYPE_ORDER_NEW",
  "TYPE_ORDER_CANCELLED",
  "TYPE_ORDER_STATE_CHANGED",
];

export const PUSH_EVENT_LABELS: Record<string, string> = {
  TYPE_NEW_POSTING: "新建 FBS 货件",
  TYPE_POSTING_CANCELLED: "FBS 货件取消",
  TYPE_STATE_CHANGED: "FBS 货件状态变化",
  TYPE_FBO_POSTING_NEW: "新建 FBO 货件",
  TYPE_FBO_POSTING_CANCELLED: "FBO 货件取消",
  TYPE_FBO_POSTING_STATE_CHANGED: "FBO 货件状态变化",
  TYPE_STOCKS_CHANGED: "FBS 库存变化",
  TYPE_FBO_STOCKS_CHANGED: "FBO 库存变化",
  TYPE_ORDER_NEW: "新建订单",
  TYPE_ORDER_CANCELLED: "订单取消",
  TYPE_ORDER_STATE_CHANGED: "订单状态变化",
};

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function responseArray(response: unknown, fields: string[]): unknown[] {
  if (Array.isArray(response)) return response;
  if (!isObject(response)) return [];
  for (const field of fields) {
    if (Array.isArray(response[field])) return response[field];
  }
  if (!isObject(response.result)) return [];
  for (const field of fields) {
    if (Array.isArray(response.result[field])) return response.result[field];
  }
  return [];
}

export function pushTypesFromResponse(response: unknown): PushEventType[] {
  return responseArray(response, ["types"]).flatMap((value) => {
    if (typeof value === "string" && value) return [value];
    if (isObject(value) && typeof value.type === "string" && value.type) return [value.type];
    return [];
  });
}

function asId(value: unknown): PushSubscription["id"] {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) return value;
  return null;
}

function asText(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  return typeof value === "string" ? value : String(value);
}

function asError(row: JsonObject): string {
  const value = row.error || row.last_error;
  return value ? String(value) : "";
}

function asBoolean(value: unknown): boolean {
  return value === true || value === 1 || value === "1" || value === "true";
}

export function pushSubscriptionsFromResponse(response: unknown): PushSubscription[] {
  return responseArray(response, ["urls", "notifications"]).flatMap((value) => {
    if (!isObject(value)) return [];
    const id = asId(value.id ?? value.notification_id);
    const url = value.url == null ? "" : String(value.url);
    if (id === null && !url) return [];
    return [{
      id,
      url,
      enabled: asBoolean(value.enabled ?? value.is_enabled),
      types: pushTypesFromResponse({ types: value.types }),
      createdAt: asText(value.created_at),
      updatedAt: asText(value.updated_at),
      error: asError(value),
    }];
  });
}

export function maskPushUrl(value: string | null | undefined): string {
  const raw = String(value ?? "").trim();
  if (!raw) return "暂无";
  try {
    const url = new URL(raw);
    const parts = url.pathname.split("/");
    const marker = parts.findIndex((part, index) => part === "ozon" && Boolean(parts[index + 1]));
    if (marker < 0) return "已配置（地址格式未解析）";
    parts[marker + 1] = "***";
    url.pathname = parts.join("/");
    if (url.search) url.search = "?***";
    if (url.hash) url.hash = "#***";
    return url.toString();
  } catch {
    return "已配置（地址格式未解析）";
  }
}

export function maskPushText(value: string): string {
  return value.replace(/https?:\/\/[^\s]+/gi, (candidate) => maskPushUrl(candidate));
}

export function pushEventLabel(type: PushEventType): string {
  return PUSH_EVENT_LABELS[type] ?? "Ozon Push 事件";
}

export function pushSubscriptionNumericId(id: PushSubscription["id"]): number | null {
  if (id === null || (typeof id === "string" && !id.trim())) return null;
  const value = Number(id);
  return Number.isInteger(value) ? value : null;
}
