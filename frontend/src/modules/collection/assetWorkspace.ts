import {
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  reactive,
  ref,
} from "vue";
import {
  ApiError,
  collectionApi,
  type Page,
  type ReviewAssetApi,
  type ReviewAssetBatchInput,
  type ReviewAssetDetail,
  type ReviewAssetFilters,
  type ReviewAssetMetadataInput,
  type ReviewAssetSourceKind,
  type ReviewAssetSummary,
  type ReviewAssetSummaryStats,
  type ReviewImportItem,
  type ReviewImportResult,
  type ReviewImportValidation,
} from "./api";

export type ImportStep = "select" | "preview" | "complete";

const emptyPage = (): Page<ReviewAssetSummary> => ({
  rows: [],
  total: 0,
  page: 1,
  page_size: 20,
});

function message(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.status === 404) return "评论资产不存在";
    if (error.status === 410) return "评论资产已永久删除";
    if (error.status === 422 && error.message.startsWith("请求失败")) {
      return "提交内容未通过校验，请检查后重试";
    }
  }
  return error instanceof Error ? error.message : fallback;
}

export function createAssetWorkspace(
  client: ReviewAssetApi = collectionApi,
  registerLifecycle = true,
) {
  const filters = reactive<{
    keyword: string;
    series_id: string;
    source_kind: ReviewAssetSourceKind | "";
    tag: string;
    analysis_enabled: "" | "true" | "false";
  }>({
    keyword: "",
    series_id: "",
    source_kind: "",
    tag: "",
    analysis_enabled: "",
  });
  const page = ref(1);
  const pageSize = ref(20);
  const assets = ref<Page<ReviewAssetSummary>>(emptyPage());
  const summary = ref<ReviewAssetSummaryStats | null>(null);
  const detail = ref<ReviewAssetDetail | null>(null);
  const selectedAssetIds = ref<string[]>([]);
  const busy = ref(false);
  const detailBusy = ref(false);
  const actionBusy = ref(false);
  const error = ref("");

  const importOpen = ref(false);
  const importStep = ref<ImportStep>("select");
  const importItems = ref<ReviewImportItem[]>([]);
  const importPayloadBytes = ref(0);
  const importPreview = ref<ReviewImportValidation | null>(null);
  const importResult = ref<ReviewImportResult | null>(null);

  let active = !registerLifecycle;
  let lifecycleId = 0;
  let listRequestId = 0;
  let detailRequestId = 0;
  let summaryRequestId = 0;
  let actionRequestId = 0;

  const current = (lifecycle: number) => active && lifecycle === lifecycleId;

  function query(): ReviewAssetFilters {
    return {
      keyword: filters.keyword || undefined,
      series_id: filters.series_id || undefined,
      source_kind: filters.source_kind || undefined,
      tag: filters.tag || undefined,
      analysis_enabled:
        filters.analysis_enabled === ""
          ? undefined
          : filters.analysis_enabled === "true",
      page: page.value,
      page_size: pageSize.value,
    };
  }

  async function loadAssets() {
    const request = ++listRequestId;
    const lifecycle = lifecycleId;
    busy.value = true;
    error.value = "";
    try {
      const result = await client.listReviewAssets(query());
      if (current(lifecycle) && request === listRequestId)
        assets.value = result;
    } catch (cause) {
      if (current(lifecycle) && request === listRequestId) {
        error.value = message(cause, "评论资产加载失败");
      }
    } finally {
      if (current(lifecycle) && request === listRequestId) busy.value = false;
    }
  }

  async function loadSummary() {
    const request = ++summaryRequestId;
    const lifecycle = lifecycleId;
    try {
      const result = await client.getReviewAssetSummary();
      if (current(lifecycle) && request === summaryRequestId)
        summary.value = result;
    } catch (cause) {
      if (current(lifecycle) && request === summaryRequestId) {
        error.value = message(cause, "统计信息加载失败");
      }
    }
  }

  async function applyFilters() {
    page.value = 1;
    await loadAssets();
  }

  async function previousPage() {
    if (page.value <= 1) return;
    page.value -= 1;
    await loadAssets();
  }

  async function nextPage() {
    if (page.value * pageSize.value >= assets.value.total) return;
    page.value += 1;
    await loadAssets();
  }

  async function openAsset(assetId: string) {
    const request = ++detailRequestId;
    const lifecycle = lifecycleId;
    detail.value = null;
    detailBusy.value = true;
    error.value = "";
    try {
      const result = await client.getReviewAsset(assetId);
      if (current(lifecycle) && request === detailRequestId)
        detail.value = result;
    } catch (cause) {
      if (current(lifecycle) && request === detailRequestId) {
        const detailError = message(cause, "评论详情加载失败");
        error.value = detailError;
        if (
          cause instanceof ApiError &&
          (cause.status === 404 || cause.status === 410)
        ) {
          await loadAssets();
          await loadSummary();
          if (current(lifecycle) && request === detailRequestId) {
            error.value = detailError;
          }
        }
      }
    } finally {
      if (current(lifecycle) && request === detailRequestId)
        detailBusy.value = false;
    }
  }

  function closeAsset() {
    detailRequestId += 1;
    detail.value = null;
    detailBusy.value = false;
  }

  async function saveMetadata(
    input: Omit<ReviewAssetMetadataInput, "revision">,
  ) {
    if (!detail.value) return;
    const assetId = detail.value.asset_id;
    const request = ++actionRequestId;
    const lifecycle = lifecycleId;
    actionBusy.value = true;
    error.value = "";
    try {
      await client.updateReviewAssetMetadata(assetId, {
        ...input,
        revision: detail.value.revision,
      });
      if (!current(lifecycle) || request !== actionRequestId) return;
      await Promise.all([openAsset(assetId), loadAssets(), loadSummary()]);
    } catch (cause) {
      if (current(lifecycle) && request === actionRequestId) {
        error.value = message(cause, "管理信息保存失败");
        if (cause instanceof ApiError && cause.status === 409) {
          await openAsset(assetId);
          error.value = message(cause, "管理信息保存失败");
        }
      }
    } finally {
      if (current(lifecycle) && request === actionRequestId)
        actionBusy.value = false;
    }
  }

  async function batchUpdate(input: Omit<ReviewAssetBatchInput, "asset_ids">) {
    if (!selectedAssetIds.value.length) {
      error.value = "请至少选择一条评论";
      return;
    }
    const request = ++actionRequestId;
    const lifecycle = lifecycleId;
    actionBusy.value = true;
    error.value = "";
    try {
      await client.batchUpdateReviewAssetMetadata({
        ...input,
        asset_ids: [...selectedAssetIds.value],
      });
      if (!current(lifecycle) || request !== actionRequestId) return;
      selectedAssetIds.value = [];
      await Promise.all([loadAssets(), loadSummary()]);
    } catch (cause) {
      if (current(lifecycle) && request === actionRequestId) {
        error.value = message(cause, "批量修改失败");
      }
    } finally {
      if (current(lifecycle) && request === actionRequestId)
        actionBusy.value = false;
    }
  }

  function beginImport() {
    importOpen.value = true;
    importStep.value = "select";
    importItems.value = [];
    importPayloadBytes.value = 0;
    importPreview.value = null;
    importResult.value = null;
    error.value = "";
  }

  function closeImport() {
    actionRequestId += 1;
    importOpen.value = false;
    actionBusy.value = false;
  }

  async function validateImport(
    items: ReviewImportItem[],
    payloadBytes: number,
  ) {
    const request = ++actionRequestId;
    const lifecycle = lifecycleId;
    actionBusy.value = true;
    error.value = "";
    importItems.value = items;
    importPayloadBytes.value = payloadBytes;
    try {
      const result = await client.validateReviewImport({
        items,
        payload_bytes: payloadBytes,
      });
      if (!current(lifecycle) || request !== actionRequestId) return;
      importPreview.value = result;
      importStep.value = "preview";
    } catch (cause) {
      if (current(lifecycle) && request === actionRequestId) {
        error.value = message(cause, "导入校验失败");
      }
    } finally {
      if (current(lifecycle) && request === actionRequestId)
        actionBusy.value = false;
    }
  }

  async function confirmImport() {
    if (!importPreview.value) return;
    const request = ++actionRequestId;
    const lifecycle = lifecycleId;
    actionBusy.value = true;
    error.value = "";
    try {
      const result = await client.confirmReviewImport({
        items: importItems.value,
        payload_bytes: importPayloadBytes.value,
        validation_fingerprint: importPreview.value.validation_fingerprint,
      });
      if (!current(lifecycle) || request !== actionRequestId) return;
      importResult.value = result;
      importStep.value = "complete";
      await Promise.all([loadAssets(), loadSummary()]);
    } catch (cause) {
      if (current(lifecycle) && request === actionRequestId) {
        error.value = message(cause, "评论导入失败");
        if (cause instanceof ApiError && cause.status === 409) {
          importStep.value = "select";
          importPreview.value = null;
        }
      }
    } finally {
      if (current(lifecycle) && request === actionRequestId)
        actionBusy.value = false;
    }
  }

  async function deleteCurrent(reason: string, confirmedReviewId: string) {
    if (!detail.value) return;
    const target = detail.value;
    const request = ++actionRequestId;
    const lifecycle = lifecycleId;
    actionBusy.value = true;
    error.value = "";
    try {
      await client.deleteReviewAsset(target.asset_id, {
        expected_content_hash: target.content_hash,
        confirmed_review_id: confirmedReviewId,
        reason,
        confirm: true,
      });
      if (!current(lifecycle) || request !== actionRequestId) return;
      closeAsset();
      selectedAssetIds.value = selectedAssetIds.value.filter(
        (id) => id !== target.asset_id,
      );
      await Promise.all([loadAssets(), loadSummary()]);
    } catch (cause) {
      if (current(lifecycle) && request === actionRequestId) {
        error.value = message(cause, "评论删除失败");
      }
    } finally {
      if (current(lifecycle) && request === actionRequestId)
        actionBusy.value = false;
    }
  }

  async function activate() {
    active = true;
    lifecycleId += 1;
    await Promise.all([loadAssets(), loadSummary()]);
  }

  function deactivate() {
    active = false;
    lifecycleId += 1;
    listRequestId += 1;
    detailRequestId += 1;
    summaryRequestId += 1;
    actionRequestId += 1;
    busy.value = false;
    detailBusy.value = false;
    actionBusy.value = false;
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
    filters,
    page,
    pageSize,
    assets,
    summary,
    detail,
    selectedAssetIds,
    busy,
    detailBusy,
    actionBusy,
    error,
    importOpen,
    importStep,
    importItems,
    importPayloadBytes,
    importPreview,
    importResult,
    loadAssets,
    loadSummary,
    applyFilters,
    previousPage,
    nextPage,
    openAsset,
    closeAsset,
    saveMetadata,
    batchUpdate,
    beginImport,
    closeImport,
    validateImport,
    confirmImport,
    deleteCurrent,
    activate,
    deactivate,
  };
}

export type AssetWorkspace = ReturnType<typeof createAssetWorkspace>;
