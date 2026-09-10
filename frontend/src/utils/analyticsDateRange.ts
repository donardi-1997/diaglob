export type AnalyticsQuickRange = "" | "today" | "7d" | "30d" | "month";


function formatLocalDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}


function subtractCalendarDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setDate(result.getDate() - days);
  return result;
}


export function getAnalyticsRangeDates(
  range: AnalyticsQuickRange,
  now: Date = new Date(),
): { from: string; to: string } {
  const today = formatLocalDate(now);

  if (range === "today") {
    return { from: today, to: today };
  }

  if (range === "7d") {
    return {
      from: formatLocalDate(subtractCalendarDays(now, 6)),
      to: today,
    };
  }

  if (range === "30d") {
    return {
      from: formatLocalDate(subtractCalendarDays(now, 29)),
      to: today,
    };
  }

  if (range === "month") {
    const first = new Date(now.getFullYear(), now.getMonth(), 1);
    return { from: formatLocalDate(first), to: today };
  }

  return { from: "", to: "" };
}
