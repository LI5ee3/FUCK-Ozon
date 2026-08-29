import { request, requestJson } from "../../shared/api/client";
import type { PushEventType } from "./types";
import type { ShopId } from "../../shared/types/common";
export {
  maskPushText,
  maskPushUrl,
  pushEventLabel,
  pushSubscriptionsFromResponse,
  pushSubscriptionNumericId,
  pushTypesFromResponse,
  PUSH_EVENT_FALLBACK_TYPES,
  PUSH_EVENT_LABELS,
} from "./utils";

export function getPushTypes(shopId: ShopId): Promise<unknown> {
  return request<unknown>(`/api/ozon/notifications/push-types?shop_id=${shopId}`, { method: "POST" });
}

export function checkPushWebhook(shopId: ShopId, url: string): Promise<unknown> {
  return requestJson<unknown>("/api/ozon/notifications/check", "POST", { shop_id: shopId, url });
}

export function setPushSubscription(shopId: ShopId, url: string, types: PushEventType[]): Promise<unknown> {
  return requestJson<unknown>("/api/ozon/notifications/set", "POST", { shop_id: shopId, url, types });
}

export function listPushSubscriptions(shopId: ShopId): Promise<unknown> {
  return requestJson<unknown>("/api/ozon/notifications/list", "POST", { shop_id: shopId });
}

export function setPushSubscriptionEnabled(shopId: ShopId, id: number, enabled: boolean): Promise<unknown> {
  return requestJson<unknown>("/api/ozon/notifications/enable", "POST", { shop_id: shopId, id, enabled });
}

export function deletePushSubscription(shopId: ShopId, id: number): Promise<unknown> {
  return requestJson<unknown>("/api/ozon/notifications/delete", "POST", { shop_id: shopId, id });
}
