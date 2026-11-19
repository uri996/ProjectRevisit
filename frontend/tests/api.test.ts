import { afterEach, expect, it, vi } from "vitest";
import { api } from "../src/api";

afterEach(() => vi.unstubAllGlobals());

it("rejects malformed server responses instead of pretending they are empty successful results", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(new Response("not JSON", { status: 200 }));
  vi.stubGlobal("fetch", fetch);
  await expect(api.projects()).rejects.toThrow("无效响应");
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("preserves sanitized API errors and never retries an explicit paid operation", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ error: "QA_SOURCE_UNKNOWN" }), {
        status: 400,
      }),
    );
  vi.stubGlobal("fetch", fetch);
  await expect(api.ask("synthetic-project", "虚构问题")).rejects.toThrow(
    "QA_SOURCE_UNKNOWN",
  );
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0]?.[0]).toBe(
    "/api/projects/synthetic-project/questions",
  );
});
