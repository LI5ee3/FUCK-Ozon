import { request, requestJson } from "./client";
import type { DingTalkSettings, DingTalkSettingsUpdate } from "../types/api";

export function getDingTalkSettings(): Promise<DingTalkSettings> {
  return request<DingTalkSettings>("/api/dingtalk/settings");
}

export function updateDingTalkSettings(payload: DingTalkSettingsUpdate): Promise<DingTalkSettings> {
  return requestJson<DingTalkSettings>("/api/dingtalk/settings", "PUT", payload);
}
