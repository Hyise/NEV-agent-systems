import { describe, expect, it } from "vitest";
import { METRIC_GUIDANCE, MODEL_GUIDANCE, modelGuidance } from "./guidance";

describe("model experiment guidance", () => {
  it("explains every executable model with a usable summary and caveat", () => {
    const modelKeys = [
      "ridge",
      "random_forest",
      "xgboost",
      "lightgbm",
      "beast_mcdm",
    ];

    expect(Object.keys(MODEL_GUIDANCE).sort()).toEqual(modelKeys.sort());
    for (const key of modelKeys) {
      expect(modelGuidance(key)).toMatchObject({
        summary: expect.any(String),
        principle: expect.any(String),
        value: expect.any(String),
        caution: expect.any(String),
      });
      expect(modelGuidance(key).summary.length).toBeGreaterThan(10);
      expect(modelGuidance(key).caution.length).toBeGreaterThan(10);
    }
  });

  it("returns neutral guidance when the backend adds an unknown model", () => {
    expect(modelGuidance("future_model").summary).toBe(
      "当前模型由运行服务提供，请结合实现版本与测试指标复核。",
    );
  });

  it("defines the interpretation order and direction of all result metrics", () => {
    expect(
      METRIC_GUIDANCE.map(({ key, direction }) => ({ key, direction })),
    ).toEqual([
      { key: "R2", direction: "越高越好" },
      { key: "WAPE", direction: "越低越好" },
      { key: "RMSE", direction: "越低越好" },
      { key: "MAE", direction: "越低越好" },
    ]);
    expect(METRIC_GUIDANCE.find(({ key }) => key === "R2")?.caution).toContain(
      "劣于测试集均值基准",
    );
    expect(
      METRIC_GUIDANCE.find(({ key }) => key === "WAPE")?.meaning,
    ).toContain("百分比");
    expect(
      METRIC_GUIDANCE.find(({ key }) => key === "RMSE")?.meaning,
    ).toContain("较大误差");
    expect(METRIC_GUIDANCE.find(({ key }) => key === "MAE")?.meaning).toContain(
      "平均绝对偏差",
    );
  });
});
