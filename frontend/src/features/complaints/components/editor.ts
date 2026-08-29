import { formatBeijingDateTime } from "../../../shared/utils/format";
import type { ComplaintDeadlineStatus } from "../types";

export type BoolChoice = "" | "true" | "false";

export const booleanOptions = [
  { label: "未填写", value: "" },
  { label: "是", value: "true" },
  { label: "否", value: "false" },
];

export function formatBeijingDateTimeInput(value: string | Date | null | undefined): string {
  if (!value) return "";
  const text = formatBeijingDateTime(value instanceof Date ? value.toISOString() : value);
  return text === "暂无" ? "" : text.replace(" ", "T");
}

export function beijingInputToUtc(value: string): string {
  if (!value) return "";
  const date = new Date(`${value}:00+08:00`);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

export function boolChoice(value: number | null | undefined): BoolChoice {
  return value == null ? "" : String(Boolean(value)) as BoolChoice;
}

export function nullableBool(value: BoolChoice): boolean | null {
  return value === "" ? null : value === "true";
}

export function numberOrNull(value: string | number | null | undefined): number | null {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatConvertedMoney(amount: string | null | undefined, currency: string | null | undefined): string {
  const numeric = Number(amount);
  return Number.isFinite(numeric) ? `${numeric.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency || ""}` : "—";
}

function sameAmount(left: number | null, right: string | number | null | undefined): boolean {
  if (left == null) return right == null || right === "";
  return right != null && right !== "" && Number(left) === Number(right);
}

function sameDateTimeInput(input: string, original: string | null | undefined): boolean {
  if (!input) return !original;
  if (!original) return false;
  const left = Date.parse(beijingInputToUtc(input));
  const right = Date.parse(original);
  return Number.isFinite(left) && Number.isFinite(right) && left === right;
}

export function compensationPreview(
  amount: number | null,
  time: string,
  originalAmount: string | number | null | undefined,
  originalTime: string | null | undefined,
  missingRate: boolean | undefined,
  target: string | null | undefined,
  converted: string | null | undefined,
  rates: Record<string, string> | undefined,
  source: string,
): string {
  if (amount == null) return "折算金额：—";
  if (!sameAmount(amount, originalAmount) || !sameDateTimeInput(time, originalTime)) return "保存后按赔偿时点重新计算";
  if (missingRate) return "缺少赔偿时点汇率";
  if (!converted || !target) return "折算金额：—";
  if (source === target) return `折算金额：${formatConvertedMoney(converted, target)}\n店铺币种相同，无需折算`;
  const rateText = Object.entries(rates || {}).map(([key, value]) => `${key.replace("_", "/")} ${value}`).join("｜");
  return `折算金额：${formatConvertedMoney(converted, target)}${rateText ? `\n采用基础汇率：${rateText}` : ""}`;
}

const deadlineLabels: Partial<Record<ComplaintDeadlineStatus, string>> = {
  overdue: "已逾期",
  due_today: "今日截止",
  due_soon: "即将截止",
};

export function deadlineText(row: { complaint_deadline: string | null; complaint_deadline_status: ComplaintDeadlineStatus }): string {
  return `投诉截止：${row.complaint_deadline || "—"}${deadlineLabels[row.complaint_deadline_status] ? ` · ${deadlineLabels[row.complaint_deadline_status]}` : ""}`;
}
