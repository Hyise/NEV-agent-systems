import { describe, expect, it } from "vitest";
import { reconcileCurveCriteria, scenarioSourceNote } from "./scenario";

describe("scenario presentation", () => {
  it("replaces unavailable archived criteria with the custom experiment criteria", () => {
    expect(
      reconcileCurveCriteria(
        ["续航与能耗可靠性", "成本效益与全周期价值"],
        ["空间", "续航", "智能化", "成本"],
      ),
    ).toEqual(["空间", "续航", "智能化"]);
    expect(
      reconcileCurveCriteria(["空间", "不存在", "续航"], ["空间", "续航"]),
    ).toEqual(["空间", "续航"]);
  });

  it("keeps preset archive provenance separate from custom experiment wording", () => {
    expect(scenarioSourceNote(true, "weights")).toContain("效用范围归一化");
    expect(scenarioSourceNote(true, "weights")).toContain("原研究后处理报表");
    expect(scenarioSourceNote(false, "weights")).toContain("所选BEAST实验");
    expect(scenarioSourceNote(false, "rationality")).toContain(
      "期望效用项与心理抽样项",
    );
  });
});
