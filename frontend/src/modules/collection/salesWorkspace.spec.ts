import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Page,
  SalesCollectionApi,
  SalesCollectionJob,
  SalesCollectionOverview,
  SalesRecordRow,
} from "./api";
import { createSalesWorkspace } from "./salesWorkspace";

const source = (
  platform: "autohome" | "dongchedi" | "yiche",
  availability: "live" | "verification_required",
) => ({ platform, label: platform, availability, description: "说明" });

const job = (status: SalesCollectionJob["status"]): SalesCollectionJob => ({
  id: "sales-job",
  start_month: "2026-01",
  end_month: "2026-04",
  platforms: ["autohome", "dongchedi", "yiche"],
  status,
  total_steps: 12,
  completed_steps: status === "completed" ? 12 : 1,
  failed_steps: 0,
  record_count: 600,
  last_error: null,
  created_at: "2026-10-19T12:00:00+00:00",
  started_at: null,
  finished_at: null,
  updated_at: "2026-10-19T12:00:00+00:00",
});

const overview = (
  active: SalesCollectionJob | null,
): SalesCollectionOverview => ({
  record_count: 600,
  matched_count: 351,
  unmatched_count: 249,
  months: ["2026-01"],
  active_job: active,
  latest_job: active ?? job("completed"),
  sources: [
    source("autohome", "live"),
    source("dongchedi", "verification_required"),
    source("yiche", "verification_required"),
  ],
});

const page = <T>(rows: T[]): Page<T> => ({
  rows,
  total: rows.length,
  page: 1,
  page_size: 20,
});

function api(overrides: Partial<SalesCollectionApi> = {}): SalesCollectionApi {
  return {
    getSalesOverview: vi.fn().mockResolvedValue(overview(null)),
    listSalesJobs: vi.fn().mockResolvedValue(page([])),
    getSalesJob: vi.fn().mockResolvedValue({ ...job("completed"), steps: [] }),
    createSalesJob: vi.fn().mockResolvedValue(job("queued")),
    listSalesRecords: vi.fn().mockResolvedValue(page([])),
    salesExportUrl: vi.fn().mockReturnValue("/api/sales-collection/export"),
    ...overrides,
  };
}

describe("sales collection workspace", () => {
  beforeEach(() => vi.useFakeTimers());

  it("loads overview, jobs, and records then polls only for an active job", async () => {
    const client = api({
      getSalesOverview: vi
        .fn()
        .mockResolvedValueOnce(overview(job("running")))
        .mockResolvedValueOnce(overview(null)),
    });
    const workspace = createSalesWorkspace(client, false);

    await workspace.activate();
    expect(workspace.overview.value?.record_count).toBe(600);
    expect(vi.getTimerCount()).toBe(1);
    await vi.runOnlyPendingTimersAsync();

    expect(client.getSalesOverview).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("creates the selected month and platform range and refreshes dashboard", async () => {
    const client = api();
    const workspace = createSalesWorkspace(client, false);
    workspace.startMonth.value = "2026-01";
    workspace.endMonth.value = "2026-04";
    workspace.selectedPlatforms.value = ["autohome", "dongchedi"];

    await workspace.startJob();

    expect(client.createSalesJob).toHaveBeenCalledWith({
      start_month: "2026-01",
      end_month: "2026-04",
      platforms: ["autohome", "dongchedi"],
    });
    expect(client.getSalesOverview).toHaveBeenCalled();
  });

  it("applies record filters and exposes the same filters in the export url", async () => {
    const row = {
      platform: "autohome",
      month: "2026-01",
      series_id: "5769",
      series_name: "Model Y",
      sales_volume: 25000,
      rank: 1,
      metric: "national_monthly_retail",
      source_url: "source",
      source_snapshot_hash: "hash",
      collected_at: "now",
      job_id: "job",
      review_series_id: "5769",
      review_series_name: "Model Y",
      match_method: "normalized_exact",
      match_status: "matched",
    } satisfies SalesRecordRow;
    const client = api({
      listSalesRecords: vi.fn().mockResolvedValue(page([row])),
    });
    const workspace = createSalesWorkspace(client, false);
    workspace.filters.platform = "autohome";
    workspace.filters.month = "2026-01";
    workspace.filters.search = "Model";
    workspace.filters.match_status = "matched";

    await workspace.applyFilters();
    const url = workspace.exportUrl.value;

    expect(client.listSalesRecords).toHaveBeenCalledWith({
      platform: "autohome",
      month: "2026-01",
      search: "Model",
      match_status: "matched",
      page: 1,
      page_size: 20,
    });
    expect(client.salesExportUrl).toHaveBeenCalledWith({
      platform: "autohome",
      month: "2026-01",
      search: "Model",
      match_status: "matched",
    });
    expect(url).toBe("/api/sales-collection/export");
  });

  it("focuses a matrix sales gap on the exact month and mapped review series", async () => {
    const client = api();
    const workspace = createSalesWorkspace(client, false);

    await workspace.focusGap("2026-03", "5769");

    expect(workspace.startMonth.value).toBe("2026-03");
    expect(workspace.endMonth.value).toBe("2026-03");
    expect(workspace.appliedFilters.month).toBe("2026-03");
    expect(workspace.appliedFilters.search).toBe("5769");
    expect(client.listSalesRecords).toHaveBeenCalledWith(
      expect.objectContaining({ month: "2026-03", search: "5769" }),
    );
  });

  it("turns API failures into one visible Chinese message", async () => {
    const workspace = createSalesWorkspace(
      api({
        getSalesOverview: vi.fn().mockRejectedValue(new Error("网络中断")),
      }),
      false,
    );

    await workspace.activate();

    expect(workspace.error.value).toContain("网络中断");
  });
});
