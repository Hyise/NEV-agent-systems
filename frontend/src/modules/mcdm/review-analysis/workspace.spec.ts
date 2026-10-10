import { ref } from "vue";
import { describe, expect, it, vi } from "vitest";
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
      rows: [],
      total: 0,
      page: 1,
      page_size: 20,
    })),
    createDiscovery: vi.fn(async (_p, body) => ({
      id: "j1",
      status: "queued",
      ...body,
    })),
    createAnnotation: vi.fn(async () => ({ id: "j2", status: "queued" })),
    controlJob: vi.fn(async () => ({ id: "j1", status: "paused" })),
    getProposal: vi.fn(),
    applyProposal: vi.fn(),
    listAnnotations: vi.fn(async () => ({
      rows: [],
      total: 0,
      page: 1,
      page_size: 20,
    })),
    getAnnotation: vi.fn(),
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
});
