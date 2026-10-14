import {
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
  type CollectionJobDetail,
  type CollectionOverview,
  type Page as ResultPage,
} from "./api";

export type CollectionPage = "acquire" | "assets" | "research";

const RUNNING = new Set(["queued", "discovering", "collecting"]);
const POLL_INTERVAL_MS = 2_000;

const emptyJobs = (): ResultPage<CollectionJob> => ({
  rows: [],
  total: 0,
  page: 1,
  page_size: 20,
});

export function createCollectionWorkspace(
  client: CollectionApi = collectionApi,
  registerLifecycle = true,
) {
  const page = ref<CollectionPage>("acquire");
  const overview = ref<CollectionOverview | null>(null);
  const jobs = ref<ResultPage<CollectionJob>>(emptyJobs());
  const selectedJob = ref<CollectionJobDetail | null>(null);
  const busy = ref(false);
  const actionBusy = ref(false);
  const jobDetailBusy = ref(false);
  const error = ref("");
  const mobileNav = ref(false);

  let active = false;
  let requestId = 0;
  let jobDetailRequestId = 0;
  let pollTimer: ReturnType<typeof setTimeout> | undefined;

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
  }

  async function openJob(jobId: string) {
    const token = ++jobDetailRequestId;
    jobDetailBusy.value = true;
    error.value = "";
    try {
      const result = await client.getJob(jobId);
      if (token === jobDetailRequestId) selectedJob.value = result;
    } catch (cause) {
      if (token === jobDetailRequestId) error.value = (cause as Error).message;
    } finally {
      if (token === jobDetailRequestId) jobDetailBusy.value = false;
    }
  }

  function closeJob() {
    jobDetailRequestId += 1;
    selectedJob.value = null;
    jobDetailBusy.value = false;
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

  async function activate() {
    active = true;
    await loadWorkspace();
  }

  function deactivate() {
    active = false;
    requestId += 1;
    jobDetailRequestId += 1;
    clearPoll();
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
    selectedJob,
    busy,
    actionBusy,
    jobDetailBusy,
    error,
    mobileNav,
    navigate,
    loadWorkspace,
    openJob,
    closeJob,
    pause,
    resume,
    stop,
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
