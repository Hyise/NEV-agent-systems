import {
  computed,
  inject,
  nextTick,
  onBeforeUnmount,
  onMounted,
  provide,
  ref,
  type InjectionKey,
} from "vue";
import { api, post } from "./api";
import type {
  Curve,
  DataPage,
  Metric,
  Overview,
  Prediction,
  Project,
  Schema,
} from "./api";

export type Page =
  | "overview"
  | "data"
  | "criteria"
  | "scenario"
  | "shares"
  | "experiments";

export const numberFormat = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 0,
});
export const count = (value: number) => numberFormat.format(value);
export const pct = (value: number) => (value * 100).toFixed(2) + "%";
export const labels = (text: string) =>
  text
    .split(/[\n|｜]/)
    .map((value) => value.trim())
    .filter(Boolean);

export function createWorkspace() {
  const page = ref<Page>("overview");
  const projects = ref<Project[]>([]);
  const projectId = ref("research-archive");
  const schemaId = ref("");
  const schemas = ref<Schema[]>([]);
  const overview = ref<Overview | null>(null);
  const month = ref("");
  const data = ref<DataPage>({
    rows: [],
    total: 0,
    month: null,
    month_models: 0,
    month_total_sales: 0,
  });
  const weights = ref<Curve[]>([]);
  const rationality = ref<Curve[]>([]);
  const predictions = ref<Prediction[]>([]);
  const experiments = ref<{ baseline: Metric[]; ablation: Metric[] }>({
    baseline: [],
    ablation: [],
  });
  const busy = ref(false);
  const saving = ref(false);
  const error = ref("");
  const message = ref("");
  const query = ref("");
  const pageNumber = ref(1);
  const draft = ref<Array<{ name: string; labelsText: string }>>([]);
  const curveKind = ref<"weights" | "rationality">("weights");
  const curveCriteria = ref<string[]>([
    "续航与能耗可靠性",
    "成本效益与全周期价值",
    "性价比合理性",
  ]);
  const mobileNav = ref(false);
  const showCreate = ref(false);
  const projectName = ref("");
  const createMode = ref<"preset" | "custom">("custom");
  const createDialog = ref<HTMLDialogElement>();
  const fileInput = ref<HTMLInputElement>();
  const restoreFocus = ref<HTMLElement | null>(null);
  const isPreset = computed(() => overview.value?.project.mode === "preset");
  const editable = computed(
    () => !isPreset.value && overview.value?.schema.status === "draft",
  );
  const selectedWeights = computed(() =>
    weights.value.find((row) => row.month === month.value),
  );
  const sortedWeights = computed(() =>
    Object.entries(selectedWeights.value?.values ?? {}).sort(
      (left, right) => right[1] - left[1],
    ),
  );
  const topCriteria = computed(() => sortedWeights.value.slice(0, 3));
  const visiblePredictions = computed(() =>
    predictions.value.filter((row) =>
      row.model.toLowerCase().includes(query.value.toLowerCase()),
    ),
  );
  const selectedCurves = computed(() =>
    curveKind.value === "weights" ? weights.value : rationality.value,
  );
  const isDirty = computed(
    () =>
      JSON.stringify(
        draft.value.map((criterion) => ({
          name: criterion.name.trim(),
          labels: labels(criterion.labelsText),
        })),
      ) !== JSON.stringify(overview.value?.schema.criteria ?? []),
  );

  let requestId = 0;
  let toastTimer: ReturnType<typeof setTimeout>;
  let searchTimer: ReturnType<typeof setTimeout>;

  function toast(text: string) {
    message.value = text;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (message.value = ""), 4500);
  }

  function navigate(value: Page) {
    clearTimeout(searchTimer);
    page.value = value;
    mobileNav.value = false;
    query.value = "";
    pageNumber.value = 1;
    if (value === "data") void loadData();
  }

  function resetDraft() {
    draft.value =
      overview.value?.schema.criteria.map((criterion) => ({
        name: criterion.name,
        labelsText: criterion.labels.join(" | "),
      })) ?? [];
  }

  const apiBase = () => `/projects/${encodeURIComponent(projectId.value)}`;
  const schemaQuery = () => `schema_id=${encodeURIComponent(schemaId.value)}`;

  async function loadProjects() {
    projects.value = await api<Project[]>("/projects");
  }

  async function loadWorkspace() {
    const token = ++requestId;
    busy.value = true;
    error.value = "";
    try {
      const base = apiBase();
      const [info, versions] = await Promise.all([
        api<Overview>(
          base + "/overview" + (schemaId.value ? "?" + schemaQuery() : ""),
        ),
        api<Schema[]>(base + "/schemas"),
      ]);
      if (token !== requestId) return;
      const nextMonth = info.months.includes(month.value)
        ? month.value
        : info.months.at(-1) || "";
      const [
        rows,
        weightRows,
        rationalityRows,
        predictionRows,
        experimentRows,
      ] = await Promise.all([
        api<DataPage>(
          base + `/data?schema_id=${info.schema.id}&month=${nextMonth}&page=1`,
        ),
        api<{ rows: Curve[] }>(base + "/curves?kind=weights"),
        api<{ rows: Curve[] }>(base + "/curves?kind=rationality"),
        api<{ rows: Prediction[] }>(base + "/predictions?month=" + nextMonth),
        api<{ baseline: Metric[]; ablation: Metric[] }>(base + "/experiments"),
      ]);
      if (token !== requestId) return;
      overview.value = info;
      schemas.value = versions;
      schemaId.value = info.schema.id;
      month.value = nextMonth;
      data.value = rows;
      weights.value = weightRows.rows;
      rationality.value = rationalityRows.rows;
      predictions.value = predictionRows.rows;
      experiments.value = experimentRows;
      query.value = "";
      pageNumber.value = 1;
      resetDraft();
    } catch (cause) {
      if (token === requestId) {
        overview.value = null;
        error.value = (cause as Error).message;
      }
    } finally {
      if (token === requestId) busy.value = false;
    }
  }

  async function changeProject() {
    schemaId.value = "";
    month.value = "";
    await loadWorkspace();
  }

  async function loadData() {
    const token = ++requestId;
    busy.value = true;
    error.value = "";
    try {
      const [rows, predictionRows] = await Promise.all([
        api<DataPage>(
          apiBase() +
            `/data?${schemaQuery()}&month=${month.value}&search=${encodeURIComponent(query.value)}&page=${pageNumber.value}`,
        ),
        api<{ rows: Prediction[] }>(
          apiBase() + "/predictions?month=" + month.value,
        ),
      ]);
      if (token === requestId) {
        data.value = rows;
        predictions.value = predictionRows.rows;
      }
    } catch (cause) {
      if (token === requestId) error.value = (cause as Error).message;
    } finally {
      if (token === requestId) busy.value = false;
    }
  }

  function searchData() {
    clearTimeout(searchTimer);
    pageNumber.value = 1;
    searchTimer = setTimeout(() => void loadData(), 250);
  }

  function changeMonth() {
    pageNumber.value = 1;
    void loadData();
  }

  function previousPage() {
    if (pageNumber.value <= 1) return;
    pageNumber.value -= 1;
    void loadData();
  }

  function nextPage() {
    if (pageNumber.value * 15 >= data.value.total) return;
    pageNumber.value += 1;
    void loadData();
  }

  async function openCreate(mode: "custom" | "preset" = "custom") {
    restoreFocus.value = document.activeElement as HTMLElement;
    createMode.value = mode;
    projectName.value = "";
    showCreate.value = true;
    await nextTick();
    createDialog.value?.showModal();
  }

  function closeCreate() {
    createDialog.value?.close();
    showCreate.value = false;
    restoreFocus.value?.focus();
  }

  async function createProject() {
    saving.value = true;
    error.value = "";
    try {
      const project = await post<Project>("/projects", {
        name: projectName.value,
        mode: createMode.value,
      });
      await loadProjects();
      projectId.value = project.id;
      schemaId.value = "";
      month.value = "";
      closeCreate();
      page.value = project.mode === "custom" ? "criteria" : "overview";
      await loadWorkspace();
      toast("分析项目已创建");
    } catch (cause) {
      error.value = (cause as Error).message;
    } finally {
      saving.value = false;
    }
  }

  async function saveCriteria(freeze = false) {
    if (!overview.value) return;
    saving.value = true;
    error.value = "";
    try {
      const path = apiBase() + "/schemas/" + schemaId.value;
      const saved = await api<Schema>(path, {
        method: "PUT",
        body: JSON.stringify({
          revision: overview.value.schema.revision,
          criteria: draft.value.map((criterion) => ({
            name: criterion.name,
            labels: labels(criterion.labelsText),
          })),
        }),
      });
      overview.value.schema = saved;
      resetDraft();
      if (freeze) {
        overview.value.schema = await post<Schema>(path + "/freeze", {
          revision: saved.revision,
        });
      }
      await loadWorkspace();
      toast(
        freeze ? "准则版本已冻结，现在可以导入匹配的数据" : "准则草稿已保存",
      );
    } catch (cause) {
      error.value = (cause as Error).message;
    } finally {
      saving.value = false;
    }
  }

  async function forkVersion() {
    saving.value = true;
    error.value = "";
    try {
      const schema = await post<Schema>(
        apiBase() + "/schemas/" + schemaId.value + "/fork",
      );
      schemaId.value = schema.id;
      await loadWorkspace();
      toast("新草稿已建立，原版本和数据保持关联");
    } catch (cause) {
      error.value = (cause as Error).message;
    } finally {
      saving.value = false;
    }
  }

  async function importFile(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    saving.value = true;
    error.value = "";
    try {
      if (file.size > 8_000_000) throw new Error("本机版CSV文件限制为8MB");
      const bytes = await file.arrayBuffer();
      let text: string;
      try {
        text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      } catch {
        throw new Error("请将文件另存为UTF-8编码的CSV后上传");
      }
      const result = await post<{ records: number }>(
        apiBase() + "/schemas/" + schemaId.value + "/datasets",
        { name: file.name, csv_text: text },
      );
      await loadWorkspace();
      toast(`已导入 ${count(result.records)} 条记录`);
    } catch (cause) {
      error.value = (cause as Error).message;
    } finally {
      saving.value = false;
      input.value = "";
    }
  }

  async function download(kind: "report" | "dataset" | "template") {
    try {
      const response = await fetch(
        "/api" + apiBase() + `/export?kind=${kind}&${schemaQuery()}`,
      );
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail || "导出失败");
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download =
        kind === "report"
          ? "研究报告.json"
          : `${kind === "template" ? "数据模板" : "评价矩阵"}.csv`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast("文件已导出");
    } catch (cause) {
      error.value = (cause as Error).message;
    }
  }

  function toggleCriterion(name: string) {
    curveCriteria.value = curveCriteria.value.includes(name)
      ? curveCriteria.value.filter((criterion) => criterion !== name)
      : [...curveCriteria.value, name];
  }

  function beforeUnload(event: BeforeUnloadEvent) {
    if (editable.value && isDirty.value) {
      event.preventDefault();
      event.returnValue = "";
    }
  }

  onMounted(async () => {
    window.addEventListener("beforeunload", beforeUnload);
    try {
      await loadProjects();
      await loadWorkspace();
    } catch (cause) {
      error.value = (cause as Error).message;
    }
  });

  onBeforeUnmount(() => {
    window.removeEventListener("beforeunload", beforeUnload);
    clearTimeout(toastTimer);
    clearTimeout(searchTimer);
  });

  return {
    page,
    projects,
    projectId,
    schemaId,
    schemas,
    overview,
    month,
    data,
    weights,
    rationality,
    predictions,
    experiments,
    busy,
    saving,
    error,
    message,
    query,
    pageNumber,
    draft,
    curveKind,
    curveCriteria,
    mobileNav,
    showCreate,
    projectName,
    createMode,
    createDialog,
    fileInput,
    isPreset,
    editable,
    sortedWeights,
    topCriteria,
    visiblePredictions,
    selectedCurves,
    isDirty,
    navigate,
    resetDraft,
    loadWorkspace,
    changeProject,
    loadData,
    searchData,
    changeMonth,
    previousPage,
    nextPage,
    openCreate,
    closeCreate,
    createProject,
    saveCriteria,
    forkVersion,
    importFile,
    download,
    toggleCriterion,
  };
}

export type Workspace = ReturnType<typeof createWorkspace>;
const workspaceKey: InjectionKey<Workspace> = Symbol("workspace");

export function provideWorkspace(workspace: Workspace) {
  provide(workspaceKey, workspace);
}

export function useWorkspace() {
  const workspace = inject(workspaceKey);
  if (!workspace) throw new Error("Workspace provider is missing");
  return workspace;
}
