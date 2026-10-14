import { describe, expect, it } from "vitest";
import { decodeReviewImport, parseReviewImportText } from "./importFile";

describe("review import file parsing", () => {
  it("rejects invalid UTF-8 instead of replacing source bytes", () => {
    expect(() => decodeReviewImport(new Uint8Array([0xff]))).toThrow("UTF-8");
  });

  it("reports the physical JSONL line containing invalid JSON", () => {
    const source = ['{"series_id":"1"}', "", '{"series_id":}'].join("\n");

    expect(() => parseReviewImportText(source)).toThrow("第 3 行");
  });
});
