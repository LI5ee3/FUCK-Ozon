export type DingTalkRunStatus = "sending" | "success" | "failed";

export interface DingTalkLastRun {
  stats_date: string;
  status: string;
  attempted_at: string;
  sent_at: string | null;
  error: string | null;
}

export interface DingTalkSettings {
  id: number;
  daily_enabled: boolean;
  push_time: string;
  weekdays: number[];
  configured: boolean;
  last_run: DingTalkLastRun | null;
  next_push_at: string | null;
}

export interface DingTalkSettingsUpdate {
  daily_enabled: boolean;
  push_time: string;
  weekdays: number[];
}
