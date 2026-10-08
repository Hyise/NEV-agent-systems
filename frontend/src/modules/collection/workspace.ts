import {
  computed,
  inject,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  provide,
  ref,
  type InjectionKey,
} from "vue";
import {
  collectionApi,
  type CollectionApi,
  type CollectionJob,
  type CollectionOverview,
  type Page as ResultPage,
  type ReviewDetail,
  type ReviewSummary,
  type SeriesRow,
} from "./api";

export type CollectionPage = "overview" | "jobs" | "series" | "reviews";

const RUNNING = new Set(["queued", "discovering", "collecting"]);
const POLL_INTERVAL_MS = 2_000;

const emptyJobs = (): ResultPage<CollectionJob> => ({
  rows: [],
  total: 0,
  page: 1,
  page_size: 20,
});

const emptyPage = <T>(): ResultPage<T> => ({
  rows: [],
  total: 0,
  page: 1,
  page_size: 20,
});

export function createCollectionWorkspace(
  client: CollectionApi = collectionApi,
  registerLifecycle = true,
) {
  const page = ref<CollectionPage>("overview");
  const overview = ref<CollectionOverview | null>(null);
  const jobs = ref<ResultPage<CollectionJob>>(emptyJobs());
  const busy = ref(false);
  const actionBusy = ref(false);
  const error = ref("");
  const mobileNav = ref(false);
  const showCreate = ref(false);
  const jobMode = ref<"verification" | "production">("verification");
  const productionConfirmPending = ref(false);
  const productionConfirmationText =
    "正式采集将处理前 500 个车系、每车系全部评论，并按当前限速持续运行。";
  const series = ref<ResultPage<SeriesRow>>(emptyPage());
  const reviews = ref<ResultPage<ReviewSummary>>(emptyPage());
  const selectedSeries = ref<SeriesRow | null>(null);
  const reviewDetail = ref<ReviewDetail | null>(null);
  const seriesQuery = ref("");
  const seriesPage = ref(1);
  const reviewPage = ref(1);
  const dataBusy = ref(false);
  const selectedSeriesExportUrl = computed(() =>
    selectedSeries.value
      ? `/api/collection/export?series_id=${encodeURIComponent(selectedSeries.value.series_id)}`
      : "",
  );

  let active = false;
  let requestId = 0;
  let pollTimer: ReturnType<typeof setTimeout> | undefined;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  let seriesRequestId = 0;
  let reviewRequestId = 0;
  let detailRequestId = 0;

  function clearPoll() {
    if (pollTimer !== undefined) clearTimeout(pollTimer);
    pollTimer = undefined;
  }

  function hasRunningJob() {
    return Boolean(
      overview.value?.active_job &&
        RUNNING.has(overview.value.active_job.status),
    );
  }

  function schedulePoll() {
    clearPoll();
    if (!active || !hasRunningJob()) return;
    pollTimer = setTimeout(() => {
      pollTimer = undefined;
      void loadWorkspace();
    }, POLL_INTERVAL_MS);
  }

  async function loadWorkspace() {
    const token = ++requestId;
    busy.value = true;
    error.value = "";
    clearPoll();
    try {
      const [nextOverview, nextJobs] = await Promise.all([
        client.getOverview(),
        client.listJobs(1, 20),
      ]);
      if (token !== requestId) return;
      overview.value = nextOverview;
      jobs.value = nextJobs;
    } catch (cause) {
      if (token === requestId) error.value = (cause as Error).message;
    } finally {
      if (token === requestId) {
        busy.value = false;
        schedulePoll();
      }
    }
  }

  function navigate(nextPage: CollectionPage) {
    page.value = nextPage;
    mobileNav.value = false;
    if (nextPage === "series") void loadSeries();
    if (nextPage === "reviews" && selectedSeries.value) void loadReviews();
  }

  async function loadSeries() {
    const token = ++seriesRequestId;
    dataBusy.value = true;
    error.value = "";
    try {
      const result = await client.listSeries(
        seriesQuery.value,
        seriesPage.value,
        20,
      );
      if (token === seriesRequestId) series.value = result;
    } catch (cause) {
      if (token === seriesRequestId) error.value = (cause as Error).message;
    } finally {
      if (token === seriesRequestId) dataBusy.value = false;
    }
  }

  function searchSeries() {
    if (searchTimer !== undefined) clearTimeout(searchTimer);
    seriesPage.value = 1;
    searchTimer = setTimeout(() => {
      searchTimer = undefined;
      void loadSeries();
    }, 250);
  }

  async function loadReviews() {
    if (!selectedSeries.value) {
      reviews.value = emptyPage();
      return;
    }
    const token = ++reviewRequestId;
    dataBusy.value = true;
    error.value = "";
    try {
      const result = await client.listReviews(
        selectedSeries.value.series_id,
        reviewPage.value,
        20,
      );
      if (token === reviewRequestId) reviews.value = result;
    } catch (cause) {
      if (token === reviewRequestId) error.value = (cause as Error).message;
    } finally {
      if (token === reviewRequestId) dataBusy.value = false;
    }
  }

  async function selectSeries(value: SeriesRow) {
    selectedSeries.value = value;
    reviewDetail.value = null;
    reviewPage.value = 1;
    page.value = "reviews";
    mobileNav.value = false;
    await loadReviews();
  }

  async function openReview(reviewId: string) {
    const token = ++detailRequestId;
    dataBusy.value = true;
    error.value = "";
    try {
      const result = await client.getReview(reviewId);
      if (token === detailRequestId) reviewDetail.value = result;
    } catch (cause) {
      if (token === detailRequestId) error.value = (cause as Error).message;
    } finally {
      if (token === detailRequestId) dataBusy.value = false;
    }
  }

  function closeReview() {
    detailRequestId += 1;
    reviewDetail.value = null;
  }

  async function previousSeriesPage() {
    if (seriesPage.value <= 1) return;
    seriesPage.value -= 1;
    await loadSeries();
  }

  async function nextSeriesPage() {
    if (seriesPage.value * 20 >= series.value.total) return;
    seriesPage.value += 1;
    await loadSeries();
  }

  async function previousReviewPage() {
    if (reviewPage.value <= 1) return;
    reviewPage.value -= 1;
    await loadReviews();
  }

  async function nextReviewPage() {
    if (reviewPage.value * 20 >= reviews.value.total) return;
    reviewPage.value += 1;
    await loadReviews();
  }

  async function runAction(
    action: (jobId: string) => Promise<CollectionJob>,
    jobId: string,
  ) {
    actionBusy.value = true;
    error.value = "";
    try {
      await action(jobId);
      await loadWorkspace();
    } catch (cause) {
      error.value = (cause as Error).message;
    } finally {
      actionBusy.value = false;
    }
  }

  const pause = (jobId: string) => runAction(client.pauseJob, jobId);
  const resume = (jobId: string) => runAction(client.resumeJob, jobId);
  const stop = (jobId: string) => runAction(client.stopJob, jobId);

  function openCreate() {
    jobMode.value = "verification";
    productionConfirmPending.value = false;
    showCreate.value = true;
  }

  function closeCreate() {
    showCreate.value = false;
    productionConfirmPending.value = false;
  }

  async function createJob(productionConfirmed = false) {
    if (jobMode.value === "production" && !productionConfirmed) {
      productionConfirmPending.value = true;
      return;
    }
    actionBusy.value = true;
    error.value = "";
    try {
      await client.createJob(
        jobMode.value === "verification"
          ? {
              mode: "verification",
              max_series: 3,
              max_pages_per_series: 2,
            }
          : { mode: "production" },
      );
      closeCreate();
      await loadWorkspace();
    } catch (cause) {
      error.value = (cause as Error).message;
    } finally {
      actionBusy.value = false;
    }
  }

  const confirmProduction = () => createJob(true);

  async function activate() {
    active = true;
    await loadWorkspace();
  }

  function deactivate() {
    active = false;
    requestId += 1;
    clearPoll();
    if (searchTimer !== undefined) clearTimeout(searchTimer);
    searchTimer = undefined;
    seriesRequestId += 1;
    reviewRequestId += 1;
    detailRequestId += 1;
  }

  if (registerLifecycle) {
    let mounted = false;
    onMounted(() => {
      mounted = true;
      void activate();
    });
    onActivated(() => {
      if (mounted && !active) void activate();
    });
    onDeactivated(deactivate);
    onBeforeUnmount(deactivate);
  }

  return {
    page,
    overview,
    jobs,
    busy,
    actionBusy,
    error,
    mobileNav,
    showCreate,
    jobMode,
    productionConfirmPending,
    productionConfirmationText,
    series,
    reviews,
    selectedSeries,
    reviewDetail,
    seriesQuery,
    seriesPage,
    reviewPage,
    dataBusy,
    selectedSeriesExportUrl,
    navigate,
    loadWorkspace,
    pause,
    resume,
    stop,
    openCreate,
    closeCreate,
    createJob,
    confirmProduction,
    loadSeries,
    searchSeries,
    loadReviews,
    selectSeries,
    openReview,
    closeReview,
    previousSeriesPage,
    nextSeriesPage,
    previousReviewPage,
    nextReviewPage,
    activate,
    deactivate,
  };
}

export type CollectionWorkspace = ReturnType<typeof createCollectionWorkspace>;
const collectionWorkspaceKey: InjectionKey<CollectionWorkspace> = Symbol(
  "collection-workspace",
);

export function provideCollectionWorkspace(workspace: CollectionWorkspace) {
  provide(collectionWorkspaceKey, workspace);
}

export function useCollectionWorkspace() {
  const workspace = inject(collectionWorkspaceKey);
  if (!workspace) throw new Error("Collection workspace provider is missing");
  return workspace;
}
