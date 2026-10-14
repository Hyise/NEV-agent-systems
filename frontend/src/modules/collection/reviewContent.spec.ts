import { describe, expect, it } from "vitest";
import { buildReadableReview } from "./reviewContent";

describe("buildReadableReview", () => {
  it("preserves every original content section in source order without truncation", () => {
    const fullText = `高速行驶时的续航表现${"依然稳定，".repeat(80)}没有省略结尾。`;

    const result = buildReadableReview({
      feeling_summary: "三个月用车总结",
      contents: [
        { structuredname: "满意", content: "空间宽敞，后排乘坐舒适。" },
        { structuredname: "不满意", content: fullText },
        { structuredname: "补充", content: "空间宽敞，后排乘坐舒适。" },
      ],
    });

    expect(result).toEqual({
      summary: "三个月用车总结",
      sections: [
        { label: "满意", content: "空间宽敞，后排乘坐舒适。" },
        { label: "不满意", content: fullText },
        { label: "补充", content: "空间宽敞，后排乘坐舒适。" },
      ],
    });
  });

  it("keeps readable content available when optional labels are missing", () => {
    const result = buildReadableReview({
      contents: [
        { content: "第一段原始评论" },
        null,
        { structuredname: " ", content: "第二段原始评论" },
        { structuredname: "无效项", content: 42 },
      ],
      score: 4.5,
    });

    expect(result).toEqual({
      summary: null,
      sections: [
        { label: "原文 1", content: "第一段原始评论" },
        { label: "原文 3", content: "第二段原始评论" },
      ],
    });
  });
});
