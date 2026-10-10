import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  collectionApi,
  type CatalogRun,
  type CatalogSeriesRow,
  type CatalogStatus,
  type CollectionApi,
  type CollectionJob,
  type Page,
} from "./api";
import { createCatalogFlow } from "./catalogFlow";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function run(status: CatalogRun["status"] = "discovering"): CatalogRun {
  return {
    id: "run-1",
    batch_id: "batch-1",
    status,
    target_unique_series: 1000,
    scanned_count: 120,
    unique_count: 100,
    skipped_count: 2,
    current_page: 3,
    error_code: null,
    error_message: null,
    source_exhausted: false,
    created_at: "2026-10-09T08:00:00+00:00",
    started_at: "2026-10-09T08:00:01+00:00",
    finished_at: null,
    updated_at: "2026-10-09T08:00:02+00:00",
  };
}

function status(
  activeRun: CatalogRun | null = null,
  batchId: string | null = "batch-1",
): CatalogStatus {
  return {
    active_batch_id: batchId,
    series_count: batchId ? 3 : 0,
    published_at: batchId ? "2026-10-09T07:00:00+00:00" : null,
    source_url: "https://www.autohome.com.cn/price/ev#pvareaid=3311257",
    source_exhausted: false,
    active_run: activeRun,
  };
}

function row(index = 1, batchId = "batch-1"): CatalogSeriesRow {
  const seriesId = String(5700 + index);
  return {
    batch_id: batchId,
    platform: "autohome",
    series_id: seriesId,
    series_name: `测试车系 ${index}`,
    series_url: `https://www.autohome.com.cn/${seriesId}/`,
    review_url: `https://k.autohome.com.cn/${seriesId}/`,
    discovery_rank: index,
    discovered_at: "2026-10-09T07:00:00+00:00",
    published_at: "2026-10-09T07:01:00+00:00",
  };
}

function emptyPage<T>(): Page<T> {
  return { rows: [], total: 0, page: 1, page_size: 20 };
}

function queuedJob(): CollectionJob {
  return {
    id: "job-1",
    mode: "verification",
    source_url: "https://www.autohome.com.cn/price/ev#pvareaid=3311257",
    max_series: 1,
    max_pages_per_series: 2,
    request_delay_min_seconds: 2,
    request_delay_max_seconds: 4,
    series_delay_min_seconds: 5,
    series_delay_max_seconds: 10,
    status: "queued",
    resume_status: null,
    control_requested: null,
    current_series_index: 0,
    current_series_id: null,
    current_series_name: null,
    current_page: 1,
    discovered_count: 1,
    saved_count: 0,
    duplicate_count: 0,
    failed_count: 0,
    skipped_count: 0,
    last_success_at: null,
    last_error: null,
    created_at: "2026-10-09T08:00:00+00:00",
    started_at: null,
    finished_at: null,
    updated_at: "2026-10-09T08:00:00+00:00",
  };
}

function api(overrides: Partial<CollectionApi> = {}): CollectionApi {
  return {
    getOverview: vi.fn(),
    listJobs: vi.fn(),
    getJob: vi.fn(),
    createJob: vi.fn().mockResolvedValue(queuedJob()),
    pauseJob: vi.fn(),
    resumeJob: vi.fn(),
    stopJob: vi.fn(),
    listSeries: vi.fn(),
    listReviews: vi.fn(),
    getReview: vi.fn(),
    getCatalogStatus: vi.fn().mockResolvedValue(status()),
    listCatalog: vi.fn().mockResolvedValue({
      rows: [row()],
      total: 1,
      page: 1,
      page_size: 20,
    }),
    listCatalogSelection: vi.fn().mockResolvedValue({
      batch_id: "batch-1",
      series_ids: ["5701"],
      total: 1,
    }),
    startCatalogDiscovery: vi.fn().mockResolvedValue(run("queued")),
    getCatalogRun: vi.fn().mockResolvedValue(run("completed_short")),
    cancelCatalogDiscovery: vi.fn().mockResolvedValue(run("cancelling")),
    ...overrides,
  };
}

describe("catalog flow", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.unstubAllGlobals();
  });

  it("loads_cached_catalog_status_on_open", async () => {
    const client = api();
    const flow = createCatalogFlow(client, vi.fn(), false);

    await flow.open();

    expect(client.getCatalogStatus).toHaveBeenCalledOnce();
    expect(flow.catalogStatus.value?.active_batch_id).toBe("batch-1");
    expect(flow.isOpen.value).toBe(true);
    expect(flow.step.value).toBe("discovery");
  });

  it("polls_only_while_discovery_is_non_terminal", async () => {
    const client = api({
      getCatalogStatus: vi
        .fn()
        .mockResolvedValueOnce(status(run("discovering")))
        .mockResolvedValueOnce(status(null, "batch-2")),
      getCatalogRun: vi.fn().mockResolvedValue(run("completed_short")),
      listCatalog: vi.fn().mockResolvedValue({
        rows: [row(1, "batch-2")],
        total: 1,
        page: 1,
        page_size: 20,
      }),
    });
    const flow = createCatalogFlow(client, vi.fn(), false);

    await flow.open();
    expect(vi.getTimerCount()).toBe(1);
    await vi.advanceTimersByTimeAsync(2_000);

    expect(client.getCatalogRun).toHaveBeenCalledWith("run-1");
    expect(client.getCatalogStatus).toHaveBeenCalledTimes(2);
    expect(client.listCatalog).toHaveBeenCalledWith("", 1, 20);
    expect(flow.discoveryRun.value?.status).toBe("completed_short");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("closes_without_leaking_poll_timers", async () => {
    const flow = createCatalogFlow(
      api({ getCatalogStatus: vi.fn().mockResolvedValue(status(run())) }),
      vi.fn(),
      false,
    );

    await flow.open();
    expect(vi.getTimerCount()).toBe(1);
    flow.close();

    expect(flow.isOpen.value).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("select_filtered_uses_all_server_matched_ids", async () => {
    const client = api({
      listCatalogSelection: vi.fn().mockResolvedValue({
        batch_id: "batch-1",
        series_ids: ["5701", "5708", "5799"],
        total: 3,
      }),
    });
    const flow = createCatalogFlow(client, vi.fn(), false);
    await flow.open();
    await flow.goToSelection();
    flow.query.value = "汉 EV";

    await flow.selectFiltered();

    expect(client.listCatalogSelection).toHaveBeenCalledWith("汉 EV");
    expect(flow.selectedSeriesIds.value).toEqual(["5701", "5708", "5799"]);
  });

  it("verification_blocks_more_than_three_without_discarding_selection", async () => {
    const client = api();
    const flow = createCatalogFlow(client, vi.fn(), false);
    ["5701", "5702", "5703", "5704"].forEach(flow.toggleSeries);

    await flow.createJob();

    expect(client.createJob).not.toHaveBeenCalled();
    expect(flow.selectedSeriesIds.value).toEqual([
      "5701",
      "5702",
      "5703",
      "5704",
    ]);
    expect(flow.error.value).toContain("最多选择 3 个");
  });

  it("production_requires_second_confirmation_with_exact_selected_count", async () => {
    const client = api();
    const flow = createCatalogFlow(client, vi.fn(), false);
    flow.mode.value = "production";
    ["5701", "5702", "5703", "5704", "5705"].forEach(flow.toggleSeries);

    await flow.createJob();

    expect(client.createJob).not.toHaveBeenCalled();
    expect(flow.productionConfirmPending.value).toBe(true);
    expect(flow.productionConfirmationText.value).toContain("5 个车系");

    await flow.confirmProduction();
    expect(client.createJob).toHaveBeenCalledWith({
      mode: "production",
      selected_series_ids: ["5701", "5702", "5703", "5704", "5705"],
    });
  });

  it("catalog_version_change_removes_invalid_unsubmitted_ids", async () => {
    const client = api({
      getCatalogStatus: vi
        .fn()
        .mockResolvedValueOnce(status(null, "batch-1"))
        .mockResolvedValueOnce(status(null, "batch-2")),
      listCatalog: vi.fn().mockResolvedValue({
        rows: [row(2, "batch-2")],
        total: 1,
        page: 1,
        page_size: 20,
      }),
      listCatalogSelection: vi.fn().mockResolvedValue({
        batch_id: "batch-2",
        series_ids: ["5702"],
        total: 1,
      }),
    });
    const flow = createCatalogFlow(client, vi.fn(), false);
    await flow.open();
    flow.toggleSeries("5701");
    flow.toggleSeries("5702");

    await flow.loadCatalog();

    expect(flow.selectedSeriesIds.value).toEqual(["5702"]);
    expect(flow.removedSelectionCount.value).toBe(1);
  });

  it("ignores_an_older_reconciliation_after_a_newer_catalog_generation", async () => {
    const oldSelection = deferred<{
      batch_id: string;
      series_ids: string[];
      total: number;
    }>();
    const client = api({
      getCatalogStatus: vi
        .fn()
        .mockResolvedValueOnce(status(null, "batch-1"))
        .mockResolvedValueOnce(status(null, "batch-2"))
        .mockResolvedValueOnce(status(null, "batch-3")),
      listCatalog: vi
        .fn()
        .mockResolvedValueOnce({
          rows: [row(1, "batch-2")],
          total: 1,
          page: 1,
          page_size: 20,
        })
        .mockResolvedValueOnce({
          rows: [row(2, "batch-3")],
          total: 1,
          page: 1,
          page_size: 20,
        }),
      listCatalogSelection: vi
        .fn()
        .mockReturnValueOnce(oldSelection.promise)
        .mockResolvedValueOnce({
          batch_id: "batch-3",
          series_ids: ["5702"],
          total: 1,
        }),
    });
    const flow = createCatalogFlow(client, vi.fn(), false);
    await flow.open();
    flow.toggleSeries("5701");
    flow.toggleSeries("5702");

    const olderLoad = flow.loadCatalog();
    while (vi.mocked(client.listCatalogSelection).mock.calls.length === 0) {
      await Promise.resolve();
    }
    const newerLoad = flow.loadCatalog();
    await newerLoad;
    oldSelection.resolve({
      batch_id: "batch-2",
      series_ids: ["5701"],
      total: 1,
    });
    await olderLoad;

    expect(flow.catalogStatus.value?.active_batch_id).toBe("batch-3");
    expect(flow.selectedSeriesIds.value).toEqual(["5702"]);
  });

  it("ignores_select_all_result_for_a_superseded_query", async () => {
    const oldSelection = deferred<{
      batch_id: string;
      series_ids: string[];
      total: number;
    }>();
    const client = api({
      listCatalogSelection: vi
        .fn()
        .mockReturnValueOnce(oldSelection.promise)
        .mockResolvedValueOnce({
          batch_id: "batch-1",
          series_ids: ["5702"],
          total: 1,
        }),
    });
    const flow = createCatalogFlow(client, vi.fn(), false);
    await flow.open();
    flow.query.value = "旧查询";
    const older = flow.selectFiltered();
    flow.query.value = "新查询";
    await flow.selectFiltered();
    oldSelection.resolve({
      batch_id: "batch-1",
      series_ids: ["5701"],
      total: 1,
    });
    await older;

    expect(flow.selectedSeriesIds.value).toEqual(["5702"]);
  });

  it("a_previous_submission_cannot_close_a_reopened_dialog", async () => {
    const submission = deferred<CollectionJob>();
    const refresh = vi.fn().mockResolvedValue(undefined);
    const client = api({
      createJob: vi.fn().mockReturnValue(submission.promise),
    });
    const flow = createCatalogFlow(client, refresh, false);
    await flow.open();
    flow.toggleSeries("5701");

    const pending = flow.createJob();
    flow.close();
    await flow.open();
    submission.resolve(queuedJob());
    await pending;

    expect(flow.isOpen.value).toBe(true);
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("successful_job_creation_closes_and_refreshes_workspace", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    const client = api();
    const flow = createCatalogFlow(client, refresh, false);
    await flow.open();
    flow.toggleSeries("5701");

    await flow.createJob();

    expect(client.createJob).toHaveBeenCalledWith({
      mode: "verification",
      selected_series_ids: ["5701"],
    });
    expect(flow.isOpen.value).toBe(false);
    expect(refresh).toHaveBeenCalledOnce();
  });
});

describe("catalog API paths", () => {
  it("uses encoded collection catalog paths", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    await collectionApi.getCatalogStatus();
    await collectionApi.listCatalog("汉 EV", 2, 20);
    await collectionApi.listCatalogSelection("汉 EV");
    await collectionApi.startCatalogDiscovery();
    await collectionApi.getCatalogRun("run/1");
    await collectionApi.cancelCatalogDiscovery("run/1");

    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/collection/catalog/status",
      "/api/collection/catalog?query=%E6%B1%89%20EV&page=2&page_size=20",
      "/api/collection/catalog/selection?query=%E6%B1%89%20EV",
      "/api/collection/catalog/discover",
      "/api/collection/catalog/discover/run%2F1",
      "/api/collection/catalog/discover/run%2F1/cancel",
    ]);
  });

  it("reads object-shaped FastAPI details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: vi.fn().mockResolvedValue({
          detail: {
            message: "所选车系已失效",
            invalid_series_ids: ["5701"],
          },
        }),
      }),
    );

    await expect(
      collectionApi.createJob({
        mode: "verification",
        selected_series_ids: ["5701"],
      }),
    ).rejects.toThrow("所选车系已失效（5701）");
  });
});
