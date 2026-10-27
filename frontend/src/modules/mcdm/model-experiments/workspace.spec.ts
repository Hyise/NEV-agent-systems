import { nextTick, ref } from "vue";
import { describe, expect, it, vi } from "vitest";
import type { ModelExperimentRun } from "./api";
import { createModelExperimentWorkspace } from "./workspace";

function fakeApi() {
  return {
    capabilities: vi.fn(async () => [
      {
        key: "ridge",
        label: "Ridge 回归",
        available: true,
        reason: null,
        implementation_version: "1",
      },
      {
        key: "lightgbm",
        label: "LightGBM",
        available: false,
        reason: "未安装",
        implementation_version: "1",
      },
    ]),
    list: vi.fn(async (_projectId: string, _schemaId: string) => ({
      rows: [] as ModelExperimentRun[],
      total: 0,
      page: 1,
      page_size: 20,
    })),
    get: vi.fn(),
    create: vi.fn(
      async () =>
        ({ id: "run-1", status: "queued", progress: 0 }) as ModelExperimentRun,
    ),
    cancel: vi.fn(
      async () =>
        ({
          id: "run-1",
          status: "cancelled",
          progress: 0,
        }) as ModelExperimentRun,
    ),
  };
}

const completedRun = (
  id: string,
  predictions: Array<{
    month: string;
    model: string;
    actual: number;
    predicted: number;
  }> = [],
) =>
  ({
    id,
    project_id: "project-1",
    schema_id: "schema-1",
    status: "completed",
    progress: 1,
    config: {
      model_keys: ["ridge"],
      validation_months: 1,
      test_months: 1,
      seed: 42,
      simulations: 16,
    },
    dataset: {
      snapshot_sha256: "a".repeat(64),
      records: 3,
      source: { id: "dataset-1", name: "矩阵", sha256: "b".repeat(64) },
    },
    result: {
      split: {
        train: ["2026-01", "2026-02"],
        validation: ["2026-03"],
        test: ["2026-04"],
      },
      models: [
        {
          key: "ridge",
          label: "Ridge 回归",
          status: "completed",
          implementation_version: "1",
          metrics: { RMSE: 0.1, WAPE: 0.2, R2: 0.3, MAE: 0.1 },
          predictions,
          metadata: {},
        },
      ],
    },
  }) satisfies ModelExperimentRun;

describe("model experiment workspace", () => {
  it("selects available models and creates a version-bound run", async () => {
    const api = fakeApi();
    const workspace = createModelExperimentWorkspace(
      api,
      ref("project-1"),
      ref("schema-1"),
    );
    await workspace.activate();
    expect(workspace.selectedModelKeys.value).toEqual(["ridge"]);

    workspace.validationMonths.value = 1;
    workspace.testMonths.value = 2;
    workspace.seed.value = 9;
    workspace.simulations.value = 64;
    await workspace.createRun();

    expect(api.create).toHaveBeenCalledWith("project-1", {
      schema_id: "schema-1",
      model_keys: ["ridge"],
      validation_months: 1,
      test_months: 2,
      seed: 9,
      simulations: 64,
    });
    expect(workspace.selectedRun.value?.id).toBe("run-1");
  });

  it("does not allow unavailable models to be selected", async () => {
    const workspace = createModelExperimentWorkspace(
      fakeApi(),
      ref("p"),
      ref("s"),
    );
    await workspace.activate();
    workspace.toggleModel("lightgbm");
    expect(workspace.selectedModelKeys.value).toEqual(["ridge"]);
  });

  it("keeps a training window when only four months are available", async () => {
    const api = fakeApi();
    const workspace = createModelExperimentWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref(4),
    );

    await workspace.activate();

    expect(workspace.validationMonths.value).toBe(1);
    expect(workspace.testMonths.value).toBe(1);
  });

  it("updates split defaults when the month count arrives after activation", async () => {
    const api = fakeApi();
    const months = ref(0);
    const workspace = createModelExperimentWorkspace(
      api,
      ref("p"),
      ref("s"),
      months,
    );
    await workspace.activate();
    expect(workspace.validationMonths.value).toBe(2);

    months.value = 4;
    await nextTick();

    expect(workspace.validationMonths.value).toBe(1);
    expect(workspace.testMonths.value).toBe(1);
  });

  it("rejects a split that leaves no training month before creating a run", async () => {
    const api = fakeApi();
    const workspace = createModelExperimentWorkspace(
      api,
      ref("p"),
      ref("s"),
      ref(4),
    );
    await workspace.activate();
    workspace.validationMonths.value = 2;
    workspace.testMonths.value = 2;

    await workspace.createRun();

    expect(api.create).not.toHaveBeenCalled();
    expect(workspace.error.value).toContain("至少保留 1 个月作为训练集");
  });

  it("loads the full selected run instead of the prediction-free list summary", async () => {
    const api = fakeApi();
    api.list.mockResolvedValue({
      rows: [completedRun("run-1")],
      total: 1,
      page: 1,
      page_size: 20,
    });
    api.get.mockResolvedValue(
      completedRun("run-1", [
        { month: "2026-04", model: "甲", actual: 0.6, predicted: 0.5 },
      ]),
    );
    const workspace = createModelExperimentWorkspace(
      api,
      ref("project-1"),
      ref("schema-1"),
    );

    await workspace.activate();

    expect(api.get).toHaveBeenCalledWith("project-1", "run-1");
    expect(
      workspace.selectedRun.value?.result?.models[0].predictions,
    ).toHaveLength(1);
  });

  it("clears the previous detail before loading another selected run", async () => {
    const api = fakeApi();
    api.list.mockResolvedValue({
      rows: [completedRun("run-1"), completedRun("run-2")],
      total: 2,
      page: 1,
      page_size: 20,
    });
    let releaseSecond!: (run: ModelExperimentRun) => void;
    api.get
      .mockResolvedValueOnce(completedRun("run-1"))
      .mockReturnValueOnce(
        new Promise<ModelExperimentRun>((resolve) => (releaseSecond = resolve)),
      );
    const workspace = createModelExperimentWorkspace(
      api,
      ref("project-1"),
      ref("schema-1"),
    );
    await workspace.activate();

    const loading = workspace.selectRun("run-2");

    expect(workspace.selectedRun.value?.id).toBe("run-2");
    expect(workspace.selectedRun.value?.result?.models[0].predictions).toEqual(
      [],
    );
    releaseSecond(
      completedRun("run-2", [
        { month: "2026-04", model: "乙", actual: 0.4, predicted: 0.5 },
      ]),
    );
    await loading;
    expect(workspace.selectedRun.value?.id).toBe("run-2");
  });

  it("requests and accepts runs only for the active criteria schema", async () => {
    const api = fakeApi();
    api.list.mockResolvedValue({
      rows: [
        completedRun("run-current"),
        { ...completedRun("run-other"), schema_id: "schema-2" },
      ],
      total: 2,
      page: 1,
      page_size: 20,
    });
    api.get.mockResolvedValue(completedRun("run-current"));
    const workspace = createModelExperimentWorkspace(
      api,
      ref("project-1"),
      ref("schema-1"),
    );

    await workspace.activate();

    expect(api.list).toHaveBeenCalledWith("project-1", "schema-1");
    expect(workspace.runs.value.map((run) => run.id)).toEqual(["run-current"]);
  });

  it("rejects a detail response from another criteria schema", async () => {
    const api = fakeApi();
    api.list.mockResolvedValue({
      rows: [completedRun("run-1")],
      total: 1,
      page: 1,
      page_size: 20,
    });
    api.get.mockResolvedValue({
      ...completedRun("run-1"),
      schema_id: "schema-2",
    });
    const workspace = createModelExperimentWorkspace(
      api,
      ref("project-1"),
      ref("schema-1"),
    );

    await workspace.activate();

    expect(workspace.selectedRunDetail.value).toBeNull();
    expect(workspace.error.value).toContain("准则版本不匹配");
  });
});
