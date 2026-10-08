import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CollectionApi,
  CollectionJob,
  CollectionJobDetail,
  CollectionOverview,
  Page,
  ReviewDetail,
  ReviewSummary,
  SeriesRow,
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

function overview(activeJob: CollectionJob | null): CollectionOverview {
  return {
    series_count: activeJob ? 3 : 12,
    review_count: activeJob ? 20 : 240,
    pending_errors: 0,
    active_job: activeJob,
  };
}

function page(rows: CollectionJob[]): Page<CollectionJob> {
  return { rows, total: rows.length, page: 1, page_size: 20 };
}

function api(overrides: Partial<CollectionApi> = {}): CollectionApi {
  return {
    getOverview: vi.fn().mockResolvedValue(overview(null)),
    listJobs: vi.fn().mockResolvedValue(page([])),
    getJob: vi.fn().mockResolvedValue({ ...job(), events: [] }),
    createJob: vi.fn().mockResolvedValue(job("queued")),
    pauseJob: vi.fn().mockResolvedValue(job("collecting")),
    resumeJob: vi.fn().mockResolvedValue(job("collecting")),
    stopJob: vi.fn().mockResolvedValue(job("collecting")),
    listSeries: vi.fn(),
    listReviews: vi.fn(),
    getReview: vi.fn(),
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function seriesRow(): SeriesRow {
  return {
    platform: "autohome",
    series_id: "5769",
    series_name: "Model Y",
    series_url: "https://www.autohome.com.cn/5769/",
    review_url: "https://k.autohome.com.cn/5769/",
    discovery_rank: 1,
    first_discovered_at: "2026-10-08T08:00:00+00:00",
    last_confirmed_at: "2026-10-08T08:01:00+00:00",
    comment_count: 1,
  };
}

function reviewSummary(): ReviewSummary {
  return {
    platform: "autohome",
    review_id: "review-1",
    series_id: "5769",
    series_name: "Model Y",
    source_url: "https://k.autohome.com.cn/5769/#review-1",
    content_hash: "a".repeat(64),
    first_collected_at: "2026-10-08T08:02:00+00:00",
    last_confirmed_at: "2026-10-08T08:02:00+00:00",
  };
}

describe("collection workspace", () => {
  beforeEach(() => vi.useFakeTimers());

  it("test_loads_overview_and_jobs_without_project_context", async () => {
    const client = api();
    const workspace = createCollectionWorkspace(client, false);

    await workspace.loadWorkspace();

    expect(client.getOverview).toHaveBeenCalledOnce();
    expect(client.listJobs).toHaveBeenCalledWith(1, 20);
    expect(workspace.overview.value?.series_count).toBe(12);
    expect(workspace.jobs.value.rows).toEqual([]);
  });

  it("test_polls_only_while_active_job_is_running", async () => {
    const running = job("collecting");
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
    expect(vi.getTimerCount()).toBe(0);
  });

  it("test_stale_poll_response_cannot_replace_newer_state", async () => {
    const oldOverview = deferred<CollectionOverview>();
    const oldJobs = deferred<Page<CollectionJob>>();
    const client = api({
      getOverview: vi
        .fn()
        .mockReturnValueOnce(oldOverview.promise)
        .mockResolvedValueOnce(overview(null)),
      listJobs: vi
        .fn()
        .mockReturnValueOnce(oldJobs.promise)
        .mockResolvedValueOnce(page([job("completed")])),
    });
    const workspace = createCollectionWorkspace(client, false);

    const stale = workspace.loadWorkspace();
    await workspace.loadWorkspace();
    oldOverview.resolve(overview(job("collecting")));
    oldJobs.resolve(page([job("collecting")]));
    await stale;

    expect(workspace.overview.value?.active_job).toBeNull();
    expect(workspace.jobs.value.rows[0]?.status).toBe("completed");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("test_pause_resume_stop_refresh_current_job", async () => {
    const client = api();
    const workspace = createCollectionWorkspace(client, false);
    await workspace.loadWorkspace();

    await workspace.pause("job-1");
    await workspace.resume("job-1");
    await workspace.stop("job-1");

    expect(client.pauseJob).toHaveBeenCalledWith("job-1");
    expect(client.resumeJob).toHaveBeenCalledWith("job-1");
    expect(client.stopJob).toHaveBeenCalledWith("job-1");
    expect(client.getOverview).toHaveBeenCalledTimes(4);
  });

  it("loads persisted events for a selected historical job", async () => {
    const detail: CollectionJobDetail = {
      ...job("partial_failed"),
      events: [
        {
          id: 7,
          job_id: "job-1",
          series_id: "5769",
          event_type: "series_failed",
          error_class: "TimeoutError",
          message: "车系采集失败",
          details: null,
          retryable: false,
          created_at: "2026-10-08T08:03:00+00:00",
        },
      ],
    };
    const client = api({ getJob: vi.fn().mockResolvedValue(detail) });
    const workspace = createCollectionWorkspace(client, false);

    await workspace.openJob("job-1");

    expect(client.getJob).toHaveBeenCalledWith("job-1");
    expect(workspace.selectedJob.value?.events[0]?.event_type).toBe(
      "series_failed",
    );
    workspace.closeJob();
    expect(workspace.selectedJob.value).toBeNull();
  });

  it("test_deactivation_clears_poll_timer", async () => {
    const client = api({
      getOverview: vi.fn().mockResolvedValue(overview(job("discovering"))),
      listJobs: vi.fn().mockResolvedValue(page([job("discovering")])),
    });
    const workspace = createCollectionWorkspace(client, false);

    await workspace.activate();
    expect(vi.getTimerCount()).toBe(1);
    workspace.deactivate();

    expect(vi.getTimerCount()).toBe(0);
  });

  it("submits verification defaults and requires a second production confirmation", async () => {
    const client = api();
    const workspace = createCollectionWorkspace(client, false);

    await workspace.createJob();
    expect(client.createJob).toHaveBeenCalledWith({
      mode: "verification",
      max_series: 3,
      max_pages_per_series: 2,
    });

    workspace.jobMode.value = "production";
    await workspace.createJob();
    expect(client.createJob).toHaveBeenCalledTimes(1);
    expect(workspace.productionConfirmPending.value).toBe(true);
    expect(workspace.productionConfirmationText).toContain(
      "前 500 个车系、每车系全部评论",
    );
    expect(workspace.productionConfirmationText).toContain("2～4 秒");
    expect(workspace.productionConfirmationText).toContain("5～10 秒");

    await workspace.confirmProduction();
    expect(client.createJob).toHaveBeenLastCalledWith({ mode: "production" });
  });

  it("keeps saved counts after stop and exposes state errors unchanged", async () => {
    const stopped = { ...job("stopped"), saved_count: 37 };
    const client = api({
      getOverview: vi.fn().mockResolvedValue(overview(null)),
      listJobs: vi.fn().mockResolvedValue(page([stopped])),
      stopJob: vi.fn().mockResolvedValue(stopped),
      pauseJob: vi.fn().mockRejectedValue(new Error("当前任务不能暂停")),
    });
    const workspace = createCollectionWorkspace(client, false);

    await workspace.stop("job-1");
    expect(workspace.jobs.value.rows[0]?.saved_count).toBe(37);
    await workspace.pause("job-1");
    expect(workspace.error.value).toBe("当前任务不能暂停");
  });

  it("resets series pagination and searches after a 250ms debounce", async () => {
    const client = api({
      listSeries: vi.fn().mockResolvedValue({
        rows: [seriesRow()],
        total: 1,
        page: 1,
        page_size: 20,
      }),
    });
    const workspace = createCollectionWorkspace(client, false);
    workspace.seriesPage.value = 3;
    workspace.seriesQuery.value = "Model Y";

    workspace.searchSeries();
    expect(workspace.seriesPage.value).toBe(1);
    await vi.advanceTimersByTimeAsync(249);
    expect(client.listSeries).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);

    expect(client.listSeries).toHaveBeenCalledWith("Model Y", 1, 20);
  });

  it("selects a named series and filters reviews only by series_id", async () => {
    const client = api({
      listReviews: vi.fn().mockResolvedValue({
        rows: [reviewSummary()],
        total: 1,
        page: 1,
        page_size: 20,
      }),
    });
    const workspace = createCollectionWorkspace(client, false);

    await workspace.selectSeries(seriesRow());

    expect(client.listReviews).toHaveBeenCalledWith("5769", 1, 20);
    expect(workspace.selectedSeries.value?.series_name).toBe("Model Y");
    expect(workspace.page.value).toBe("reviews");
  });

  it("loads full review details separately from summary rows", async () => {
    const detail: ReviewDetail = {
      ...reviewSummary(),
      original_review: {
        Koubeiid: "review-1",
        contents: [{ content: "完整评论" }],
      },
    };
    const client = api({
      listReviews: vi.fn().mockResolvedValue({
        rows: [reviewSummary()],
        total: 1,
        page: 1,
        page_size: 20,
      }),
      getReview: vi.fn().mockResolvedValue(detail),
    });
    const workspace = createCollectionWorkspace(client, false);
    await workspace.selectSeries(seriesRow());

    expect("original_review" in workspace.reviews.value.rows[0]!).toBe(false);
    await workspace.openReview("review-1");

    expect(client.getReview).toHaveBeenCalledWith("review-1");
    expect(workspace.reviewDetail.value?.original_review).toEqual(
      detail.original_review,
    );
  });

  it("builds export URLs only from the selected persisted series", () => {
    const workspace = createCollectionWorkspace(api(), false);
    expect(workspace.selectedSeriesExportUrl.value).toBe("");

    workspace.selectedSeries.value = seriesRow();

    expect(workspace.selectedSeriesExportUrl.value).toBe(
      "/api/collection/export?series_id=5769",
    );
  });
});
