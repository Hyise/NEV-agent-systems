import {
  computed,
  inject,
  provide,
  ref,
  watch,
  type InjectionKey,
  type Ref,
} from "vue";
import type {
  ModelCapability,
  ModelExperimentApi,
  ModelExperimentRun,
} from "./api";

export function createModelExperimentWorkspace(
  api: ModelExperimentApi,
  projectId: Ref<string>,
  schemaId: Ref<string>,
) {
  const capabilities = ref<ModelCapability[]>([]);
  const runs = ref<ModelExperimentRun[]>([]);
  const selectedRunId = ref("");
  const selectedRun = computed(
    () => runs.value.find((run) => run.id === selectedRunId.value) ?? null,
  );
  const selectedModelKeys = ref<string[]>([]);
  const validationMonths = ref(2);
  const testMonths = ref(2);
  const seed = ref(42);
  const simulations = ref(128);
  const busy = ref(false);
  const error = ref("");
  let active = false;
  let generation = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;

  function selectDefaults() {
    if (selectedModelKeys.value.length) return;
    selectedModelKeys.value = capabilities.value
      .filter((item) => item.available)
      .map((item) => item.key);
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    const running = runs.value.some((run) =>
      ["queued", "running"].includes(run.status),
    );
    if (active && running) timer = setTimeout(() => void activate(), 1200);
  }

  async function activate() {
    active = true;
    const token = ++generation;
    busy.value = true;
    error.value = "";
    try {
      const [modelRows, runPage] = await Promise.all([
        api.capabilities(projectId.value),
        api.list(projectId.value),
      ]);
      if (token !== generation) return;
      capabilities.value = modelRows;
      runs.value = runPage.rows;
      selectDefaults();
      if (
        !selectedRunId.value ||
        !runs.value.some((run) => run.id === selectedRunId.value)
      )
        selectedRunId.value = runs.value[0]?.id ?? "";
      schedule();
    } catch (cause) {
      if (token === generation) error.value = (cause as Error).message;
    } finally {
      if (token === generation) busy.value = false;
    }
  }

  function deactivate() {
    active = false;
    generation += 1;
    if (timer) clearTimeout(timer);
    timer = undefined;
  }

  function toggleModel(key: string) {
    const capability = capabilities.value.find((item) => item.key === key);
    if (!capability?.available) return;
    selectedModelKeys.value = selectedModelKeys.value.includes(key)
      ? selectedModelKeys.value.filter((item) => item !== key)
      : [...selectedModelKeys.value, key];
  }

  async function createRun() {
    if (!selectedModelKeys.value.length) {
      error.value = "请至少选择一个当前可运行的模型";
      return;
    }
    busy.value = true;
    error.value = "";
    try {
      const run = await api.create(projectId.value, {
        schema_id: schemaId.value,
        model_keys: selectedModelKeys.value,
        validation_months: validationMonths.value,
        test_months: testMonths.value,
        seed: seed.value,
        simulations: simulations.value,
      });
      runs.value = [run, ...runs.value.filter((item) => item.id !== run.id)];
      selectedRunId.value = run.id;
      schedule();
    } catch (cause) {
      error.value = (cause as Error).message;
    } finally {
      busy.value = false;
    }
  }

  async function cancelRun() {
    if (!selectedRun.value) return;
    try {
      const run = await api.cancel(projectId.value, selectedRun.value.id);
      runs.value = runs.value.map((item) => (item.id === run.id ? run : item));
    } catch (cause) {
      error.value = (cause as Error).message;
    }
  }

  watch([projectId, schemaId], () => {
    const reload = active;
    deactivate();
    capabilities.value = [];
    runs.value = [];
    selectedRunId.value = "";
    selectedModelKeys.value = [];
    error.value = "";
    if (reload) void activate();
  });

  return {
    capabilities,
    runs,
    selectedRunId,
    selectedRun,
    selectedModelKeys,
    validationMonths,
    testMonths,
    seed,
    simulations,
    busy,
    error,
    activate,
    deactivate,
    toggleModel,
    createRun,
    cancelRun,
  };
}

export type ModelExperimentWorkspace = ReturnType<
  typeof createModelExperimentWorkspace
>;
const key: InjectionKey<ModelExperimentWorkspace> = Symbol(
  "model-experiment-workspace",
);
export const provideModelExperimentWorkspace = (
  workspace: ModelExperimentWorkspace,
) => provide(key, workspace);
export function useModelExperimentWorkspace() {
  const workspace = inject(key);
  if (!workspace)
    throw new Error("Model experiment workspace provider is missing");
  return workspace;
}
