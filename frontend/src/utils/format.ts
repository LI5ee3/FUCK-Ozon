import type { GmvSummary } from "../types/api";

export function formatNumber(value: number | null | undefined, digits = 2): string {
  const numeric = Number(value ?? 0);
  return (Number.isFinite(numeric) ? numeric : 0).toLocaleString("zh-CN", {
    maximumFractionDigits: digits,
  });
}

export function formatInteger(value: number | null | undefined): string {
  return formatNumber(value, 0);
}

export function formatPercent(value: number | null | undefined): string {
  return `${(Number(value ?? 0) * 100).toFixed(2)}%`;
}

export function formatMoney(amount: number | null | undefined, currency: string): string {
  if (amount == null) return "金额暂无";
  const number = formatNumber(amount);
  if (currency === "CNY") return `¥${number}`;
  if (currency === "USD") return `$${number}`;
  return currency ? `${number} ${currency}` : number;
}

export function formatGmvAmount(gmv: GmvSummary | null | undefined): string {
  return gmv ? formatMoney(gmv.amount, gmv.currency) : "金额暂无";
}

export function formatGmv(gmv: GmvSummary | null | undefined): string {
  if (!gmv) return "GMV：—";
  if (gmv.missing_rate_orders) {
    return `可折算GMV：¥${formatNumber(gmv.amount)}｜缺少汇率：${formatInteger(gmv.missing_rate_orders)}单`;
  }
  return `GMV：${formatMoney(gmv.amount, gmv.currency)}`;
}

export function formatHours(value: number | null | undefined): string {
  if (value == null) return "暂无";
  return `${formatNumber(value, 1)} 小时 / ${formatNumber(value / 24, 1)} 天`;
}

export function formatBeijingDateTime(value: string | null | undefined): string {
  if (!value) return "暂无";
  if (value.length === 10) return value;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "暂无";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date).replaceAll("/", "-");
}
