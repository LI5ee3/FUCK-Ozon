export type DateRange = [string, string];

function todayInTimeZone(timeZone: string, now: Date): string {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function beijingToday(now = new Date()): string {
  return todayInTimeZone("Asia/Shanghai", now);
}

export function moscowToday(now = new Date()): string {
  return todayInTimeZone("Europe/Moscow", now);
}

export function dateParts(value: string): [number, number, number] {
  const [year, month, day] = value.split("-").map(Number);
  return [year, month, day];
}

export function dateText(year: number, month: number, day: number): string {
  return `${year.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}-${day.toString().padStart(2, "0")}`;
}

export function shiftDays(value: string, days: number): string {
  const [year, month, day] = dateParts(value);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  return dateText(shifted.getUTCFullYear(), shifted.getUTCMonth() + 1, shifted.getUTCDate());
}

export function subtractMonths(value: string, months: number): string {
  const [year, month, day] = dateParts(value);
  const target = new Date(Date.UTC(year, month - 1 - months, 1));
  const lastDay = new Date(Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)).getUTCDate();
  return dateText(target.getUTCFullYear(), target.getUTCMonth() + 1, Math.min(day, lastDay));
}

export function isValidDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = dateParts(value);
  if (year < 1) return false;
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}

export function parseValidDateRange(from: string, to: string, fallback: DateRange): DateRange {
  return isValidDate(from) && isValidDate(to) && from <= to ? [from, to] : [...fallback];
}
