import type { ShopId } from "../../shared/types/common";

export type PushEventType = string;

export interface PushSubscription {
  id: number | string | null;
  url: string;
  enabled: boolean;
  types: PushEventType[];
  createdAt: string | null;
  updatedAt: string | null;
  error: string;
}

export type PushCheckStatus = "idle" | "loading" | "success" | "error";

export interface PushCheckState {
  status: PushCheckStatus;
  message: string;
}

export interface PushShopState {
  shopId: ShopId;
  loading: boolean;
  apiAvailable: boolean;
  listReady: boolean;
  types: PushEventType[];
  typesFresh: boolean;
  subscriptions: PushSubscription[];
  typeError: string;
  listError: string;
  selectedTypes: PushEventType[];
  urlDraft: string;
  setting: boolean;
  setError: string;
  enableBusyIds: string[];
  enableError: string;
  deletingIds: string[];
  deleteError: string;
  check: PushCheckState;
}
