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
  let timer: ReturnType<typeof setTimeout> | undefined;
  const availableReviews = computed(() =>
    sources.value
      .filter((item) => selectedSeriesIds.value.includes(item.series_id))
      .reduce((sum, item) => sum + item.review_count, 0),
  );
  watch(selectedJobId, (jobId) => {
    if (proposal.value?.job_id !== jobId) {
      proposal.value = null;
      proposalDraft.value = [];
    }
  });

  async function loadSources(page = sourcePage.value) {
    const result = await api.listSources(
      projectId.value,
      sourceQuery.value,
      page,
    );
    sources.value = result.rows;
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
  function reset() {
    deactivate();
    sources.value = [];
    sourceQuery.value = "";
    sourcePage.value = 1;
    sourceTotal.value = 0;
    selectedSeriesIds.value = [];
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
  function toggleSeries(id: string) {
    selectedSeriesIds.value = selectedSeriesIds.value.includes(id)
      ? selectedSeriesIds.value.filter((item) => item !== id)
      : [...selectedSeriesIds.value, id];
  }
  async function createDiscovery() {
    busy.value = true;
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
    const target =
      action === "retry-failures" ? selectedJob.value : activeJob.value;
    if (!target) return;
    const result = await api.controlJob(projectId.value, target.id, action);
    selectedJobId.value = result.id;
    await refreshJobs();
    schedule();
  }
  async function loadProposal(jobId: string) {
    proposal.value = await api.getProposal(projectId.value, jobId);
    proposalDraft.value = JSON.parse(
      JSON.stringify(proposal.value.proposal.criteria),
    ) as ProposalCriterion[];
  }
  async function applyProposal(revision: number) {
    if (!proposal.value) return;
    await api.applyProposal(
      projectId.value,
      proposal.value.job_id,
      revision,
      proposalDraft.value,
    );
  }
  async function loadAnnotations(page = 1) {
    annotationPage.value = page;
    const params = Object.fromEntries(
      Object.entries(filters.value).filter(([, value]) => value),
    );
    params.page = String(page);
    params.page_size = "20";
    const result = await api.listAnnotations(projectId.value, params);
    annotations.value = result.rows;
    annotationTotal.value = result.total;
    summary.value = await api.getSummary(projectId.value, filters.value.job_id);
  }
  async function openAnnotation(id: string) {
    selectedAnnotation.value = await api.getAnnotation(projectId.value, id);
  }
  return {
    projectId,
    schemaId,
    schemaStatus,
    sources,
    sourceQuery,
    sourcePage,
    sourceTotal,
    selectedSeriesIds,
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
