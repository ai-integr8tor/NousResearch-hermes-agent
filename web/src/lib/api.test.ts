import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("api.getStatus", () => {
  it.each([
    ["valid", "valid"],
    ["terminal", "terminal"],
    ["unknown", "unknown"],
    [undefined, "unknown"],
    [null, "unknown"],
    ["unexpected", "unknown"],
    [false, "unknown"],
  ])("normalizes nous_session_valid=%s to %s", async (rawValue, expected) => {
    vi.stubGlobal("window", {});

    const body =
      rawValue === undefined ? {} : { nous_session_valid: rawValue };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify(body), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      ),
    );

    await expect(api.getStatus()).resolves.toMatchObject({
      nous_session_valid: expected,
    });
  });
});

describe("api.getModelOptions", () => {
  it("requests a live model refresh when asked", async () => {
    vi.stubGlobal("window", {});

    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ providers: [] }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.getModelOptions({ refresh: true });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/model/options?refresh=1",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("keeps explicit profile scoping when refreshing", async () => {
    vi.stubGlobal("window", {});

    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ providers: [] }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.getModelOptions({ profile: "default", refresh: true });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/model/options?profile=default&refresh=1",
      expect.objectContaining({ credentials: "include" }),
    );
  });
});
