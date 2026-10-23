import { describe, expect, it, vi } from "vitest";
import type { MatrixHandoff, Project } from "./api";
import {
  createWorkspace,
  resolveInitialProject,
  type ApiClient,
  type PostClient,
} from "./workspace";

const projects: Project[] = [
  {
    id: "research-archive",
    name: "研究归档",
    mode: "preset",
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "custom-1",
    name: "自定义研究",
    mode: "custom",
    created_at: "2026-01-02T00:00:00Z",
  },
];

describe("mcdm project selection", () => {
  it("restores a previously selected project that still exists", () => {
    expect(resolveInitialProject(projects, "custom-1")).toBe("custom-1");
  });

  it("falls back to the preset project when stored selection no longer exists", () => {
    expect(resolveInitialProject(projects, "removed-project")).toBe(
      "research-archive",
    );
  });
});

const overview = (schemaId: string, version: number) => ({
  project: {
    id: "p",
    name: "一至四月实验",
    mode: "custom" as const,
    created_at: "now",
  },
  schema: {
    id: schemaId,
    project_id: "p",
    version,
    revision: 1,
    status: "frozen" as const,
    criteria: [{ name: "空间", labels: ["宽敞", "局促"] }],
  },
  months: [],
  prediction_months: [],
  stats: { records: 0, models: 0, months: 0, criteria: 1 },
  dataset: null,
  source_labels: {},
  notes: [],
  source: null,
});

const blockedHandoff: MatrixHandoff = {
  state: "blocked",
  target_schema_id: "s2",
  target_schema_version: 2,
  target_schema_status: "frozen",
  compatibility: "fingerprint",
  job: {
    id: "job-v1",
    status: "completed",
    source_schema_id: "s1",
    source_schema_version: 1,
  },
  matrix: {
    stats: {
      source_reviews: 300,
      groups: 300,
      records: 259,
      blocked_groups: 41,
      missing_date_reviews: 0,
      unmentioned_criterion_groups: 252,
    },
    failed_reviews: 0,
    blocker_counts: { missing_sales: 41 },
    first_blocker: null,
  },
  dataset: null,
};

function requestFor(handoff: MatrixHandoff) {
  return vi.fn(async (path: string) => {
    if (path.includes("/overview")) return overview("s2", 2);
    if (path.endsWith("/schemas")) return [overview("s2", 2).schema];
    if (path.includes("/review-analysis/handoff")) return handoff;
    if (path.includes("/data?"))
      return {
        rows: [],
        total: 0,
        month: null,
        month_models: 0,
        month_total_sales: 0,
      };
    if (path.includes("/curves")) return { rows: [] };
    if (path.includes("/predictions")) return { rows: [] };
    if (path.includes("/experiments")) return { baseline: [], ablation: [] };
    throw new Error(`unexpected request ${path}`);
  });
}

describe("matrix data handoff", () => {
  it("loads the current schema handoff with the project workspace", async () => {
    const request = requestFor(blockedHandoff);
    const workspace = createWorkspace(
      request as unknown as ApiClient,
      vi.fn() as unknown as PostClient,
      false,
    );
    workspace.projectId.value = "p";
    workspace.schemaId.value = "s2";

    await workspace.loadWorkspace();

    expect(request).toHaveBeenCalledWith(
      "/projects/p/review-analysis/handoff?schema_id=s2",
    );
    expect(workspace.matrixHandoff.value).toEqual(blockedHandoff);
  });

  it("materializes a ready handoff into the selected schema and refreshes", async () => {
    const ready = {
      ...blockedHandoff,
      state: "ready" as const,
      matrix: {
        ...blockedHandoff.matrix!,
        stats: {
          ...blockedHandoff.matrix!.stats,
          records: 300,
          blocked_groups: 0,
        },
        blocker_counts: {},
      },
    };
    const request = requestFor(ready);
    const submit = vi.fn(async () => ({
      id: "dataset-v2",
      name: "评论标注矩阵-job-v1-V2",
      records: 300,
      sha256: "a".repeat(64),
      created_at: "now",
      schema_id: "s2",
    }));
    const workspace = createWorkspace(
      request as unknown as ApiClient,
      submit as unknown as PostClient,
      false,
    );
    workspace.projectId.value = "p";
    workspace.schemaId.value = "s2";
    await workspace.loadWorkspace();

    await workspace.materializeHandoff();

    expect(submit).toHaveBeenCalledWith(
      "/projects/p/review-analysis/jobs/job-v1/datasets",
      { target_schema_id: "s2" },
    );
    expect(
      request.mock.calls.filter(([path]) => path.includes("/overview")),
    ).toHaveLength(2);
  });

  it("clears schema-bound results while another criteria version is loading", async () => {
    let releaseOverview!: (value: ReturnType<typeof overview>) => void;
    const pendingOverview = new Promise<ReturnType<typeof overview>>(
      (resolve) => (releaseOverview = resolve),
    );
    const baseRequest = requestFor(blockedHandoff);
    const request = vi.fn(async (path: string) => {
      if (path.includes("/overview?schema_id=s3")) return pendingOverview;
      if (path.endsWith("/schemas"))
        return [overview("s2", 2).schema, overview("s3", 3).schema];
      if (path.includes("/review-analysis/handoff?schema_id=s3"))
        return { ...blockedHandoff, target_schema_id: "s3" };
      return baseRequest(path);
    });
    const workspace = createWorkspace(
      request as unknown as ApiClient,
      vi.fn() as unknown as PostClient,
      false,
    );
    workspace.projectId.value = "p";
    workspace.schemaId.value = "s2";
    await workspace.loadWorkspace();
    expect(workspace.overview.value?.schema.id).toBe("s2");
    expect(workspace.matrixHandoff.value?.target_schema_id).toBe("s2");

    workspace.schemaId.value = "s3";
    const loading = workspace.loadWorkspace();

    expect(workspace.overview.value).toBeNull();
    expect(workspace.matrixHandoff.value).toBeNull();
    releaseOverview(overview("s3", 3));
    await loading;
    expect(workspace.overview.value?.schema.id).toBe("s3");
    expect(workspace.matrixHandoff.value?.target_schema_id).toBe("s3");
  });
});
