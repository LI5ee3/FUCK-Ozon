import { request, requestJson } from "../../shared/api/client";
import type { DingTalkSettings, DingTalkSettingsUpdate } from "./types";

export function getDingTalkSettings(): Promise<DingTalkSettings> {
  return request<DingTalkSettings>("/api/dingtalk/settings");
}

export function updateDingTalkSettings(payload: DingTalkSettingsUpdate): Promise<DingTalkSettings> {
  return requestJson<DingTalkSettings>("/api/dingtalk/settings", "PUT", payload);
}
