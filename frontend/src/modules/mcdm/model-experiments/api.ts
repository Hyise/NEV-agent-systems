import { api } from "../api";

export interface ModelCapability {
  key: string;
  label: string;
  available: boolean;
  reason: string | null;
  implementation_version: string;
}

export interface ModelPrediction {
  month: string;
  model: string;
  actual: number;
  predicted: number;
}

export interface ExperimentCurve {
  month: string;
  pressure: number;
  values: Record<string, number>;
}

export interface ExecutedModelMetadata extends Record<string, unknown> {
  diagnostic_curves?: {
    weights: ExperimentCurve[];
    rationality: ExperimentCurve[];
  };
}

export interface ExecutedModelResult {
  key: string;
  label: string;
  status: string;
  implementation_version: string;
  metrics: Record<"RMSE" | "WAPE" | "R2" | "MAE", number>;
  predictions: ModelPrediction[];
  metadata: ExecutedModelMetadata;
}

export interface ModelExperimentRun {
  id: string;
  project_id?: string;
  schema_id?: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  current_model?: string | null;
  error_message?: string | null;
  created_at?: string;
  finished_at?: string | null;
  config?: {
    model_keys: string[];
    validation_months: number;
    test_months: number;
    seed: number;
    simulations: number;
  };
  dataset?: {
    snapshot_sha256: string;
    records: number;
    source: { id?: string; name?: string; sha256?: string };
  };
  result?: {
    split: { train: string[]; validation: string[]; test: string[] };
    models: ExecutedModelResult[];
  } | null;
}

export interface RunPage {
  rows: ModelExperimentRun[];
  total: number;
  page: number;
  page_size: number;
}

const base = (projectId: string) =>
  `/projects/${encodeURIComponent(projectId)}/model-experiments`;

export function createModelExperimentApi(fetcher = api) {
  return {
    capabilities: (projectId: string) =>
      fetcher<ModelCapability[]>(`${base(projectId)}/capabilities`),
    list: (projectId: string, schemaId: string) =>
      fetcher<RunPage>(
        `${base(projectId)}?schema_id=${encodeURIComponent(schemaId)}`,
      ),
    get: (projectId: string, runId: string) =>
      fetcher<ModelExperimentRun>(`${base(projectId)}/${runId}`),
    create: (projectId: string, body: unknown) =>
      fetcher<ModelExperimentRun>(base(projectId), {
        method: "POST",
        body: JSON.stringify(body),
      }),
    cancel: (projectId: string, runId: string) =>
      fetcher<ModelExperimentRun>(`${base(projectId)}/${runId}/cancel`, {
        method: "POST",
      }),
  };
}

export type ModelExperimentApi = ReturnType<typeof createModelExperimentApi>;
