import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  reactive,
  ref,
  shallowRef,
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
  type ReviewDeletion,
  type ReviewImportResult,
  type ReviewImportValidation,
} from "./api";

export type ImportStep = "select" | "preview" | "complete";

export interface ReviewImportFilePreview {
  file: File;
  validation: ReviewImportValidation;
}

export interface ReviewImportFileResult extends ReviewImportResult {
  file_name: string;
}

export interface ReviewImportProgress {
  phase: "validating" | "writing" | null;
  completed: number;
  total: number;
  currentFile: string;
}

interface AssetFilterState {
  keyword: string;
  series_id: string;
  source_kind: ReviewAssetSourceKind | "";
  tag: string;
  analysis_enabled: "" | "true" | "false";
  review_date_from: string;
  review_date_to: string;
}

interface ActiveAssetFilter {
  key: keyof AssetFilterState;
  label: string;
}

const emptyFilters = (): AssetFilterState => ({
  keyword: "",
  series_id: "",
  source_kind: "",
  tag: "",
  analysis_enabled: "",
  review_date_from: "",
  review_date_to: "",
});

const emptyImportProgress = (): ReviewImportProgress => ({
  phase: null,
  completed: 0,
  total: 0,
  currentFile: "",
});

const emptyPage = (): Page<ReviewAssetSummary> => ({
  rows: [],
  total: 0,
  page: 1,
  page_size: 20,
});

const emptyDeletionPage = (): Page<ReviewDeletion> => ({
  rows: [],
  total: 0,
  page: 1,
  page_size: 20,
});

export function isSkippedImportPreview(
  preview: ReviewImportFilePreview,
): boolean {
  return (
    !preview.validation.importable.length &&
    !preview.validation.duplicates.length &&
    preview.validation.errors.length > 0 &&
    preview.validation.errors.every((item) => item.type === "empty_file")
  );
}

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
  const filters = reactive<AssetFilterState>(emptyFilters());
  const appliedFilters = reactive<AssetFilterState>(emptyFilters());
  const page = ref(1);
  const pageSize = ref(20);
  const assets = ref<Page<ReviewAssetSummary>>(emptyPage());
  const summary = ref<ReviewAssetSummaryStats | null>(null);
  const detail = ref<ReviewAssetDetail | null>(null);
  const selectedAssetIds = ref<string[]>([]);
  const deletions = ref<Page<ReviewDeletion>>(emptyDeletionPage());
  const deletionPage = ref(1);
  const busy = ref(false);
  const detailBusy = ref(false);
  const deletionBusy = ref(false);
  const actionBusy = ref(false);
  const error = ref("");

  const importOpen = ref(false);
  const importStep = ref<ImportStep>("select");
  const importFilePreviews = shallowRef<ReviewImportFilePreview[]>([]);
  const importFileResults = ref<ReviewImportFileResult[]>([]);
  const importProgress = ref<ReviewImportProgress>(emptyImportProgress());
  const importPreview = ref<ReviewImportValidation | null>(null);
  const importResult = ref<ReviewImportResult | null>(null);
  const importTotals = computed(() => ({
    files: importFilePreviews.value.length,
    importable: importFilePreviews.value.reduce(
      (total, item) => total + item.validation.importable.length,
      0,
    ),
    duplicates: importFilePreviews.value.reduce(
      (total, item) => total + item.validation.duplicates.length,
      0,
    ),
    skipped: importFilePreviews.value.filter(isSkippedImportPreview).length,
    errors: importFilePreviews.value.reduce(
      (total, item) =>
        total +
        item.validation.errors.filter((error) => error.type !== "empty_file")
          .length,
      0,
    ),
  }));
  const skippedImportFiles = computed(() =>
    importFilePreviews.value
      .filter(isSkippedImportPreview)
      .map((preview) => preview.file.webkitRelativePath || preview.file.name),
  );
  const activeFilters = computed<ActiveAssetFilter[]>(() => {
    const result: ActiveAssetFilter[] = [];
    if (appliedFilters.keyword)
      result.push({
        key: "keyword",
        label: `关键词：${appliedFilters.keyword}`,
      });
    if (appliedFilters.series_id)
      result.push({
        key: "series_id",
        label: (() => {
          const series = summary.value?.by_series.find(
            (item) => item.series_id === appliedFilters.series_id,
          );
          return series
            ? `车型：${series.series_name}（${series.series_id}）`
            : `车型 ID：${appliedFilters.series_id}`;
        })(),
      });
    if (appliedFilters.source_kind)
      result.push({
        key: "source_kind",
        label: `来源：${
          appliedFilters.source_kind === "autohome"
            ? "汽车之家采集"
            : "人工导入"
        }`,
      });
    if (appliedFilters.tag)
      result.push({ key: "tag", label: `标签：${appliedFilters.tag}` });
    if (appliedFilters.analysis_enabled)
      result.push({
        key: "analysis_enabled",
        label: `分析状态：${
          appliedFilters.analysis_enabled === "true" ? "参与分析" : "暂不分析"
        }`,
      });
    if (appliedFilters.review_date_from || appliedFilters.review_date_to) {
      const label =
        appliedFilters.review_date_from && appliedFilters.review_date_to
          ? `${appliedFilters.review_date_from} 至 ${appliedFilters.review_date_to}`
          : appliedFilters.review_date_from
            ? `${appliedFilters.review_date_from} 起`
            : `截至 ${appliedFilters.review_date_to}`;
      result.push({
        key: "review_date_from",
        label: `评论时间：${label}`,
      });
    }
    return result;
  });
  const canResetFilters = computed(
    () =>
      activeFilters.value.length > 0 ||
      Object.values(filters).some((value) => value !== ""),
  );

  let active = !registerLifecycle;
  let lifecycleId = 0;
  let listRequestId = 0;
  let detailRequestId = 0;
  let detailContextId = 0;
  let summaryRequestId = 0;
  let deletionRequestId = 0;
  let actionRequestId = 0;

  const current = (lifecycle: number) => active && lifecycle === lifecycleId;

  function query(): ReviewAssetFilters {
    return {
      keyword: appliedFilters.keyword || undefined,
      series_id: appliedFilters.series_id || undefined,
      source_kind: appliedFilters.source_kind || undefined,
      tag: appliedFilters.tag || undefined,
      analysis_enabled:
        appliedFilters.analysis_enabled === ""
          ? undefined
          : appliedFilters.analysis_enabled === "true",
      review_date_from: appliedFilters.review_date_from || undefined,
      review_date_to: appliedFilters.review_date_to || undefined,
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
    if (
      filters.review_date_from &&
      filters.review_date_to &&
      filters.review_date_from > filters.review_date_to
    ) {
      error.value = "评论开始日期不能晚于结束日期";
      return;
    }
    Object.assign(appliedFilters, {
      keyword: filters.keyword.trim(),
      series_id: filters.series_id.trim(),
      source_kind: filters.source_kind,
      tag: filters.tag.trim(),
      analysis_enabled: filters.analysis_enabled,
      review_date_from: filters.review_date_from,
      review_date_to: filters.review_date_to,
    });
    Object.assign(filters, appliedFilters);
    page.value = 1;
    selectedAssetIds.value = [];
    await loadAssets();
  }

  async function focusReview(reviewId: string, seriesId: string) {
    Object.assign(filters, emptyFilters(), {
      keyword: reviewId,
      series_id: seriesId,
    });
    await applyFilters();
  }

  async function resetFilters() {
    Object.assign(filters, emptyFilters());
    Object.assign(appliedFilters, emptyFilters());
    page.value = 1;
    selectedAssetIds.value = [];
    await loadAssets();
  }

  async function selectSeries(seriesId: string) {
    filters.series_id = seriesId;
    appliedFilters.series_id = seriesId;
    page.value = 1;
    selectedAssetIds.value = [];
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
    detailContextId += 1;
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
    detailContextId += 1;
    detailRequestId += 1;
    detail.value = null;
    detailBusy.value = false;
  }

  async function saveMetadata(
    input: Omit<ReviewAssetMetadataInput, "revision">,
  ) {
    if (!detail.value) return;
    const assetId = detail.value.asset_id;
    const detailContext = detailContextId;
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
      await Promise.all([loadAssets(), loadSummary()]);
      if (!current(lifecycle) || request !== actionRequestId) return;
      if (
        detailContext === detailContextId &&
        detail.value?.asset_id === assetId
      ) {
        await openAsset(assetId);
      }
    } catch (cause) {
      if (
        current(lifecycle) &&
        request === actionRequestId &&
        detailContext === detailContextId &&
        detail.value?.asset_id === assetId
      ) {
        error.value = message(cause, "管理信息保存失败");
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
    importFilePreviews.value = [];
    importFileResults.value = [];
    importPreview.value = null;
    importResult.value = null;
    importProgress.value = emptyImportProgress();
    error.value = "";
  }

  function closeImport() {
    actionRequestId += 1;
    importOpen.value = false;
    actionBusy.value = false;
    importProgress.value = emptyImportProgress();
  }

  async function validateImportFiles(files: File[]) {
    if (!files.length) return;
    const request = ++actionRequestId;
    const lifecycle = lifecycleId;
    actionBusy.value = true;
    error.value = "";
    importFilePreviews.value = [];
    importFileResults.value = [];
    importPreview.value = null;
    importResult.value = null;
    importProgress.value = {
      phase: "validating",
      completed: 0,
      total: files.length,
      currentFile: files[0]?.name ?? "",
    };
    try {
      const previews: ReviewImportFilePreview[] = [];
      for (const file of files) {
        importProgress.value.currentFile = file.name;
        const validation = await client.validateReviewImportFile(file);
        if (!current(lifecycle) || request !== actionRequestId) return;
        previews.push({ file, validation });
        importFilePreviews.value = [...previews];
        importProgress.value.completed = previews.length;
      }
      if (!current(lifecycle) || request !== actionRequestId) return;
      importFilePreviews.value = previews;
      importPreview.value = {
        importable: previews.flatMap((item) => item.validation.importable),
        duplicates: previews.flatMap((item) => item.validation.duplicates),
        errors: previews.flatMap((item) =>
          item.validation.errors.filter(
            (validationError) => validationError.type !== "empty_file",
          ),
        ),
        validation_fingerprint: "",
      };
      importStep.value = "preview";
      importProgress.value.phase = null;
      importProgress.value.currentFile = "";
    } catch (cause) {
      if (current(lifecycle) && request === actionRequestId) {
        error.value = message(cause, "导入校验失败");
        importProgress.value.phase = null;
        importProgress.value.currentFile = "";
      }
    } finally {
      if (current(lifecycle) && request === actionRequestId)
        actionBusy.value = false;
    }
  }

  async function confirmImport() {
    if (!importFilePreviews.value.length) return;
    if (importTotals.value.errors) {
      error.value = "文件校验结果仍有错误，修正后才能写入";
      return;
    }
    if (!importTotals.value.importable) {
      error.value = "没有可写入的新评论";
      return;
    }
    const writablePreviews = importFilePreviews.value.filter(
      (preview) => !isSkippedImportPreview(preview),
    );
    const request = ++actionRequestId;
    const lifecycle = lifecycleId;
    actionBusy.value = true;
    error.value = "";
    importProgress.value = {
      phase: "writing",
      completed: 0,
      total: writablePreviews.length,
      currentFile: writablePreviews[0]?.file.name ?? "",
    };
    try {
      const fileResults: ReviewImportFileResult[] = [];
      for (const preview of writablePreviews) {
        importProgress.value.currentFile = preview.file.name;
        const result = await client.confirmReviewImportFile(
          preview.file,
          preview.validation.validation_fingerprint,
        );
        if (!current(lifecycle) || request !== actionRequestId) return;
        fileResults.push({ file_name: preview.file.name, ...result });
        importFileResults.value = [...fileResults];
        importProgress.value.completed = fileResults.length;
      }
      if (!current(lifecycle) || request !== actionRequestId) return;
      importResult.value = {
        imported_count: fileResults.reduce(
          (total, item) => total + item.imported_count,
          0,
        ),
        duplicate_count: fileResults.reduce(
          (total, item) => total + item.duplicate_count,
          0,
        ),
        asset_ids: fileResults.flatMap((item) => item.asset_ids),
      };
      importStep.value = "complete";
      importProgress.value.phase = null;
      importProgress.value.currentFile = "";
      await Promise.all([loadAssets(), loadSummary()]);
    } catch (cause) {
      if (current(lifecycle) && request === actionRequestId) {
        error.value = message(cause, "评论导入失败");
        importProgress.value.phase = null;
        importProgress.value.currentFile = "";
      }
    } finally {
      if (current(lifecycle) && request === actionRequestId)
        actionBusy.value = false;
    }
  }

  async function deleteCurrent(reason: string, confirmedReviewId: string) {
    if (!detail.value) return;
    const target = detail.value;
    const detailContext = detailContextId;
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
      selectedAssetIds.value = selectedAssetIds.value.filter(
        (id) => id !== target.asset_id,
      );
      if (
        detailContext === detailContextId &&
        detail.value?.asset_id === target.asset_id
      ) {
        closeAsset();
      }
      await Promise.all([loadAssets(), loadSummary(), loadDeletions()]);
    } catch (cause) {
      if (
        current(lifecycle) &&
        request === actionRequestId &&
        detailContext === detailContextId &&
        detail.value?.asset_id === target.asset_id
      ) {
        error.value = message(cause, "评论删除失败");
      }
    } finally {
      if (current(lifecycle) && request === actionRequestId)
        actionBusy.value = false;
    }
  }

  async function refreshCurrentDetail() {
    const assetId = detail.value?.asset_id;
    if (assetId) await openAsset(assetId);
  }

  async function loadDeletions(targetPage = deletionPage.value) {
    const request = ++deletionRequestId;
    const lifecycle = lifecycleId;
    deletionBusy.value = true;
    try {
      const result = await client.listReviewDeletions(
        targetPage,
        pageSize.value,
      );
      if (current(lifecycle) && request === deletionRequestId) {
        deletions.value = result;
        deletionPage.value = result.page;
      }
    } catch (cause) {
      if (current(lifecycle) && request === deletionRequestId) {
        error.value = message(cause, "删除记录加载失败");
      }
    } finally {
      if (current(lifecycle) && request === deletionRequestId) {
        deletionBusy.value = false;
      }
    }
  }

  async function allowRecollection(assetId: string) {
    const request = ++actionRequestId;
    const lifecycle = lifecycleId;
    actionBusy.value = true;
    error.value = "";
    try {
      await client.allowReviewRecollection(assetId);
      if (!current(lifecycle) || request !== actionRequestId) return;
      await loadDeletions();
    } catch (cause) {
      if (current(lifecycle) && request === actionRequestId) {
        error.value = message(cause, "解除重采阻止失败");
      }
    } finally {
      if (current(lifecycle) && request === actionRequestId) {
        actionBusy.value = false;
      }
    }
  }

  async function refresh() {
    await Promise.all([loadAssets(), loadSummary(), loadDeletions()]);
  }

  async function activate() {
    active = true;
    lifecycleId += 1;
    await refresh();
  }

  function deactivate() {
    active = false;
    lifecycleId += 1;
    listRequestId += 1;
    detailRequestId += 1;
    summaryRequestId += 1;
    deletionRequestId += 1;
    actionRequestId += 1;
    busy.value = false;
    detailBusy.value = false;
    deletionBusy.value = false;
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
    appliedFilters,
    activeFilters,
    canResetFilters,
    page,
    pageSize,
    assets,
    summary,
    detail,
    selectedAssetIds,
    deletions,
    deletionPage,
    busy,
    detailBusy,
    deletionBusy,
    actionBusy,
    error,
    importOpen,
    importStep,
    importFilePreviews,
    importFileResults,
    importProgress,
    importPreview,
    importResult,
    importTotals,
    skippedImportFiles,
    loadAssets,
    loadSummary,
    applyFilters,
    focusReview,
    resetFilters,
    selectSeries,
    previousPage,
    nextPage,
    openAsset,
    closeAsset,
    refreshCurrentDetail,
    saveMetadata,
    batchUpdate,
    beginImport,
    closeImport,
    validateImportFiles,
    confirmImport,
    deleteCurrent,
    loadDeletions,
    allowRecollection,
    refresh,
    activate,
    deactivate,
  };
}

export type AssetWorkspace = ReturnType<typeof createAssetWorkspace>;
