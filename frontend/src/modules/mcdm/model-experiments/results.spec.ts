import { describe, expect, it } from "vitest";
import type { ModelExperimentRun } from "./api";
import {
  defaultPredictionModelKey,
  diagnosticCurves,
  predictionModels,
  predictionMonths,
  predictionsFor,
} from "./results";

const run: ModelExperimentRun = {
  id: "run-1",
  status: "completed",
  progress: 1,
  result: {
    split: {
      train: ["2026-01", "2026-02"],
      validation: ["2026-03"],
      test: ["2026-04"],
    },
    models: [
      {
        key: "ridge",
        label: "Ridge 回归",
        status: "completed",
        implementation_version: "1",
        metrics: { RMSE: 0.1, WAPE: 0.2, R2: 0.3, MAE: 0.1 },
        predictions: [
          { month: "2026-03", model: "甲", actual: 0.6, predicted: 0.5 },
          { month: "2026-04", model: "甲", actual: 0.7, predicted: 0.65 },
        ],
        metadata: {},
      },
      {
        key: "beast_mcdm",
        label: "BEAST-MCDM",
        status: "completed",
        implementation_version: "1",
        metrics: { RMSE: 0.1, WAPE: 0.2, R2: 0.3, MAE: 0.1 },
        predictions: [
          { month: "2026-04", model: "甲", actual: 0.6, predicted: 0.55 },
          { month: "2026-04", model: "乙", actual: 0.4, predicted: 0.45 },
        ],
        metadata: {
          diagnostic_curves: {
            weights: [{ month: "2026-04", pressure: 0, values: { 空间: 0.5 } }],
            rationality: [
              { month: "2026-04", pressure: 0, values: { 空间: 0.4 } },
            ],
          },
        },
      },
    ],
  },
};

describe("model experiment result selectors", () => {
  it("prefers BEAST and keeps each model's prediction months separate", () => {
    expect(predictionModels(run).map((model) => model.key)).toEqual([
      "ridge",
      "beast_mcdm",
    ]);
    expect(defaultPredictionModelKey(run)).toBe("beast_mcdm");
    expect(predictionMonths(run, "beast_mcdm")).toEqual(["2026-04"]);
    expect(predictionsFor(run, "beast_mcdm", "2026-04")).toHaveLength(2);
    expect(predictionsFor(run, "beast_mcdm", "2026-03")).toEqual([]);
    expect(predictionMonths(run, "ridge")).toEqual(["2026-03", "2026-04"]);
    expect(predictionsFor(run, "ridge", "2026-03")).toEqual([
      { month: "2026-03", model: "甲", actual: 0.6, predicted: 0.5 },
    ]);
  });

  it("returns BEAST diagnostics and treats legacy runs as unsupported", () => {
    expect(diagnosticCurves(run, "weights")).toEqual([
      { month: "2026-04", pressure: 0, values: { 空间: 0.5 } },
    ]);
    const legacy = structuredClone(run);
    legacy.result!.models[1].metadata = {};
    expect(diagnosticCurves(legacy, "rationality")).toEqual([]);
  });
});
