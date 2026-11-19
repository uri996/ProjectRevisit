import { describe, expect, it } from "vitest";
import { formatMessageTime } from "../src/presentation";

describe("browser time display without changing stored UTC", () => {
  it.each([
    [
      "2026-10-27T14:58:01.123456+00:00",
      "Australia/Sydney",
      "2026/10/28 01:58",
    ],
    ["2026-06-30T23:30:00Z", "Australia/Sydney", "2026/07/01 09:30"],
    ["2026-01-01T01:00:00Z", "America/Los_Angeles", "2025/12/31 17:00"],
    ["2026-10-03T15:30:00Z", "Australia/Sydney", "2026/10/04 01:30"],
    ["2026-10-03T16:30:00Z", "Australia/Sydney", "2026/10/04 03:30"],
  ])("handles cross-date and DST conversion: %s", (value, zone, expected) => {
    expect(formatMessageTime(value, zone)).toBe(expected);
  });
  it("defaults to the browser timezone and safely handles invalid timestamps", () => {
    const value = "2026-10-27T14:58:01.123456+00:00";
    expect(formatMessageTime(value)).toBe(
      formatMessageTime(
        value,
        Intl.DateTimeFormat().resolvedOptions().timeZone,
      ),
    );
    expect(value).toBe("2026-10-27T14:58:01.123456+00:00");
    expect(formatMessageTime("invalid")).toBe("时间未知");
  });
});
