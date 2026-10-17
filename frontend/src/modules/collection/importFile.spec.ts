import { describe, expect, it } from "vitest";
import {
  decodeReviewImport,
  parseReviewImportText,
  prepareReviewImportFiles,
} from "./importFile";

describe("review import file parsing", () => {
  it("rejects invalid UTF-8 instead of replacing source bytes", () => {
    expect(() => decodeReviewImport(new Uint8Array([0xff]))).toThrow("UTF-8");
  });

  it("reports the physical JSONL line containing invalid JSON", () => {
    const source = ['{"series_id":"1"}', "", '{"series_id":}'].join("\n");

    expect(() => parseReviewImportText(source)).toThrow("第 3 行");
  });

  it("keeps supported folder files in relative-path order and skips temporary files", () => {
    const files = [
      {
        name: "b.csv",
        size: 20,
        webkitRelativePath: "评论/b.csv",
      } as File,
      {
        name: "说明.txt",
        size: 10,
        webkitRelativePath: "评论/说明.txt",
      } as File,
      {
        name: "~$a.xlsx",
        size: 10,
        webkitRelativePath: "评论/~$a.xlsx",
      } as File,
      {
        name: "a.xlsx",
        size: 30,
        webkitRelativePath: "评论/a.xlsx",
      } as File,
    ];

    const result = prepareReviewImportFiles(files, { fromDirectory: true });

    expect(result.files.map((file) => file.name)).toEqual(["a.xlsx", "b.csv"]);
    expect(result.skippedCount).toBe(2);
  });

  it("rejects folders containing more than 200 supported files", () => {
    const files = Array.from(
      { length: 201 },
      (_, index) =>
        ({
          name: `${index}.xlsx`,
          size: 10,
          webkitRelativePath: `评论/${index}.xlsx`,
        }) as File,
    );

    expect(() =>
      prepareReviewImportFiles(files, { fromDirectory: true }),
    ).toThrow("200");
  });
});
