import { describe, expect, it } from "vitest";
import {
  filterDashboardItemsForMode,
  filterDashboardRecordForMode,
  normalizeDashboardMode,
} from "./dashboard-mode";

describe("dashboard lightweight mode helpers", () => {
  it("normalizes legacy aliases to lightweight", () => {
    expect(normalizeDashboardMode("lightweight")).toBe("lightweight");
    expect(normalizeDashboardMode("light")).toBe("lightweight");
    expect(normalizeDashboardMode("legacy")).toBe("lightweight");
    expect(normalizeDashboardMode("full")).toBe("full");
    expect(normalizeDashboardMode("unexpected")).toBe("full");
  });

  it("keeps admin-heavy routes out of lightweight mode", () => {
    const routes = {
      "/sessions": "sessions",
      "/mcp": "mcp",
      "/channels": "channels",
      "/system": "system",
      "/config": "config",
    };

    expect(filterDashboardRecordForMode(routes, "lightweight")).toEqual({
      "/sessions": "sessions",
      "/config": "config",
    });
    expect(filterDashboardRecordForMode(routes, "full")).toBe(routes);
  });

  it("filters nav items by the same lightweight allow-list", () => {
    const nav = [
      { path: "/sessions", label: "Sessions" },
      { path: "/plugins", label: "Plugins" },
      { path: "/mcp", label: "MCP" },
      { path: "/logs", label: "Logs" },
    ];

    expect(filterDashboardItemsForMode(nav, "lightweight")).toEqual([
      { path: "/sessions", label: "Sessions" },
      { path: "/logs", label: "Logs" },
    ]);
  });
});
