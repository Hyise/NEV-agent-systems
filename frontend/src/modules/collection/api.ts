export type CollectionJobStatus =
  | "queued"
  | "discovering"
  | "collecting"
  | "paused"
  | "completed"
  | "stopped"
  | "partial_failed";

export interface CollectionJob {
  id: string;
  mode: "verification" | "production";
  source_url: string;
  max_series: number;
  max_pages_per_series: number | null;
  request_delay_min_seconds: number;
  request_delay_max_seconds: number;
  series_delay_min_seconds: number;
  series_delay_max_seconds: number;
  status: CollectionJobStatus;
  resume_status: CollectionJobStatus | null;
  control_requested: "pause" | "stop" | null;
  current_series_index: number;
  current_series_id: string | null;
  current_series_name: string | null;
  current_page: number;
  discovered_count: number;
  saved_count: number;
  duplicate_count: number;
  failed_count: number;
  skipped_count: number;
  last_success_at: string | null;
  last_error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface CollectionOverview {
  series_count: number;
  review_count: number;
  pending_errors: number;
  active_job: CollectionJob | null;
}

export interface CollectionEvent {
  id: number;
  job_id: string;
  series_id: string | null;
  event_type: string;
  error_class: string | null;
  message: string;
  details: string | null;
  retryable: boolean;
  created_at: string;
}

export interface CollectionJobDetail extends CollectionJob {
  events: CollectionEvent[];
}

export interface Page<T> {
  rows: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface SeriesRow {
  platform: "autohome";
  series_id: string;
  series_name: string;
  series_url: string;
  review_url: string;
  discovery_rank: number;
  first_discovered_at: string;
  last_confirmed_at: string;
  comment_count: number;
}

export interface ReviewSummary {
  platform: "autohome";
  review_id: string;
  series_id: string;
  series_name: string;
  source_url: string;
  content_hash: string;
  first_collected_at: string;
  last_confirmed_at: string;
}

export interface ReviewDetail extends ReviewSummary {
  original_review: Record<string, unknown>;
}

export type CatalogRunStatus =
  | "queued"
  | "discovering"
  | "publishing"
  | "completed"
  | "completed_short"
  | "cancelling"
  | "cancelled"
  | "failed";

export interface CatalogRun {
  id: string;
  batch_id: string;
  status: CatalogRunStatus;
  target_unique_series: number;
  scanned_count: number;
  unique_count: number;
  skipped_count: number;
  current_page: number;
  error_code: string | null;
  error_message: string | null;
  source_exhausted: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface CatalogStatus {
  active_batch_id: string | null;
  series_count: number;
  published_at: string | null;
  source_url: string;
  source_exhausted: boolean;
  active_run: CatalogRun | null;
}

export interface CatalogSeriesRow {
  batch_id: string;
  platform: "autohome";
  series_id: string;
  series_name: string;
  series_url: string;
  review_url: string;
  discovery_rank: number;
  discovered_at: string;
  published_at: string;
}

export interface CatalogSelectionResult {
  batch_id: string | null;
  series_ids: string[];
  total: number;
}

export interface CreateJobInput {
  mode: "verification" | "production";
  selected_series_ids: string[];
  request_delay_min_seconds?: number;
  request_delay_max_seconds?: number;
  series_delay_min_seconds?: number;
  series_delay_max_seconds?: number;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch("/api/collection" + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = (await response.json()) as {
        detail?:
          | string
          | Array<{ msg: string }>
          | { message?: string; invalid_series_ids?: string[] };
      };
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) {
        message = body.detail.map((item) => item.msg).join("；") || message;
      } else if (body.detail && typeof body.detail === "object") {
        const invalid = body.detail.invalid_series_ids ?? [];
        message = body.detail.message || message;
        if (invalid.length) message += `（${invalid.join("、")}）`;
      }
    } catch {
      // Retain the status-based fallback when the response is not JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export interface CollectionApi {
  getOverview(): Promise<CollectionOverview>;
  listJobs(page?: number, pageSize?: number): Promise<Page<CollectionJob>>;
  getJob(jobId: string): Promise<CollectionJobDetail>;
  createJob(input: CreateJobInput): Promise<CollectionJob>;
  pauseJob(jobId: string): Promise<CollectionJob>;
  resumeJob(jobId: string): Promise<CollectionJob>;
  stopJob(jobId: string): Promise<CollectionJob>;
  listSeries(
    search?: string,
    page?: number,
    pageSize?: number,
  ): Promise<Page<SeriesRow>>;
  listReviews(
    seriesId?: string,
    page?: number,
    pageSize?: number,
  ): Promise<Page<ReviewSummary>>;
  getReview(reviewId: string): Promise<ReviewDetail>;
  getCatalogStatus(): Promise<CatalogStatus>;
  listCatalog(
    query?: string,
    page?: number,
    pageSize?: number,
  ): Promise<Page<CatalogSeriesRow>>;
  listCatalogSelection(query?: string): Promise<CatalogSelectionResult>;
  startCatalogDiscovery(): Promise<CatalogRun>;
  getCatalogRun(runId: string): Promise<CatalogRun>;
  cancelCatalogDiscovery(runId: string): Promise<CatalogRun>;
}

export const collectionApi: CollectionApi = {
  getOverview: () => request("/overview"),
  listJobs: (page = 1, pageSize = 20) =>
    request(`/jobs?page=${page}&page_size=${pageSize}`),
  getJob: (jobId) => request(`/jobs/${encodeURIComponent(jobId)}`),
  createJob: (input) => post("/jobs", input),
  pauseJob: (jobId) => post(`/jobs/${encodeURIComponent(jobId)}/pause`),
  resumeJob: (jobId) => post(`/jobs/${encodeURIComponent(jobId)}/resume`),
  stopJob: (jobId) => post(`/jobs/${encodeURIComponent(jobId)}/stop`),
  listSeries: (search = "", page = 1, pageSize = 20) =>
    request(
      `/series?search=${encodeURIComponent(search)}&page=${page}&page_size=${pageSize}`,
    ),
  listReviews: (seriesId, page = 1, pageSize = 20) =>
    request(
      `/reviews?${seriesId ? `series_id=${encodeURIComponent(seriesId)}&` : ""}page=${page}&page_size=${pageSize}`,
    ),
  getReview: (reviewId) => request(`/reviews/${encodeURIComponent(reviewId)}`),
  getCatalogStatus: () => request("/catalog/status"),
  listCatalog: (query = "", page = 1, pageSize = 20) =>
    request(
      `/catalog?query=${encodeURIComponent(query)}&page=${page}&page_size=${pageSize}`,
    ),
  listCatalogSelection: (query = "") =>
    request(`/catalog/selection?query=${encodeURIComponent(query)}`),
  startCatalogDiscovery: () => post("/catalog/discover"),
  getCatalogRun: (runId) =>
    request(`/catalog/discover/${encodeURIComponent(runId)}`),
  cancelCatalogDiscovery: (runId) =>
    post(`/catalog/discover/${encodeURIComponent(runId)}/cancel`),
};
