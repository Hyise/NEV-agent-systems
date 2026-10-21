import { describe, expect, it } from "vitest";
import { formatTimePressure } from "./timePressure";

describe("formatTimePressure", () => {
  it("keeps historical pressure before 2026", () => {
    expect(formatTimePressure("2025-12", 0.375)).toBe("0.375");
  });

  it("shows no time pressure from 2026 onward", () => {
    expect(formatTimePressure("2026-01", 0.8)).toBe("无");
    expect(formatTimePressure("2027-03", 0.2)).toBe("无");
  });
});
