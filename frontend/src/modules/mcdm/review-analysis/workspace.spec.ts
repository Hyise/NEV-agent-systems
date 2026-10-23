import { nextTick, ref } from "vue";
import { describe, expect, it, vi } from "vitest";
import type { AnalysisJob, AnnotationRow, PageResult } from "./api";
import { createReviewAnalysisWorkspace } from "./workspace";

function fakeApi() {
  return {
    listSources: vi.fn(async () => ({
      rows: [{ series_id: "1", series_name: "车系一", review_count: 3 }],
      total: 1,
      page: 1,
      page_size: 20,
    })),
    listJobs: vi.fn(async () => ({
      rows: [] as AnalysisJob[],
      total: 0,
      page: 1,
      page_size: 20,
    })),
    createDiscovery: vi.fn(async (_p, body) => ({
      id: "j1",
      status: "queued",
      ...body,
    })),
    createAnnotation: vi.fn(
      async () => ({ id: "j2", status: "queued" }) as AnalysisJob,
    ),
    controlJob: vi.fn(
      async () => ({ id: "j1", status: "paused" }) as AnalysisJob,
    ),
    getProposal: vi.fn(),
    applyProposal: vi.fn(),
    listAnnotations: vi.fn(async () => ({
      rows: [] as AnnotationRow[],
      total: 0,
      page: 1,
      page_size: 20,
    })),
    getAnnotation: vi.fn(),
    getSummary: vi.fn(async () => ({
      annotated_reviews: 0,
      criteria: {},
      labels: {},
    })),
    getMatrixPreview: vi.fn(async () => ({
      job_id: "j2",
      project_id: "p",
      schema_id: "s",
      failed_reviews: 0,
      records: [] as Array<Record<string, unknown>>,
      blockers: [] as Array<{
        month: string;
        series_id: string;
        series_name: string;
        reasons: string[];
        issues: Array<{ code: "missing_sales"; message: string }>;
      }>,
      warnings: [],
      missing_date_items: [],
      stats: {
        source_reviews: 0,
        groups: 0,
        records: 0,
        blocked_groups: 0,
        missing_date_reviews: 0,
        unmentioned_criterion_groups: 0,
      },
    })),
    materializeDataset: vi.fn(async () => ({
      id: "dataset-1",
      name: "评论标注矩阵-j2",
      records: 12,
      sha256: "a".repeat(64),
      created_at: "2026-10-21T00:00:00Z",
    })),
  };
}

describe("review analysis workspace", () => {
  it("loads sources and creates discovery with the active project and schema", async () => {
    const api = fakeApi();
    const project = ref("p1");
    const schema = ref("s1");
    const status = ref<"draft" | "frozen">("draft");
    const workspace = createReviewAnalysisWorkspace(
      api,
      project,
      schema,
      status,
    );
    await workspace.activate();
    workspace.toggleSeries("1");
    workspace.sampleLimit.value = 100;
    await workspace.createDiscovery();
    expect(api.createDiscovery).toHaveBeenCalledWith("p1", {
      schema_id: "s1",
      selected_series_ids: ["1"],
      sample_limit: 100,
    });
  });

  it("filtering annotations does not create a new task", async () => {
    const api = fakeApi();
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("frozen"),
    );
    workspace.filters.value.criterion = "空间";
    await workspace.loadAnnotations();
    expect(api.listAnnotations).toHaveBeenCalled();
    expect(api.createAnnotation).not.toHaveBeenCalled();
    expect(api.getSummary).toHaveBeenCalledWith("p", "");
  });

  it("keeps a local editable proposal and applies with revision", async () => {
    const api = fakeApi();
    api.applyProposal.mockResolvedValue({ revision: 4 });
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("draft"),
    );
    workspace.proposal.value = {
      job_id: "j",
      proposal: {
        criteria: [
          {
            name: "空间",
            labels: ["好", "差"],
            similar_terms: [],
            basis: "依据",
            evidence: [],
          },
        ],
      },
    };
    workspace.proposalDraft.value = JSON.parse(
      JSON.stringify(workspace.proposal.value.proposal.criteria),
    );
    workspace.proposalDraft.value[0].name = "空间实用性";
    await workspace.applyProposal(3);
    expect(api.applyProposal).toHaveBeenCalledWith(
      "p",
      "j",
      3,
      workspace.proposalDraft.value,
    );
  });

  it("keeps completed jobs selectable so their proposal remains reachable", async () => {
    const api = fakeApi();
    api.listJobs.mockResolvedValue({
      rows: [
        {
          id: "done",
          job_type: "criteria_discovery",
          status: "completed",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("draft"),
    );

    await workspace.activate();

    expect(workspace.activeJob.value).toBeNull();
    expect(workspace.selectedJob.value?.id).toBe("done");
  });

  it("searches and pages cached review sources", async () => {
    const api = fakeApi();
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("draft"),
    );
    workspace.sourceQuery.value = "海豹";

    await workspace.loadSources(2);

    expect(api.listSources).toHaveBeenCalledWith("p", "海豹", 2);
  });

  it("requires confirmation before annotating all selected reviews", async () => {
    const api = fakeApi();
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("frozen"),
    );
    workspace.annotationLimit.value = null;
    workspace.selectedSeriesIds.value = ["1"];
    const confirmation = vi.fn(() => false);
    vi.stubGlobal("confirm", confirmation);

    await workspace.createAnnotation();

    expect(confirmation).toHaveBeenCalled();
    expect(api.createAnnotation).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("starts a dated month-series annotation and immediately loads its results", async () => {
    const api = fakeApi();
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("frozen"),
    );
    workspace.selectedSeriesIds.value = ["1"];
    workspace.annotationLimit.value = 300;
    workspace.reviewDateFrom.value = "2026-01-01";
    workspace.reviewDateTo.value = "2026-04-30";
    workspace.annotationSampling.value = "month_series";

    await workspace.createAnnotation();

    expect(api.createAnnotation).toHaveBeenCalledWith("p", {
      schema_id: "s",
      selected_series_ids: ["1"],
      limit: 300,
      review_date_from: "2026-01-01",
      review_date_to: "2026-04-30",
      sampling: "month_series",
    });
    expect(workspace.filters.value.job_id).toBe("j2");
    expect(api.listAnnotations).toHaveBeenCalledWith("p", {
      job_id: "j2",
      page: "1",
      page_size: "20",
    });
    expect(api.getSummary).toHaveBeenCalledWith("p", "j2");
  });

  it("refreshes job-scoped annotation rows while an annotation job is running", async () => {
    const api = fakeApi();
    api.listJobs.mockResolvedValue({
      rows: [
        {
          id: "live",
          job_type: "review_annotation",
          status: "running",
          processed_count: 2,
          total_count: 10,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("frozen"),
    );

    await workspace.activate();

    expect(workspace.filters.value.job_id).toBe("live");
    expect(api.listAnnotations).toHaveBeenCalledWith("p", {
      job_id: "live",
      page: "1",
      page_size: "20",
    });
    workspace.deactivate();
  });

  it("loads a completed job matrix preview and materializes its dataset", async () => {
    const api = fakeApi();
    api.listJobs.mockResolvedValue({
      rows: [
        {
          id: "done",
          job_type: "review_annotation",
          status: "completed",
          processed_count: 12,
          total_count: 12,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    api.getMatrixPreview.mockResolvedValue({
      job_id: "done",
      project_id: "p",
      schema_id: "s",
      failed_reviews: 0,
      records: [{ month: "2026-01", model: "车系一" }],
      blockers: [],
      warnings: [],
      missing_date_items: [],
      stats: {
        source_reviews: 12,
        groups: 1,
        records: 1,
        blocked_groups: 0,
        missing_date_reviews: 0,
        unmentioned_criterion_groups: 0,
      },
    });
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("frozen"),
    );

    await workspace.activate();

    expect(api.getMatrixPreview).toHaveBeenCalledWith("p", "done");
    expect(workspace.matrixPreview.value?.stats.records).toBe(1);

    await workspace.materializeMatrix();

    expect(api.materializeDataset).toHaveBeenCalledWith("p", "done");
    expect(workspace.generatedDataset.value?.records).toBe(12);
    workspace.deactivate();
  });

  it("reloads results when the researcher selects another annotation job", async () => {
    const api = fakeApi();
    api.listJobs.mockResolvedValue({
      rows: [
        { id: "new", job_type: "review_annotation", status: "completed" },
        { id: "old", job_type: "review_annotation", status: "completed" },
      ],
      total: 2,
      page: 1,
      page_size: 20,
    });
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("frozen"),
    );
    await workspace.activate();

    workspace.selectedJobId.value = "old";
    await nextTick();
    await Promise.resolve();

    expect(workspace.filters.value.job_id).toBe("old");
    expect(api.listAnnotations).toHaveBeenLastCalledWith("p", {
      job_id: "old",
      page: "1",
      page_size: "20",
    });
    workspace.deactivate();
  });

  it("starts the retry job returned for a partial failure", async () => {
    const api = fakeApi();
    api.listJobs
      .mockResolvedValueOnce({
        rows: [
          {
            id: "failed",
            job_type: "review_annotation",
            status: "partial_failed",
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      })
      .mockResolvedValueOnce({
        rows: [
          {
            id: "retry",
            job_type: "review_annotation",
            status: "queued",
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      });
    api.controlJob.mockResolvedValue({
      id: "retry",
      job_type: "review_annotation",
      status: "queued",
    });
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("frozen"),
    );
    await workspace.activate();

    await workspace.control("retry-failures");

    expect(api.controlJob).toHaveBeenCalledWith(
      "p",
      "failed",
      "retry-failures",
    );
    expect(workspace.selectedJob.value?.id).toBe("retry");
  });

  it("does not apply active-task controls to a selected completed job", async () => {
    const api = fakeApi();
    api.listJobs.mockResolvedValue({
      rows: [
        { id: "active", job_type: "review_annotation", status: "paused" },
        { id: "done", job_type: "criteria_discovery", status: "completed" },
      ],
      total: 2,
      page: 1,
      page_size: 20,
    });
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("draft"),
    );
    await workspace.activate();
    workspace.selectedJobId.value = "done";

    await workspace.control("cancel");

    expect(api.controlJob).not.toHaveBeenCalled();
  });

  it("keeps selected review counts across source pages", async () => {
    const api = fakeApi();
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("draft"),
    );
    await workspace.activate();
    workspace.toggleSeries("1");
    api.listSources.mockResolvedValueOnce({
      rows: [{ series_id: "2", series_name: "车系二", review_count: 5 }],
      total: 2,
      page: 2,
      page_size: 20,
    });
    await workspace.loadSources(2);
    workspace.toggleSeries("2");

    expect(workspace.availableReviews.value).toBe(8);
    expect(workspace.selectedSeriesIds.value).toEqual(["1", "2"]);
  });

  it("resets state and ignores stale responses after project changes", async () => {
    const api = fakeApi();
    let resolveOld!: (
      value: Awaited<ReturnType<typeof api.listSources>>,
    ) => void;
    api.listSources
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOld = resolve;
          }),
      )
      .mockResolvedValueOnce({
        rows: [{ series_id: "2", series_name: "新项目车系", review_count: 7 }],
        total: 1,
        page: 1,
        page_size: 20,
      });
    const project = ref("p1");
    const workspace = createReviewAnalysisWorkspace(
      api,
      project,
      ref("s"),
      ref("draft"),
    );
    const oldActivation = workspace.activate();
    workspace.filters.value.job_id = "old-job";
    workspace.selectedAnnotation.value = {
      job_id: "old-job",
      review_id: "old-review",
      series_id: "1",
      series_name: "旧车系",
      status: "succeeded",
      annotation_count: 1,
    };
    project.value = "p2";
    await nextTick();
    await Promise.resolve();
    resolveOld({
      rows: [{ series_id: "1", series_name: "旧项目车系", review_count: 3 }],
      total: 1,
      page: 1,
      page_size: 20,
    });
    await oldActivation;
    await nextTick();

    expect(api.listSources).toHaveBeenLastCalledWith("p2", "", 1);
    expect(workspace.sources.value[0]?.series_name).toBe("新项目车系");
    expect(workspace.selectedSeriesIds.value).toEqual([]);
    expect(workspace.filters.value.job_id).toBe("");
    expect(workspace.selectedAnnotation.value).toBeNull();
  });

  it("ignores stale result and detail reads after project changes", async () => {
    const api = fakeApi();
    let resolveRows!: (value: PageResult<AnnotationRow>) => void;
    let resolveDetail!: (value: AnnotationRow) => void;
    api.listAnnotations.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveRows = resolve;
        }),
    );
    api.getAnnotation.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveDetail = resolve;
        }),
    );
    const project = ref("p1");
    const workspace = createReviewAnalysisWorkspace(
      api,
      project,
      ref("s"),
      ref("frozen"),
    );
    await workspace.activate();
    workspace.filters.value.job_id = "old-job";
    const oldRows = workspace.loadAnnotations();
    const oldDetail = workspace.openAnnotation("old-annotation");

    project.value = "p2";
    await nextTick();
    resolveRows({ rows: [], total: 0, page: 1, page_size: 20 });
    resolveDetail({
      job_id: "old-job",
      review_id: "old-review",
      series_id: "1",
      series_name: "旧车系",
      status: "succeeded",
      annotation_count: 1,
    });
    await Promise.all([oldRows, oldDetail]);

    expect(workspace.filters.value.job_id).toBe("");
    expect(workspace.annotations.value).toEqual([]);
    expect(workspace.selectedAnnotation.value).toBeNull();
  });

  it("opens annotation detail with its job-scoped snapshot identity", async () => {
    const api = fakeApi();
    api.getAnnotation.mockResolvedValue({
      job_id: "job-2",
      snapshot_id: "asset-1",
      review_id: "review-1",
      series_id: "1",
      series_name: "车系一",
      status: "cached",
      annotation_count: 0,
    });
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p1"),
      ref("s1"),
      ref("frozen"),
    );

    await workspace.openAnnotation("annotation-1", "job-2", "asset-1");

    expect(api.getAnnotation).toHaveBeenCalledWith(
      "p1",
      "annotation-1",
      "job-2",
      "asset-1",
    );
  });

  it("surfaces proposal conflicts without discarding local edits", async () => {
    const api = fakeApi();
    api.applyProposal.mockRejectedValue(new Error("准则草稿 revision 已变化"));
    const workspace = createReviewAnalysisWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref("draft"),
    );
    workspace.proposal.value = {
      job_id: "j",
      proposal: {
        criteria: [
          {
            name: "空间",
            labels: ["好", "差"],
            similar_terms: [],
            basis: "依据",
            evidence: [],
          },
        ],
      },
    };
    workspace.proposalDraft.value = JSON.parse(
      JSON.stringify(workspace.proposal.value.proposal.criteria),
    );
    workspace.proposalDraft.value[0].name = "空间实用性";

    expect(await workspace.applyProposal(2)).toBe(false);
    expect(workspace.error.value).toContain("revision");
    expect(workspace.proposalDraft.value[0].name).toBe("空间实用性");
  });
});
