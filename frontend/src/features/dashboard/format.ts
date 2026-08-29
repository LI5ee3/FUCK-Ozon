import type { GmvSummary } from "./types";
import { formatInteger, formatMoney, formatNumber } from "../../shared/utils/format";

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
