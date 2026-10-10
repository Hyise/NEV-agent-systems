import { computed, onBeforeUnmount, ref } from "vue";
import {
  collectionApi,
  type CatalogRun,
  type CatalogRunStatus,
  type CatalogSeriesRow,
  type CatalogStatus,
  type CollectionApi,
  type Page,
} from "./api";

export type CatalogStep = "discovery" | "selection";

const POLL_INTERVAL_MS = 2_000;
const NON_TERMINAL = new Set<CatalogRunStatus>([
  "queued",
  "discovering",
  "publishing",
  "cancelling",
]);

const emptyCatalog = (): Page<CatalogSeriesRow> => ({
  rows: [],
  total: 0,
  page: 1,
  page_size: 20,
});

export function createCatalogFlow(
  client: CollectionApi = collectionApi,
  onJobCreated: () => Promise<void> = async () => undefined,
  registerLifecycle = true,
) {
  const isOpen = ref(false);
  const step = ref<CatalogStep>("discovery");
  const catalogStatus = ref<CatalogStatus | null>(null);
  const discoveryRun = ref<CatalogRun | null>(null);
  const catalog = ref<Page<CatalogSeriesRow>>(emptyCatalog());
  const query = ref("");
  const page = ref(1);
  const selectedSeriesIds = ref<string[]>([]);
  const mode = ref<"verification" | "production">("verification");
  const busy = ref(false);
  const actionBusy = ref(false);
  const error = ref("");
  const productionConfirmPending = ref(false);
  const removedSelectionCount = ref(0);
  const removedSeriesIds = ref<string[]>([]);
  const productionConfirmationText = computed(
    () =>
      `正式采集将处理已选 ${selectedSeriesIds.value.length} 个车系，每车系采集全部评论；` +
      "分页间隔 2～4 秒、车系间隔 5～10 秒。",
  );

  let requestId = 0;
  let lifecycleId = 0;
  let actionId = 0;
  let pollTimer: ReturnType<typeof setTimeout> | undefined;

  function isCurrentAction(token: number, lifecycle: number) {
    return token === actionId && lifecycle === lifecycleId && isOpen.value;
  }

  function clearPoll() {
    if (pollTimer !== undefined) clearTimeout(pollTimer);
    pollTimer = undefined;
  }

  function currentRun() {
    return discoveryRun.value ?? catalogStatus.value?.active_run ?? null;
  }

  function schedulePoll() {
    clearPoll();
    const activeRun = currentRun();
    if (
      !isOpen.value ||
      activeRun === null ||
      !NON_TERMINAL.has(activeRun.status)
    ) {
      return;
    }
    pollTimer = setTimeout(() => {
      pollTimer = undefined;
      void pollDiscovery(activeRun.id);
    }, POLL_INTERVAL_MS);
  }

  async function refreshStatus(token = ++requestId) {
    const next = await client.getCatalogStatus();
    if (token !== requestId || !isOpen.value) return null;
    catalogStatus.value = next;
    discoveryRun.value = next.active_run;
    return next;
  }

  async function reconcileSelection(
    previousBatchId: string | null,
    token: number,
  ) {
    const nextBatchId = catalogStatus.value?.active_batch_id ?? null;
    if (
      previousBatchId === null ||
      previousBatchId === nextBatchId ||
      selectedSeriesIds.value.length === 0
    ) {
      return;
    }
    const valid = await client.listCatalogSelection("");
    if (
      token !== requestId ||
      !isOpen.value ||
      catalogStatus.value?.active_batch_id !== nextBatchId ||
      valid.batch_id !== nextBatchId
    )
      return;
    const validIds = new Set(valid.series_ids);
    removedSeriesIds.value = selectedSeriesIds.value.filter(
      (id) => !validIds.has(id),
    );
    const retained = selectedSeriesIds.value.filter((id) => validIds.has(id));
    removedSelectionCount.value = removedSeriesIds.value.length;
    selectedSeriesIds.value = retained;
  }

  async function loadCatalog() {
    const token = ++requestId;
    const previousBatchId = catalogStatus.value?.active_batch_id ?? null;
    busy.value = true;
    error.value = "";
    try {
      const [nextStatus, nextCatalog] = await Promise.all([
        client.getCatalogStatus(),
        client.listCatalog(query.value, page.value, 20),
      ]);
      if (token !== requestId || !isOpen.value) return;
      catalogStatus.value = nextStatus;
      if (nextStatus.active_run !== null) {
        discoveryRun.value = nextStatus.active_run;
      }
      catalog.value = nextCatalog;
      await reconcileSelection(previousBatchId, token);
    } catch (cause) {
      if (token === requestId) error.value = (cause as Error).message;
    } finally {
      if (token === requestId) {
        busy.value = false;
        schedulePoll();
      }
    }
  }

  async function pollDiscovery(runId: string) {
    const token = ++requestId;
    try {
      const next = await client.getCatalogRun(runId);
      if (token !== requestId || !isOpen.value) return;
      discoveryRun.value = next;
      if (NON_TERMINAL.has(next.status)) {
        schedulePoll();
        return;
      }
      page.value = 1;
      await loadCatalog();
    } catch (cause) {
      if (token === requestId) {
        error.value = (cause as Error).message;
        schedulePoll();
      }
    }
  }

  async function open() {
    isOpen.value = true;
    lifecycleId += 1;
    step.value = "discovery";
    error.value = "";
    productionConfirmPending.value = false;
    const token = ++requestId;
    busy.value = true;
    try {
      await refreshStatus(token);
    } catch (cause) {
      if (token === requestId) error.value = (cause as Error).message;
    } finally {
      if (token === requestId) {
        busy.value = false;
        schedulePoll();
      }
    }
  }

  function close() {
    isOpen.value = false;
    lifecycleId += 1;
    actionId += 1;
    requestId += 1;
    clearPoll();
    actionBusy.value = false;
    busy.value = false;
    productionConfirmPending.value = false;
  }

  async function startDiscovery() {
    const actionToken = ++actionId;
    const lifecycle = lifecycleId;
    actionBusy.value = true;
    error.value = "";
    clearPoll();
    try {
      const next = await client.startCatalogDiscovery();
      if (!isCurrentAction(actionToken, lifecycle)) return;
      discoveryRun.value = next;
      schedulePoll();
    } catch (cause) {
      if (isCurrentAction(actionToken, lifecycle)) {
        error.value = (cause as Error).message;
      }
    } finally {
      if (actionToken === actionId && lifecycle === lifecycleId) {
        actionBusy.value = false;
      }
    }
  }

  async function cancelDiscovery() {
    const activeRun = currentRun();
    if (activeRun === null) return;
    const actionToken = ++actionId;
    const lifecycle = lifecycleId;
    actionBusy.value = true;
    error.value = "";
    try {
      const next = await client.cancelCatalogDiscovery(activeRun.id);
      if (!isCurrentAction(actionToken, lifecycle)) return;
      discoveryRun.value = next;
      schedulePoll();
    } catch (cause) {
      if (isCurrentAction(actionToken, lifecycle)) {
        error.value = (cause as Error).message;
      }
    } finally {
      if (actionToken === actionId && lifecycle === lifecycleId) {
        actionBusy.value = false;
      }
    }
  }

  async function goToSelection() {
    step.value = "selection";
    page.value = 1;
    await loadCatalog();
  }

  async function search() {
    page.value = 1;
    await loadCatalog();
  }

  function toggleSeries(seriesId: string) {
    const index = selectedSeriesIds.value.indexOf(seriesId);
    if (index >= 0) {
      selectedSeriesIds.value = selectedSeriesIds.value.filter(
        (id) => id !== seriesId,
      );
    } else {
      selectedSeriesIds.value = [...selectedSeriesIds.value, seriesId];
    }
    productionConfirmPending.value = false;
  }

  async function selectFiltered() {
    const actionToken = ++actionId;
    const lifecycle = lifecycleId;
    const expectedQuery = query.value;
    const expectedBatchId = catalogStatus.value?.active_batch_id ?? null;
    actionBusy.value = true;
    error.value = "";
    try {
      const result = await client.listCatalogSelection(expectedQuery);
      if (
        !isCurrentAction(actionToken, lifecycle) ||
        query.value !== expectedQuery
      )
        return;
      if (
        result.batch_id !== expectedBatchId ||
        catalogStatus.value?.active_batch_id !== expectedBatchId
      ) {
        error.value = "车系目录已更新，请刷新后重新选择";
        return;
      }
      const selected = new Set(selectedSeriesIds.value);
      selectedSeriesIds.value = [
        ...selectedSeriesIds.value,
        ...result.series_ids.filter((id) => !selected.has(id)),
      ];
      productionConfirmPending.value = false;
    } catch (cause) {
      if (isCurrentAction(actionToken, lifecycle)) {
        error.value = (cause as Error).message;
      }
    } finally {
      if (actionToken === actionId && lifecycle === lifecycleId) {
        actionBusy.value = false;
      }
    }
  }

  function clearSelection() {
    selectedSeriesIds.value = [];
    productionConfirmPending.value = false;
  }

  async function submitJob() {
    const actionToken = ++actionId;
    const lifecycle = lifecycleId;
    actionBusy.value = true;
    error.value = "";
    try {
      await client.createJob({
        mode: mode.value,
        selected_series_ids: [...selectedSeriesIds.value],
      });
      if (isCurrentAction(actionToken, lifecycle)) close();
      await onJobCreated();
    } catch (cause) {
      if (isCurrentAction(actionToken, lifecycle)) {
        error.value = (cause as Error).message;
      }
    } finally {
      if (actionToken === actionId && lifecycle === lifecycleId) {
        actionBusy.value = false;
      }
    }
  }

  async function createJob() {
    const count = selectedSeriesIds.value.length;
    if (count === 0) {
      error.value = "请至少选择 1 个车系";
      return;
    }
    if (mode.value === "verification" && count > 3) {
      error.value = "功能验证最多选择 3 个车系";
      return;
    }
    if (mode.value === "production" && !productionConfirmPending.value) {
      productionConfirmPending.value = true;
      return;
    }
    await submitJob();
  }

  async function confirmProduction() {
    if (mode.value !== "production") return;
    productionConfirmPending.value = true;
    await createJob();
  }

  if (registerLifecycle) onBeforeUnmount(close);

  return {
    isOpen,
    step,
    catalogStatus,
    discoveryRun,
    catalog,
    query,
    page,
    selectedSeriesIds,
    mode,
    busy,
    actionBusy,
    error,
    productionConfirmPending,
    productionConfirmationText,
    removedSelectionCount,
    removedSeriesIds,
    open,
    close,
    startDiscovery,
    cancelDiscovery,
    goToSelection,
    loadCatalog,
    search,
    toggleSeries,
    selectFiltered,
    clearSelection,
    createJob,
    confirmProduction,
  };
}

export type CatalogFlow = ReturnType<typeof createCatalogFlow>;
