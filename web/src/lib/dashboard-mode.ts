export type DashboardMode = "full" | "lightweight";

export const LIGHTWEIGHT_DASHBOARD_PATHS = new Set([
  "/",
  "/sessions",
  "/files",
  "/logs",
  "/chat",
  "/config",
  "/env",
  "/docs",
]);

export interface DashboardPathItem {
  path: string;
}

export function normalizeDashboardMode(value: unknown): DashboardMode {
  const raw = String(value ?? "").trim().toLowerCase();
  return raw === "lightweight" || raw === "light" || raw === "legacy"
    ? "lightweight"
    : "full";
}

export function filterDashboardRecordForMode<T>(
  records: Record<string, T>,
  mode: DashboardMode,
): Record<string, T> {
  if (mode === "full") return records;
  return Object.fromEntries(
    Object.entries(records).filter(([path]) =>
      LIGHTWEIGHT_DASHBOARD_PATHS.has(path),
    ),
  );
}

export function filterDashboardItemsForMode<T extends DashboardPathItem>(
  items: T[],
  mode: DashboardMode,
): T[] {
  if (mode === "full") return items;
  return items.filter((item) => LIGHTWEIGHT_DASHBOARD_PATHS.has(item.path));
}
