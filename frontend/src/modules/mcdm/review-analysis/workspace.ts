import {
  computed,
  inject,
  provide,
  ref,
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
  const selectedSeriesIds = ref<string[]>([]);
  const jobs = ref<AnalysisJob[]>([]);
  const activeJob = ref<AnalysisJob | null>(null);
  const proposal = ref<CriteriaProposal | null>(null);
  const proposalDraft = ref<ProposalCriterion[]>([]);
  const annotations = ref<AnnotationRow[]>([]);
  const selectedAnnotation = ref<AnnotationRow | null>(null);
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

  async function activate() {
    const token = ++generation;
    busy.value = true;
    error.value = "";
    try {
      const [sourcePage, jobPage] = await Promise.all([
        api.listSources(projectId.value),
        api.listJobs(projectId.value),
      ]);
      if (token !== generation) return;
      sources.value = sourcePage.rows;
      jobs.value = jobPage.rows;
      activeJob.value =
        jobs.value.find((job) =>
          ["queued", "running", "paused"].includes(job.status),
        ) ?? null;
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
    selectedSeriesIds.value = [];
    jobs.value = [];
    activeJob.value = null;
    proposal.value = null;
    proposalDraft.value = [];
    annotations.value = [];
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
      schedule();
    } catch (cause) {
      error.value = (cause as Error).message;
    } finally {
      busy.value = false;
    }
  }
  async function createAnnotation() {
    busy.value = true;
    try {
      activeJob.value = await api.createAnnotation(projectId.value, {
        schema_id: schemaId.value,
        selected_series_ids: selectedSeriesIds.value,
        limit: annotationLimit.value,
      });
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
    if (!activeJob.value) return;
    activeJob.value = await api.controlJob(
      projectId.value,
      activeJob.value.id,
      action,
    );
    await activate();
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
  async function loadAnnotations() {
    const params = Object.fromEntries(
      Object.entries(filters.value).filter(([, value]) => value),
    );
    const page = await api.listAnnotations(projectId.value, params);
    annotations.value = page.rows;
  }
  async function openAnnotation(id: string) {
    selectedAnnotation.value = await api.getAnnotation(projectId.value, id);
  }
  return {
    projectId,
    schemaId,
    schemaStatus,
    sources,
    selectedSeriesIds,
    jobs,
    activeJob,
    proposal,
    proposalDraft,
    annotations,
    selectedAnnotation,
    sampleLimit,
    annotationLimit,
    filters,
    busy,
    error,
    availableReviews,
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
