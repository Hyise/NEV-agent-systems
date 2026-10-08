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

export interface CreateJobInput {
  mode: "verification" | "production";
  max_series?: number;
  max_pages_per_series?: number;
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
        detail?: string | Array<{ msg: string }>;
      };
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) {
        message = body.detail.map((item) => item.msg).join("；") || message;
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
};
