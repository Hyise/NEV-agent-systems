import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  reactive,
  ref,
} from "vue";
import {
  salesCollectionApi,
  type Page,
  type SalesCollectionApi,
  type SalesCollectionJob,
  type SalesCollectionJobDetail,
  type SalesCollectionOverview,
  type SalesPlatform,
  type SalesRecordFilters,
  type SalesRecordRow,
} from "./api";

const POLL_INTERVAL_MS = 2_000;
const RUNNING = new Set(["queued", "running"]);

const emptyPage = <T>(): Page<T> => ({
  rows: [],
  total: 0,
  page: 1,
  page_size: 20,
});

interface SalesFilterState {
  platform: SalesPlatform | "";
  month: string;
  search: string;
  match_status: SalesRecordRow["match_status"] | "";
}

const emptyFilters = (): SalesFilterState => ({
  platform: "",
  month: "",
  search: "",
  match_status: "",
});

export function createSalesWorkspace(
  client: SalesCollectionApi = salesCollectionApi,
  registerLifecycle = true,
) {
  const overview = ref<SalesCollectionOverview | null>(null);
  const jobs = ref<Page<SalesCollectionJob>>(emptyPage());
  const detail = ref<SalesCollectionJobDetail | null>(null);
  const records = ref<Page<SalesRecordRow>>(emptyPage());
  const busy = ref(false);
  const recordsBusy = ref(false);
  const actionBusy = ref(false);
  const error = ref("");
  const startMonth = ref("2026-01");
  const endMonth = ref("2026-04");
  const selectedPlatforms = ref<SalesPlatform[]>([
    "autohome",
    "dongchedi",
    "yiche",
  ]);
  const filters = reactive<SalesFilterState>(emptyFilters());
  const appliedFilters = reactive<SalesFilterState>(emptyFilters());
  const page = ref(1);
  const pageSize = ref(20);

  let active = !registerLifecycle;
  let lifecycleId = 0;
  let statusRequestId = 0;
  let recordsRequestId = 0;
  let pollTimer: ReturnType<typeof setTimeout> | undefined;

  const current = (lifecycle: number) => active && lifecycle === lifecycleId;

  function clearPoll() {
    if (pollTimer !== undefined) clearTimeout(pollTimer);
    pollTimer = undefined;
  }

  function schedulePoll() {
    clearPoll();
    if (!active || !overview.value?.active_job) return;
    if (!RUNNING.has(overview.value.active_job.status)) return;
    pollTimer = setTimeout(() => {
      pollTimer = undefined;
      void loadStatus();
    }, POLL_INTERVAL_MS);
  }

  async function loadStatus() {
    const request = ++statusRequestId;
    const lifecycle = lifecycleId;
    busy.value = true;
    error.value = "";
    clearPoll();
    try {
      const [nextOverview, nextJobs] = await Promise.all([
        client.getSalesOverview(),
        client.listSalesJobs(1, 20),
      ]);
      if (!current(lifecycle) || request !== statusRequestId) return;
      overview.value = nextOverview;
      jobs.value = nextJobs;
      const selected = nextOverview.active_job ?? nextOverview.latest_job;
      detail.value = selected ? await client.getSalesJob(selected.id) : null;
      if (!current(lifecycle) || request !== statusRequestId) return;
      if (!nextOverview.active_job && selected) await loadRecords();
    } catch (cause) {
      if (current(lifecycle) && request === statusRequestId) {
        error.value = `销量任务加载失败：${(cause as Error).message}`;
      }
    } finally {
      if (current(lifecycle) && request === statusRequestId) {
        busy.value = false;
        schedulePoll();
      }
    }
  }

  function recordQuery(): SalesRecordFilters {
    return {
      platform: appliedFilters.platform || undefined,
      month: appliedFilters.month || undefined,
      search: appliedFilters.search || undefined,
      match_status: appliedFilters.match_status || undefined,
      page: page.value,
      page_size: pageSize.value,
    };
  }

  async function loadRecords() {
    const request = ++recordsRequestId;
    const lifecycle = lifecycleId;
    recordsBusy.value = true;
    try {
      const result = await client.listSalesRecords(recordQuery());
      if (current(lifecycle) && request === recordsRequestId)
        records.value = result;
    } catch (cause) {
      if (current(lifecycle) && request === recordsRequestId) {
        error.value = `销量记录加载失败：${(cause as Error).message}`;
      }
    } finally {
      if (current(lifecycle) && request === recordsRequestId)
        recordsBusy.value = false;
    }
  }

  async function activate() {
    active = true;
    await Promise.all([loadStatus(), loadRecords()]);
  }

  function deactivate() {
    active = false;
    lifecycleId += 1;
    statusRequestId += 1;
    recordsRequestId += 1;
    clearPoll();
  }

  async function startJob() {
    if (!selectedPlatforms.value.length) {
      error.value = "请至少选择一个销量来源平台";
      return;
    }
    actionBusy.value = true;
    error.value = "";
    try {
      await client.createSalesJob({
        start_month: startMonth.value,
        end_month: endMonth.value,
        platforms: [...selectedPlatforms.value],
      });
      await loadStatus();
    } catch (cause) {
      error.value = `销量任务创建失败：${(cause as Error).message}`;
    } finally {
      actionBusy.value = false;
    }
  }

  function togglePlatform(platform: SalesPlatform) {
    selectedPlatforms.value = selectedPlatforms.value.includes(platform)
      ? selectedPlatforms.value.filter((item) => item !== platform)
      : [...selectedPlatforms.value, platform];
  }

  async function applyFilters() {
    Object.assign(appliedFilters, filters);
    page.value = 1;
    await loadRecords();
  }

  async function focusGap(month: string, reviewSeriesId: string) {
    startMonth.value = month;
    endMonth.value = month;
    filters.month = month;
    filters.search = reviewSeriesId;
    filters.match_status = "";
    await applyFilters();
  }

  async function resetFilters() {
    Object.assign(filters, emptyFilters());
    Object.assign(appliedFilters, emptyFilters());
    page.value = 1;
    await loadRecords();
  }

  async function previousPage() {
    if (page.value <= 1) return;
    page.value -= 1;
    await loadRecords();
  }

  async function nextPage() {
    if (page.value * pageSize.value >= records.value.total) return;
    page.value += 1;
    await loadRecords();
  }

  const exportUrl = computed(() =>
    client.salesExportUrl({
      platform: appliedFilters.platform || undefined,
      month: appliedFilters.month || undefined,
      search: appliedFilters.search || undefined,
      match_status: appliedFilters.match_status || undefined,
    }),
  );

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
    overview,
    jobs,
    detail,
    records,
    busy,
    recordsBusy,
    actionBusy,
    error,
    startMonth,
    endMonth,
    selectedPlatforms,
    filters,
    appliedFilters,
    page,
    pageSize,
    exportUrl,
    activate,
    deactivate,
    refresh: loadStatus,
    loadRecords,
    startJob,
    togglePlatform,
    applyFilters,
    focusGap,
    resetFilters,
    previousPage,
    nextPage,
  };
}

export type SalesWorkspace = ReturnType<typeof createSalesWorkspace>;
