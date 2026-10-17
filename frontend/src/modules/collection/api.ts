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
  deleted_review_skip_count?: number;
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

export type ReviewAssetSourceKind = "autohome" | "manual_import";

export interface ReviewAssetSummary {
  asset_id: string;
  review_id: string;
  series_id: string;
  series_name: string;
  source_kind: ReviewAssetSourceKind;
  platform: string;
  source_url: string | null;
  content_hash: string;
  excerpt: string;
  first_collected_at: string;
  last_confirmed_at: string;
  analysis_enabled: boolean;
  tags: string[];
  note: string;
  revision: number;
  metadata_updated_at: string;
}

export interface ReviewAssetDetail extends ReviewAssetSummary {
  original_review: Record<string, unknown>;
  reference_count: number;
}

export interface ReviewAssetFilters {
  keyword?: string;
  series_id?: string;
  source_kind?: ReviewAssetSourceKind;
  tag?: string;
  analysis_enabled?: boolean;
  page?: number;
  page_size?: number;
}

export interface ReviewAssetMetadataInput {
  revision: number;
  tags: string[];
  note: string;
  analysis_enabled: boolean;
}

export interface ReviewAssetMetadata extends ReviewAssetMetadataInput {
  asset_id: string;
  updated_at: string;
}

export interface ReviewAssetBatchInput {
  asset_ids: string[];
  analysis_enabled?: boolean;
  add_tags: string[];
  remove_tags: string[];
}

export interface ReviewImportItem {
  series_id: string;
  series_name: string;
  review_id?: string | null;
  source_url?: string | null;
  original_review: Record<string, unknown>;
}

export interface ReviewImportValidation {
  importable: Array<{
    line: number;
    series_id: string;
    series_name: string;
    review_id: string | null;
    content_hash: string;
  }>;
  duplicates: Array<{ line: number; reason: string }>;
  errors: Array<{ line: number; type: string; message: string }>;
  validation_fingerprint: string;
}

export interface ReviewImportResult {
  imported_count: number;
  duplicate_count: number;
  asset_ids: string[];
}

export interface ReviewDeletion {
  audit_id?: string;
  asset_id: string;
  source_kind?: ReviewAssetSourceKind;
  platform?: string;
  review_id: string;
  series_id?: string;
  series_name_snapshot?: string;
  content_hash: string;
  reason: string;
  deleted_at: string;
  recollection_allowed_at?: string | null;
}

export interface ReviewAssetSummaryStats {
  total: number;
  analysis_enabled: number;
  analysis_disabled: number;
  by_source: Array<{ source_kind: ReviewAssetSourceKind; count: number }>;
  by_series: Array<{
    series_id: string;
    series_name: string;
    count: number;
    analysis_enabled: number;
  }>;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
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
    throw new ApiError(response.status, message, undefined);
  }
  return response.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });

const remove = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "DELETE", body: JSON.stringify(body) });

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

export interface ReviewAssetApi {
  listReviewAssets(
    filters?: ReviewAssetFilters,
  ): Promise<Page<ReviewAssetSummary>>;
  getReviewAsset(assetId: string): Promise<ReviewAssetDetail>;
  updateReviewAssetMetadata(
    assetId: string,
    input: ReviewAssetMetadataInput,
  ): Promise<ReviewAssetMetadata>;
  batchUpdateReviewAssetMetadata(
    input: ReviewAssetBatchInput,
  ): Promise<{ updated_count: number }>;
  validateReviewImport(input: {
    items: ReviewImportItem[];
    payload_bytes: number;
  }): Promise<ReviewImportValidation>;
  confirmReviewImport(input: {
    items: ReviewImportItem[];
    payload_bytes: number;
    validation_fingerprint: string;
  }): Promise<ReviewImportResult>;
  validateReviewImportFile(file: File): Promise<ReviewImportValidation>;
  confirmReviewImportFile(
    file: File,
    validationFingerprint: string,
  ): Promise<ReviewImportResult>;
  deleteReviewAsset(
    assetId: string,
    input: {
      expected_content_hash: string;
      confirmed_review_id: string;
      reason: string;
      confirm: true;
    },
  ): Promise<ReviewDeletion>;
  getReviewAssetSummary(): Promise<ReviewAssetSummaryStats>;
  listReviewDeletions(
    page?: number,
    pageSize?: number,
  ): Promise<Page<ReviewDeletion>>;
  allowReviewRecollection(assetId: string): Promise<ReviewDeletion>;
}

export const collectionApi: CollectionApi & ReviewAssetApi = {
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
  listReviewAssets: (filters = {}) => {
    const entries: Array<[string, string]> = [];
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== "") {
        entries.push([key, String(value)]);
      }
    }
    const query = entries
      .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
      .join("&");
    return request(`/review-assets${query ? `?${query}` : ""}`);
  },
  getReviewAsset: (assetId) =>
    request(`/review-assets/${encodeURIComponent(assetId)}`),
  updateReviewAssetMetadata: (assetId, input) =>
    patch(`/review-assets/${encodeURIComponent(assetId)}/metadata`, input),
  batchUpdateReviewAssetMetadata: (input) =>
    patch("/review-assets/metadata", input),
  validateReviewImport: (input) =>
    post("/review-assets/import/validate", input),
  confirmReviewImport: (input) => post("/review-assets/import", input),
  validateReviewImportFile: (file) =>
    request(
      `/review-assets/import-file/validate?filename=${encodeURIComponent(file.name)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      },
    ),
  confirmReviewImportFile: (file, validationFingerprint) =>
    request(
      `/review-assets/import-file?filename=${encodeURIComponent(file.name)}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-Validation-Fingerprint": validationFingerprint,
        },
        body: file,
      },
    ),
  deleteReviewAsset: (assetId, input) =>
    remove(`/review-assets/${encodeURIComponent(assetId)}`, input),
  getReviewAssetSummary: () => request("/review-assets/summary"),
  listReviewDeletions: (page = 1, pageSize = 20) =>
    request(`/deletions?page=${page}&page_size=${pageSize}`),
  allowReviewRecollection: (assetId) =>
    post(`/deletions/${encodeURIComponent(assetId)}/allow-recollection`),
};
