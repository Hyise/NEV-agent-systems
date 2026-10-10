import { api } from "../api";

export interface ReviewSource { series_id: string; series_name: string; review_count: number }
export interface AnalysisJob { id: string; job_type?: "criteria_discovery" | "review_annotation"; status: string; processed_count?: number; total_count?: number; success_count?: number; failed_count?: number; input_tokens?: number; output_tokens?: number }
export interface ProposalCriterion { name: string; labels: string[]; similar_terms: string[]; basis: string; evidence: string[] }
export interface CriteriaProposal { job_id: string; proposal: { criteria: ProposalCriterion[] } }
export interface AnnotationRow { annotation_id?: string; review_id: string; series_id: string; series_name: string; status: string; annotation_count: number; analysis_text?: string; result?: { annotations: Array<{ criterion: string; label: string; evidence: string[]; basis: string }>; unmatched_evidence: string[] } }
export interface PageResult<T> { rows: T[]; total: number; page: number; page_size: number }

const base = (projectId: string) => `/projects/${encodeURIComponent(projectId)}/review-analysis`;

export function createReviewAnalysisApi(fetcher = api) {
  const request = <T>(path: string, options?: RequestInit) => fetcher<T>(path, options);
  return {
    listSources: (projectId: string, query = "") => request<PageResult<ReviewSource>>(`${base(projectId)}/sources?query=${encodeURIComponent(query)}`),
    listJobs: (projectId: string) => request<PageResult<AnalysisJob>>(`${base(projectId)}/jobs`),
    createDiscovery: (projectId: string, body: unknown) => request<AnalysisJob>(`${base(projectId)}/discovery-jobs`, { method: "POST", body: JSON.stringify(body) }),
    createAnnotation: (projectId: string, body: unknown) => request<AnalysisJob>(`${base(projectId)}/annotation-jobs`, { method: "POST", body: JSON.stringify(body) }),
    controlJob: (projectId: string, jobId: string, action: string) => request<AnalysisJob>(`${base(projectId)}/jobs/${jobId}/${action}`, { method: "POST" }),
    getProposal: (projectId: string, jobId: string) => request<CriteriaProposal>(`${base(projectId)}/jobs/${jobId}/proposal`),
    applyProposal: (projectId: string, jobId: string, revision: number, criteria: ProposalCriterion[]) => request(`${base(projectId)}/jobs/${jobId}/proposal/apply`, { method: "POST", body: JSON.stringify({ revision, criteria }) }),
    listAnnotations: (projectId: string, params: Record<string, string>) => request<PageResult<AnnotationRow>>(`${base(projectId)}/annotations?${new URLSearchParams(params)}`),
    getAnnotation: (projectId: string, id: string) => request<AnnotationRow>(`${base(projectId)}/annotations/${id}`),
  };
}

export type ReviewAnalysisApi = ReturnType<typeof createReviewAnalysisApi>;

