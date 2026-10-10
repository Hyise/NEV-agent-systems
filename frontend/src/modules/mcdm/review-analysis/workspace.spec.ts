import { nextTick, ref } from "vue";
import { describe, expect, it, vi } from "vitest";
import type { AnalysisJob } from "./api";
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
      rows: [],
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
