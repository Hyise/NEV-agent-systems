import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CollectionApi,
  CollectionJob,
  CollectionJobDetail,
  CollectionOverview,
  Page,
} from "./api";
import { createCollectionWorkspace } from "./workspace";

function job(status: CollectionJob["status"] = "collecting"): CollectionJob {
  return {
    id: "job-1",
    mode: "verification",
    source_url: "https://www.autohome.com.cn/price/ev#pvareaid=3311257",
    max_series: 3,
    max_pages_per_series: 2,
    request_delay_min_seconds: 2,
    request_delay_max_seconds: 4,
    series_delay_min_seconds: 5,
    series_delay_max_seconds: 10,
    status,
    resume_status: null,
    control_requested: null,
    current_series_index: 0,
    current_series_id: "5769",
    current_series_name: "Model Y",
    current_page: 1,
    discovered_count: 3,
    saved_count: 20,
    duplicate_count: 0,
    failed_count: 0,
    skipped_count: 0,
    last_success_at: null,
    last_error: null,
    created_at: "2026-10-08T08:00:00+00:00",
    started_at: "2026-10-08T08:00:01+00:00",
    finished_at: null,
    updated_at: "2026-10-08T08:00:02+00:00",
  };
}

const overview = (active_job: CollectionJob | null): CollectionOverview => ({
  series_count: active_job ? 3 : 12,
  review_count: active_job ? 20 : 240,
  pending_errors: 0,
  active_job,
});

const page = (rows: CollectionJob[]): Page<CollectionJob> => ({
  rows,
  total: rows.length,
  page: 1,
  page_size: 20,
});

function api(overrides: Partial<CollectionApi> = {}): CollectionApi {
  return {
    getOverview: vi.fn().mockResolvedValue(overview(null)),
    listJobs: vi.fn().mockResolvedValue(page([])),
    getJob: vi.fn().mockResolvedValue({ ...job(), events: [] }),
    createJob: vi.fn().mockResolvedValue(job("queued")),
    pauseJob: vi.fn().mockResolvedValue(job()),
    resumeJob: vi.fn().mockResolvedValue(job()),
    stopJob: vi.fn().mockResolvedValue(job()),
    listSeries: vi.fn(),
    listReviews: vi.fn(),
    getReview: vi.fn(),
    getCatalogStatus: vi.fn(),
    listCatalog: vi.fn(),
    listCatalogSelection: vi.fn(),
    startCatalogDiscovery: vi.fn(),
    getCatalogRun: vi.fn(),
    cancelCatalogDiscovery: vi.fn(),
    ...overrides,
  };
}

describe("collection workspace", () => {
  beforeEach(() => vi.useFakeTimers());

  it("defaults to acquisition and owns only navigation and collection jobs", () => {
    const workspace = createCollectionWorkspace(api(), false);

    expect(workspace.page.value).toBe("acquire");
    workspace.navigate("assets");
    expect(workspace.page.value).toBe("assets");
    workspace.navigate("research");
    expect(workspace.page.value).toBe("research");
    expect("reviews" in workspace).toBe(false);
    expect("series" in workspace).toBe(false);
  });

  it("loads overview and jobs and polls only while a job is running", async () => {
    const running = job();
    const client = api({
      getOverview: vi
        .fn()
        .mockResolvedValueOnce(overview(running))
        .mockResolvedValueOnce(overview(null)),
      listJobs: vi
        .fn()
        .mockResolvedValueOnce(page([running]))
        .mockResolvedValueOnce(page([job("completed")])),
    });
    const workspace = createCollectionWorkspace(client, false);

    await workspace.activate();
    expect(vi.getTimerCount()).toBe(1);
    await vi.runOnlyPendingTimersAsync();

    expect(client.getOverview).toHaveBeenCalledTimes(2);
    expect(workspace.jobs.value.rows[0]?.status).toBe("completed");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("keeps the loaded workspace visible while a running job is polled", async () => {
    const running = job();
    let resolveOverview!: (value: CollectionOverview) => void;
    let resolveJobs!: (value: Page<CollectionJob>) => void;
    const pendingOverview = new Promise<CollectionOverview>((resolve) => {
      resolveOverview = resolve;
    });
    const pendingJobs = new Promise<Page<CollectionJob>>((resolve) => {
      resolveJobs = resolve;
    });
    const client = api({
      getOverview: vi
        .fn()
        .mockResolvedValueOnce(overview(running))
        .mockReturnValueOnce(pendingOverview),
      listJobs: vi
        .fn()
        .mockResolvedValueOnce(page([running]))
        .mockReturnValueOnce(pendingJobs),
    });
    const workspace = createCollectionWorkspace(client, false);

    const firstLoad = workspace.activate();
    expect(workspace.busy.value).toBe(true);
    await firstLoad;
    expect(workspace.busy.value).toBe(false);
    expect(workspace.overview.value?.active_job?.status).toBe("collecting");

    await vi.advanceTimersByTimeAsync(2_000);

    expect(client.getOverview).toHaveBeenCalledTimes(2);
    expect(workspace.busy.value).toBe(false);
    expect(workspace.overview.value?.active_job?.status).toBe("collecting");

    resolveOverview(overview(null));
    resolveJobs(page([job("completed")]));
    await Promise.resolve();
    await Promise.resolve();

    expect(workspace.jobs.value.rows[0]?.status).toBe("completed");
    expect(workspace.busy.value).toBe(false);
  });

  it("controls jobs, loads persisted events, and invalidates late state", async () => {
    let resolveOverview!: (value: CollectionOverview) => void;
    const pending = new Promise<CollectionOverview>((resolve) => {
      resolveOverview = resolve;
    });
    const detail: CollectionJobDetail = {
      ...job("partial_failed"),
      events: [],
    };
    const client = api({
      getOverview: vi
        .fn()
        .mockReturnValueOnce(pending)
        .mockResolvedValue(overview(null)),
      getJob: vi.fn().mockResolvedValue(detail),
    });
    const workspace = createCollectionWorkspace(client, false);

    const stale = workspace.loadWorkspace();
    await workspace.loadWorkspace();
    resolveOverview(overview(job()));
    await stale;
    expect(workspace.overview.value?.active_job).toBeNull();

    await workspace.openJob("job-1");
    expect(workspace.selectedJob.value?.status).toBe("partial_failed");
    workspace.closeJob();
    await workspace.pause("job-1");
    await workspace.resume("job-1");
    await workspace.stop("job-1");
    expect(client.pauseJob).toHaveBeenCalledWith("job-1");
    expect(client.resumeJob).toHaveBeenCalledWith("job-1");
    expect(client.stopJob).toHaveBeenCalledWith("job-1");
  });
});
