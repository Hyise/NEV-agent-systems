import { api } from "../api";

export interface ReviewSource {
  series_id: string;
  series_name: string;
  review_count: number;
}
export interface AnalysisJob {
  id: string;
  job_type?: "criteria_discovery" | "review_annotation";
  status: string;
  processed_count?: number;
  total_count?: number;
  success_count?: number;
  failed_count?: number;
  input_tokens?: number;
  output_tokens?: number;
}
export interface ProposalCriterion {
  name: string;
  labels: string[];
  similar_terms: string[];
  basis: string;
  evidence: string[];
}
export interface CriteriaProposal {
  job_id: string;
  proposal: { criteria: ProposalCriterion[] };
  source_deleted_count?: number;
}
export interface AnnotationRow {
  job_id: string;
  snapshot_id?: string;
  annotation_id?: string;
  review_id: string;
  series_id: string;
  series_name: string;
  status: string;
  annotation_count: number;
  annotated_at?: string;
  analysis_text?: string;
  source_deleted?: boolean;
  result?: {
    annotations: Array<{
      criterion: string;
      label: string;
      evidence: string[];
      basis: string;
    }>;
    unmatched_evidence: string[];
  };
}
export interface PageResult<T> {
  rows: T[];
  total: number;
  page: number;
  page_size: number;
}
export interface AnnotationSummary {
  annotated_reviews: number;
  criteria: Record<string, number>;
  labels: Record<string, number>;
}
export interface MatrixBlocker {
  month: string;
  series_id: string;
  series_name: string;
  reasons: string[];
}
export interface MatrixPreview {
  job_id: string;
  project_id: string;
  schema_id: string;
  failed_reviews: number;
  records: Array<Record<string, unknown>>;
  blockers: MatrixBlocker[];
  stats: {
    source_reviews: number;
    groups: number;
    records: number;
    blocked_groups: number;
    missing_date_reviews: number;
  };
}
export interface GeneratedDataset {
  id: string;
  name: string;
  records: number;
  sha256: string;
  created_at: string;
}

const base = (projectId: string) =>
  `/projects/${encodeURIComponent(projectId)}/review-analysis`;

export function createReviewAnalysisApi(fetcher = api) {
  const request = <T>(path: string, options?: RequestInit) =>
    fetcher<T>(path, options);
  return {
    listSources: (projectId: string, query = "", page = 1) =>
      request<PageResult<ReviewSource>>(
        `${base(projectId)}/sources?${new URLSearchParams({ query, page: String(page), page_size: "20" })}`,
      ),
    listJobs: (projectId: string) =>
      request<PageResult<AnalysisJob>>(`${base(projectId)}/jobs`),
    createDiscovery: (projectId: string, body: unknown) =>
      request<AnalysisJob>(`${base(projectId)}/discovery-jobs`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    createAnnotation: (projectId: string, body: unknown) =>
      request<AnalysisJob>(`${base(projectId)}/annotation-jobs`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    controlJob: (projectId: string, jobId: string, action: string) =>
      request<AnalysisJob>(`${base(projectId)}/jobs/${jobId}/${action}`, {
        method: "POST",
      }),
    getProposal: (projectId: string, jobId: string) =>
      request<CriteriaProposal>(`${base(projectId)}/jobs/${jobId}/proposal`),
    applyProposal: (
      projectId: string,
      jobId: string,
      revision: number,
      criteria: ProposalCriterion[],
    ) =>
      request(`${base(projectId)}/jobs/${jobId}/proposal/apply`, {
        method: "POST",
        body: JSON.stringify({ revision, criteria }),
      }),
    listAnnotations: (projectId: string, params: Record<string, string>) =>
      request<PageResult<AnnotationRow>>(
        `${base(projectId)}/annotations?${new URLSearchParams(params)}`,
      ),
    getAnnotation: (
      projectId: string,
      id: string,
      jobId?: string,
      snapshotId?: string,
    ) =>
      request<AnnotationRow>(
        `${base(projectId)}/annotations/${id}?${new URLSearchParams({
          ...(jobId ? { job_id: jobId } : {}),
          ...(snapshotId ? { snapshot_id: snapshotId } : {}),
        })}`,
      ),
    getSummary: (projectId: string, jobId = "") =>
      request<AnnotationSummary>(
        `${base(projectId)}/summary${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ""}`,
      ),
    getMatrixPreview: (projectId: string, jobId: string) =>
      request<MatrixPreview>(
        `${base(projectId)}/jobs/${encodeURIComponent(jobId)}/matrix-preview`,
      ),
    materializeDataset: (projectId: string, jobId: string) =>
      request<GeneratedDataset>(
        `${base(projectId)}/jobs/${encodeURIComponent(jobId)}/datasets`,
        { method: "POST" },
      ),
  };
}

export type ReviewAnalysisApi = ReturnType<typeof createReviewAnalysisApi>;
