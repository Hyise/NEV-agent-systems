export interface Criterion {
  name: string;
  labels: string[];
}
export interface Project {
  id: string;
  name: string;
  mode: "preset" | "custom";
  created_at: string;
}
export interface Schema {
  id: string;
  project_id: string;
  version: number;
  revision: number;
  status: "draft" | "frozen";
  criteria: Criterion[];
}
export interface Curve {
  month: string;
  pressure: number;
  values: Record<string, number>;
}
export interface RecordRow {
  month: string;
  model: string;
  sales: number;
  share: number;
  pressure: number;
  probabilities: Record<string, number[]>;
}
export interface Prediction {
  month: string;
  model: string;
  actual: number;
  predicted: number;
}
export interface Metric {
  model: string;
  RMSE: number;
  WAPE: number;
  R2: number;
}
export interface Overview {
  project: Project;
  schema: Schema;
  months: string[];
  prediction_months: string[];
  stats: { records: number; models: number; months: number; criteria: number };
  dataset: { id: string; name: string; sha256: string } | null;
  source_labels: Record<string, string[]>;
  notes: string[];
  source: { archive_name: string; archive_sha256: string } | null;
}
export interface DataPage {
  rows: RecordRow[];
  total: number;
  month: string | null;
  month_models: number;
  month_total_sales: number;
}
export interface MatrixHandoffBlocker {
  month: string;
  series_id: string;
  series_name: string;
  reasons: string[];
  issues: Array<{ code: string; message: string }>;
}
export interface MatrixHandoff {
  state: "no_job" | "processing" | "blocked" | "ready" | "materialized";
  target_schema_id: string;
  target_schema_version: number;
  target_schema_status: "draft" | "frozen";
  compatibility: "exact" | "fingerprint" | null;
  job: {
    id: string;
    status: string;
    source_schema_id: string;
    source_schema_version: number | null;
  } | null;
  matrix: {
    stats: {
      source_reviews: number;
      groups: number;
      records: number;
      blocked_groups: number;
      missing_date_reviews: number;
      unmentioned_criterion_groups: number;
    };
    failed_reviews: number;
    blocker_counts: Record<string, number>;
    first_blocker: MatrixHandoffBlocker | null;
  } | null;
  dataset: {
    id: string;
    name: string;
    sha256: string;
    record_count: number;
    source_job_id?: string | null;
    source_schema_id?: string | null;
    target_schema_id?: string | null;
  } | null;
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : (body.detail ?? []).map((d: { msg: string }) => d.msg).join("；") ||
            message;
    } catch {
      /* keep HTTP error */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
