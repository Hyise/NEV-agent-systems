import type {
  ExecutedModelResult,
  ExperimentCurve,
  ModelExperimentRun,
  ModelPrediction,
} from "./api";

export function predictionModels(
  run: ModelExperimentRun | null,
): ExecutedModelResult[] {
  return (run?.result?.models ?? []).filter(
    (model) => model.status === "completed" && model.predictions.length > 0,
  );
}

export function defaultPredictionModelKey(
  run: ModelExperimentRun | null,
): string {
  const models = predictionModels(run);
  return (
    models.find((model) => model.key === "beast_mcdm")?.key ??
    models[0]?.key ??
    ""
  );
}

export function predictionMonths(
  run: ModelExperimentRun | null,
  modelKey: string,
): string[] {
  const model = predictionModels(run).find((item) => item.key === modelKey);
  return [
    ...new Set((model?.predictions ?? []).map((row) => row.month)),
  ].sort();
}

export function predictionsFor(
  run: ModelExperimentRun | null,
  modelKey: string,
  month: string,
): ModelPrediction[] {
  const model = predictionModels(run).find((item) => item.key === modelKey);
  return (model?.predictions ?? [])
    .filter((row) => row.month === month)
    .sort((left, right) => right.actual - left.actual);
}

export function diagnosticCurves(
  run: ModelExperimentRun | null,
  kind: "weights" | "rationality",
): ExperimentCurve[] {
  const beast = run?.result?.models.find(
    (model) => model.key === "beast_mcdm" && model.status === "completed",
  );
  return beast?.metadata.diagnostic_curves?.[kind] ?? [];
}
