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
  AnalysisJob,
  AnnotationRow,
  CriteriaProposal,
  ProposalCriterion,
  ReviewAnalysisApi,
  ReviewSource,
} from "./api";

export function createReviewAnalysisWorkspace(
  api: ReviewAnalysisApi,
  projectId: Ref<string>,
  schemaId: Ref<string>,
  schemaStatus: Ref<"draft" | "frozen">,
) {
  const sources = ref<ReviewSource[]>([]);
  const sourceQuery = ref("");
  const sourcePage = ref(1);
  const sourceTotal = ref(0);
  const selectedSeriesIds = ref<string[]>([]);
  const selectedSources = ref<Record<string, ReviewSource>>({});
  const jobs = ref<AnalysisJob[]>([]);
  const activeJob = ref<AnalysisJob | null>(null);
  const selectedJobId = ref("");
  const selectedJob = computed(
    () => jobs.value.find((job) => job.id === selectedJobId.value) ?? null,
  );
  const proposal = ref<CriteriaProposal | null>(null);
  const proposalDraft = ref<ProposalCriterion[]>([]);
  const annotations = ref<AnnotationRow[]>([]);
  const selectedAnnotation = ref<AnnotationRow | null>(null);
  const annotationPage = ref(1);
  const annotationTotal = ref(0);
  const summary = ref({
    annotated_reviews: 0,
    criteria: {} as Record<string, number>,
    labels: {} as Record<string, number>,
  });
  const sampleLimit = ref(1500);
  const annotationLimit = ref<number | null>(100);
  const filters = ref({
    job_id: "",
    series_id: "",
    criterion: "",
    label: "",
    status: "",
  });
  const busy = ref(false);
  const error = ref("");
  let generation = 0;
  let activated = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const availableReviews = computed(() =>
    Object.values(selectedSources.value).reduce(
      (sum, item) => sum + item.review_count,
      0,
    ),
  );
  watch(selectedJobId, (jobId) => {
    if (proposal.value?.job_id !== jobId) {
      proposal.value = null;
      proposalDraft.value = [];
    }
  });

  function rememberSelected(rows: ReviewSource[]) {
    const next = { ...selectedSources.value };
    for (const source of rows) {
      if (selectedSeriesIds.value.includes(source.series_id))
        next[source.series_id] = source;
    }
    selectedSources.value = next;
  }

  async function guarded<T>(
    operation: () => Promise<T>,
  ): Promise<T | undefined> {
    busy.value = true;
    error.value = "";
    try {
      return await operation();
    } catch (cause) {
      error.value = (cause as Error).message;
      return undefined;
    } finally {
      busy.value = false;
    }
  }

  async function loadSources(page = sourcePage.value) {
    const result = await guarded(() =>
      api.listSources(projectId.value, sourceQuery.value, page),
    );
    if (!result) return;
    sources.value = result.rows;
    rememberSelected(result.rows);
    sourcePage.value = result.page;
    sourceTotal.value = result.total;
  }

  async function refreshJobs() {
    const result = await api.listJobs(projectId.value);
    jobs.value = result.rows;
    activeJob.value =
      jobs.value.find((job) =>
        ["queued", "running", "paused"].includes(job.status),
      ) ?? null;
    if (
      !selectedJobId.value ||
      !jobs.value.some((job) => job.id === selectedJobId.value)
    ) {
      selectedJobId.value = activeJob.value?.id ?? jobs.value[0]?.id ?? "";
    }
  }

  async function activate() {
    activated = true;
    const token = ++generation;
    busy.value = true;
    error.value = "";
    try {
      const [sourceResult, jobPage] = await Promise.all([
        api.listSources(projectId.value, sourceQuery.value, sourcePage.value),
        api.listJobs(projectId.value),
      ]);
      if (token !== generation) return;
      sources.value = sourceResult.rows;
      rememberSelected(sourceResult.rows);
      sourcePage.value = sourceResult.page;
      sourceTotal.value = sourceResult.total;
      jobs.value = jobPage.rows;
      activeJob.value =
        jobs.value.find((job) =>
          ["queued", "running", "paused"].includes(job.status),
        ) ?? null;
      if (
        !selectedJobId.value ||
        !jobs.value.some((job) => job.id === selectedJobId.value)
      ) {
        selectedJobId.value = activeJob.value?.id ?? jobs.value[0]?.id ?? "";
      }
      schedule();
    } catch (cause) {
      if (token === generation) error.value = (cause as Error).message;
    } finally {
      if (token === generation) busy.value = false;
    }
  }
  function deactivate() {
    activated = false;
    generation++;
    if (timer) clearTimeout(timer);
    timer = undefined;
  }
  function schedule() {
    if (timer) clearTimeout(timer);
    if (
      activeJob.value &&
      ["queued", "running"].includes(activeJob.value.status)
    )
      timer = setTimeout(() => void activate(), 1500);
  }
  function clearState() {
    sources.value = [];
    sourceQuery.value = "";
    sourcePage.value = 1;
    sourceTotal.value = 0;
    selectedSeriesIds.value = [];
    selectedSources.value = {};
    jobs.value = [];
    activeJob.value = null;
    selectedJobId.value = "";
    proposal.value = null;
    proposalDraft.value = [];
    annotations.value = [];
    annotationPage.value = 1;
    annotationTotal.value = 0;
    summary.value = { annotated_reviews: 0, criteria: {}, labels: {} };
  }
  function reset() {
    deactivate();
    clearState();
  }
  function toggleSeries(id: string) {
    if (selectedSeriesIds.value.includes(id)) {
      selectedSeriesIds.value = selectedSeriesIds.value.filter(
        (item) => item !== id,
      );
      const next = { ...selectedSources.value };
      delete next[id];
      selectedSources.value = next;
      return;
    }
    selectedSeriesIds.value = [...selectedSeriesIds.value, id];
    const source = sources.value.find((item) => item.series_id === id);
    if (source)
      selectedSources.value = { ...selectedSources.value, [id]: source };
  }
  async function createDiscovery() {
    busy.value = true;
    error.value = "";
    try {
      activeJob.value = await api.createDiscovery(projectId.value, {
        schema_id: schemaId.value,
        selected_series_ids: selectedSeriesIds.value,
        sample_limit: sampleLimit.value,
      });
      selectedJobId.value = activeJob.value.id;
      jobs.value = [activeJob.value, ...jobs.value];
      schedule();
    } catch (cause) {
      error.value = (cause as Error).message;
    } finally {
      busy.value = false;
    }
  }
  async function createAnnotation() {
    if (annotationLimit.value === null) {
      const confirmed =
        typeof globalThis.confirm !== "function" ||
        globalThis.confirm(
          "将对已选车系的 " +
            availableReviews.value +
            " 条评论逐条调用模型，确认继续吗？",
        );
      if (!confirmed) return;
    }
    busy.value = true;
    error.value = "";
    try {
      activeJob.value = await api.createAnnotation(projectId.value, {
        schema_id: schemaId.value,
        selected_series_ids: selectedSeriesIds.value,
        limit: annotationLimit.value,
      });
      selectedJobId.value = activeJob.value.id;
      jobs.value = [activeJob.value, ...jobs.value];
      schedule();
    } catch (cause) {
      error.value = (cause as Error).message;
    } finally {
      busy.value = false;
    }
  }
  async function control(
    action: "pause" | "resume" | "cancel" | "retry-failures",
  ) {
    const target = selectedJob.value;
    if (!target) return;
    if (
      action !== "retry-failures" &&
      !["queued", "running", "paused"].includes(target.status)
    )
      return;
    await guarded(async () => {
      const result = await api.controlJob(projectId.value, target.id, action);
      selectedJobId.value = result.id;
      await refreshJobs();
      schedule();
    });
  }
  async function loadProposal(jobId: string) {
    const result = await guarded(() => api.getProposal(projectId.value, jobId));
    if (!result) return;
    proposal.value = result;
    proposalDraft.value = JSON.parse(
      JSON.stringify(result.proposal.criteria),
    ) as ProposalCriterion[];
  }
  async function applyProposal(revision: number): Promise<boolean> {
    if (!proposal.value) return false;
    const applied = await guarded(() =>
      api.applyProposal(
        projectId.value,
        proposal.value!.job_id,
        revision,
        proposalDraft.value,
      ),
    );
    return applied !== undefined;
  }
  async function loadAnnotations(page = 1) {
    const params = Object.fromEntries(
      Object.entries(filters.value).filter(([, value]) => value),
    );
    params.page = String(page);
    params.page_size = "20";
    const result = await guarded(() =>
      Promise.all([
        api.listAnnotations(projectId.value, params),
        api.getSummary(projectId.value, filters.value.job_id),
      ]),
    );
    if (!result) return;
    annotationPage.value = page;
    annotations.value = result[0].rows;
    annotationTotal.value = result[0].total;
    summary.value = result[1];
  }
  async function openAnnotation(id: string) {
    const result = await guarded(() => api.getAnnotation(projectId.value, id));
    if (result) selectedAnnotation.value = result;
  }
  watch([projectId, schemaId], () => {
    const reload = activated;
    deactivate();
    clearState();
    if (reload) void activate();
  });
  return {
    projectId,
    schemaId,
    schemaStatus,
    sources,
    sourceQuery,
    sourcePage,
    sourceTotal,
    selectedSeriesIds,
    selectedSources,
    jobs,
    activeJob,
    selectedJobId,
    selectedJob,
    proposal,
    proposalDraft,
    annotations,
    selectedAnnotation,
    annotationPage,
    annotationTotal,
    summary,
    sampleLimit,
    annotationLimit,
    filters,
    busy,
    error,
    availableReviews,
    loadSources,
    activate,
    deactivate,
    reset,
    toggleSeries,
    createDiscovery,
    createAnnotation,
    control,
    loadProposal,
    applyProposal,
    loadAnnotations,
    openAnnotation,
  };
}

export type ReviewAnalysisWorkspace = ReturnType<
  typeof createReviewAnalysisWorkspace
>;
const key: InjectionKey<ReviewAnalysisWorkspace> = Symbol(
  "review-analysis-workspace",
);
export const provideReviewAnalysisWorkspace = (
  workspace: ReviewAnalysisWorkspace,
) => provide(key, workspace);
export function useReviewAnalysisWorkspace() {
  const workspace = inject(key);
  if (!workspace)
    throw new Error("Review analysis workspace provider is missing");
  return workspace;
}
