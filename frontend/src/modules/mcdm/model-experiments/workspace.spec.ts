import { ref } from "vue";
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
    list: vi.fn(async () => ({
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
});
