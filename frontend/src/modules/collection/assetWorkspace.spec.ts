import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  collectionApi,
  type Page,
  type ReviewAssetApi,
  type ReviewAssetDetail,
  type ReviewAssetMetadata,
  type ReviewAssetSummary,
  type ReviewDeletion,
  type ReviewImportValidation,
} from "./api";
import { createAssetWorkspace } from "./assetWorkspace";

const asset = (id = "autohome:r1"): ReviewAssetSummary => ({
  asset_id: id,
  review_id: id.split(":")[1]!,
  series_id: "5769",
  series_name: "Model Y",
  source_kind: id.startsWith("manual") ? "manual_import" : "autohome",
  platform: id.startsWith("manual") ? "manual" : "autohome",
  source_url: null,
  content_hash: "a".repeat(64),
  excerpt: "空间宽敞，续航稳定",
  first_collected_at: "2026-10-14T08:00:00+00:00",
  last_confirmed_at: "2026-10-14T08:00:00+00:00",
  analysis_enabled: true,
  tags: [],
  note: "",
  revision: 1,
  metadata_updated_at: "2026-10-14T08:00:00+00:00",
});

const detail = (id = "autohome:r1"): ReviewAssetDetail => ({
  ...asset(id),
  original_review: { feeling_summary: "完整评论" },
  reference_count: 0,
});

const resultPage = (
  rows: ReviewAssetSummary[],
  page = 1,
): Page<ReviewAssetSummary> => ({
  rows,
  total: rows.length,
  page,
  page_size: 20,
});

const summary = {
  total: 2,
  analysis_enabled: 2,
  analysis_disabled: 0,
  by_source: [{ source_kind: "autohome", count: 2 }],
  by_series: [
    {
      series_id: "5769",
      series_name: "Model Y",
      count: 2,
      analysis_enabled: 2,
    },
  ],
};

function api(overrides: Partial<ReviewAssetApi> = {}): ReviewAssetApi {
  return {
    listReviewAssets: vi.fn().mockResolvedValue(resultPage([asset()])),
    getReviewAsset: vi.fn().mockResolvedValue(detail()),
    updateReviewAssetMetadata: vi.fn().mockResolvedValue({
      asset_id: "autohome:r1",
      analysis_enabled: false,
      tags: ["重点"],
      note: "复核",
      revision: 2,
      updated_at: "now",
    }),
    batchUpdateReviewAssetMetadata: vi
      .fn()
      .mockResolvedValue({ updated_count: 1 }),
    validateReviewImport: vi.fn().mockResolvedValue({
      importable: [
        {
          line: 1,
          series_id: "5769",
          series_name: "Model Y",
          review_id: "m1",
          content_hash: "b".repeat(64),
        },
      ],
      duplicates: [],
      errors: [],
      validation_fingerprint: "c".repeat(64),
    }),
    confirmReviewImport: vi.fn().mockResolvedValue({
      imported_count: 1,
      duplicate_count: 0,
      asset_ids: ["manual:1"],
    }),
    validateReviewImportFile: vi.fn().mockResolvedValue({
      importable: [
        {
          line: 1,
          series_id: "5769",
          series_name: "Model Y",
          review_id: "file-1",
          content_hash: "d".repeat(64),
        },
      ],
      duplicates: [],
      errors: [],
      validation_fingerprint: "e".repeat(64),
    }),
    confirmReviewImportFile: vi.fn().mockResolvedValue({
      imported_count: 1,
      duplicate_count: 0,
      asset_ids: ["manual:file-1"],
    }),
    deleteReviewAsset: vi.fn().mockResolvedValue({
      asset_id: "autohome:r1",
      review_id: "r1",
      content_hash: "a".repeat(64),
      reason: "错误数据",
      deleted_at: "now",
    }),
    getReviewAssetSummary: vi.fn().mockResolvedValue(summary),
    listReviewDeletions: vi.fn().mockResolvedValue({
      rows: [],
      total: 0,
      page: 1,
      page_size: 20,
    }),
    allowReviewRecollection: vi.fn().mockResolvedValue({
      asset_id: "autohome:r1",
      review_id: "r1",
      content_hash: "a".repeat(64),
      reason: "误采集",
      deleted_at: "now",
      recollection_allowed_at: "later",
    }),
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("review asset workspace", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("sends raw files and the validation fingerprint through the file API", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          importable: [],
          duplicates: [],
          errors: [],
          validation_fingerprint: "f".repeat(64),
        }),
    });
    vi.stubGlobal("fetch", fetch);
    const file = new Blob(["series_id"], {
      type: "application/octet-stream",
    }) as File;
    Object.defineProperty(file, "name", { value: "reviews.csv" });

    await collectionApi.validateReviewImportFile(file);
    await collectionApi.confirmReviewImportFile(file, "f".repeat(64));

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "/api/collection/review-assets/import-file/validate?filename=reviews.csv",
      expect.objectContaining({ method: "POST", body: file }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/collection/review-assets/import-file?filename=reviews.csv",
      expect.objectContaining({
        method: "POST",
        body: file,
        headers: expect.objectContaining({
          "X-Validation-Fingerprint": "f".repeat(64),
        }),
      }),
    );
  });

  it("filters, resets pagination, pages, and opens and closes details", async () => {
    const client = api({
      listReviewAssets: vi
        .fn()
        .mockResolvedValue({ ...resultPage([asset()]), total: 41 }),
    });
    const workspace = createAssetWorkspace(client, false);
    workspace.page.value = 3;
    workspace.filters.keyword = "续航";
    workspace.filters.source_kind = "autohome";

    await workspace.applyFilters();
    expect(workspace.page.value).toBe(1);
    expect(client.listReviewAssets).toHaveBeenCalledWith(
      expect.objectContaining({
        keyword: "续航",
        source_kind: "autohome",
        page: 1,
      }),
    );
    await workspace.nextPage();
    expect(workspace.page.value).toBe(2);
    await workspace.openAsset("autohome:r1");
    expect(workspace.detail.value?.asset_id).toBe("autohome:r1");
    workspace.closeAsset();
    expect(workspace.detail.value).toBeNull();
  });

  it("saves metadata, reloads a revision conflict, batches, and refreshes summary", async () => {
    const conflictClient = api({
      updateReviewAssetMetadata: vi
        .fn()
        .mockRejectedValue(
          new ApiError(409, "资产管理信息已被其他操作更新，请刷新后重试"),
        ),
    });
    const workspace = createAssetWorkspace(conflictClient, false);
    await workspace.openAsset("autohome:r1");
    await workspace.saveMetadata({
      tags: ["重点"],
      note: "复核",
      analysis_enabled: false,
    });
    expect(conflictClient.getReviewAsset).toHaveBeenCalledTimes(1);
    expect(workspace.error.value).toContain("刷新后重试");
    await workspace.refreshCurrentDetail();
    expect(conflictClient.getReviewAsset).toHaveBeenCalledTimes(2);

    const client = api();
    const next = createAssetWorkspace(client, false);
    await next.openAsset("autohome:r1");
    await next.saveMetadata({
      tags: ["重点"],
      note: "复核",
      analysis_enabled: false,
    });
    expect(client.updateReviewAssetMetadata).toHaveBeenCalledWith(
      "autohome:r1",
      expect.objectContaining({ revision: 1 }),
    );
    next.selectedAssetIds.value = ["autohome:r1"];
    await next.batchUpdate({
      analysis_enabled: false,
      add_tags: ["本轮"],
      remove_tags: [],
    });
    expect(client.batchUpdateReviewAssetMetadata).toHaveBeenCalledOnce();
    expect(client.getReviewAssetSummary).toHaveBeenCalled();
  });

  it("validates every selected file before confirming them in order", async () => {
    const client = api({
      validateReviewImportFile: vi
        .fn()
        .mockResolvedValueOnce({
          importable: [
            {
              line: 1,
              series_id: "5769",
              series_name: "Model Y",
              review_id: "first",
              content_hash: "1".repeat(64),
            },
          ],
          duplicates: [],
          errors: [],
          validation_fingerprint: "a".repeat(64),
        })
        .mockResolvedValueOnce({
          importable: [
            {
              line: 1,
              series_id: "5346",
              series_name: "Model 3",
              review_id: "second",
              content_hash: "2".repeat(64),
            },
          ],
          duplicates: [{ line: 2, reason: "内容已存在" }],
          errors: [],
          validation_fingerprint: "b".repeat(64),
        }),
      confirmReviewImportFile: vi
        .fn()
        .mockResolvedValueOnce({
          imported_count: 1,
          duplicate_count: 0,
          asset_ids: ["manual:first"],
        })
        .mockResolvedValueOnce({
          imported_count: 1,
          duplicate_count: 1,
          asset_ids: ["manual:second"],
        }),
    });
    const workspace = createAssetWorkspace(client, false);
    const first = { name: "first.xlsx", size: 120 } as File;
    const second = { name: "second.csv", size: 80 } as File;

    workspace.beginImport();
    await workspace.validateImportFiles([first, second]);
    expect(workspace.importStep.value).toBe("preview");
    expect(workspace.importTotals.value).toEqual({
      files: 2,
      importable: 2,
      duplicates: 1,
      errors: 0,
    });
    expect(client.confirmReviewImportFile).not.toHaveBeenCalled();
    await workspace.confirmImport();
    expect(client.confirmReviewImportFile).toHaveBeenNthCalledWith(
      1,
      first,
      "a".repeat(64),
    );
    expect(client.confirmReviewImportFile).toHaveBeenNthCalledWith(
      2,
      second,
      "b".repeat(64),
    );
    expect(workspace.importStep.value).toBe("complete");
    expect(workspace.importResult.value).toEqual({
      imported_count: 2,
      duplicate_count: 1,
      asset_ids: ["manual:first", "manual:second"],
    });
    expect(client.getReviewAssetSummary).toHaveBeenCalled();
  });

  it("does not confirm any file when one validation contains errors", async () => {
    const client = api({
      validateReviewImportFile: vi
        .fn()
        .mockResolvedValueOnce({
          importable: [],
          duplicates: [],
          errors: [
            { line: 0, type: "file_parse_error", message: "缺少必要列" },
          ],
          validation_fingerprint: "a".repeat(64),
        })
        .mockResolvedValueOnce({
          importable: [
            {
              line: 1,
              series_id: "5769",
              series_name: "Model Y",
              review_id: "valid",
              content_hash: "1".repeat(64),
            },
          ],
          duplicates: [],
          errors: [],
          validation_fingerprint: "b".repeat(64),
        }),
    });
    const workspace = createAssetWorkspace(client, false);

    await workspace.validateImportFiles([
      { name: "invalid.xlsx", size: 10 } as File,
      { name: "valid.csv", size: 10 } as File,
    ]);
    await workspace.confirmImport();

    expect(workspace.importTotals.value.errors).toBe(1);
    expect(workspace.error.value).toContain("错误");
    expect(client.confirmReviewImportFile).not.toHaveBeenCalled();
    expect(workspace.importStep.value).toBe("preview");
  });

  it("reports live progress while validating a folder batch", async () => {
    const firstValidation = deferred<ReviewImportValidation>();
    const secondValidation = deferred<ReviewImportValidation>();
    const client = api({
      validateReviewImportFile: vi
        .fn()
        .mockReturnValueOnce(firstValidation.promise)
        .mockReturnValueOnce(secondValidation.promise),
    });
    const workspace = createAssetWorkspace(client, false);
    const first = { name: "first.xlsx", size: 10 } as File;
    const second = { name: "second.xlsx", size: 10 } as File;

    const validating = workspace.validateImportFiles([first, second]);
    expect(workspace.importProgress.value).toEqual({
      phase: "validating",
      completed: 0,
      total: 2,
      currentFile: "first.xlsx",
    });

    firstValidation.resolve({
      importable: [],
      duplicates: [],
      errors: [],
      validation_fingerprint: "a".repeat(64),
    });
    await vi.waitFor(() => {
      expect(workspace.importProgress.value).toEqual({
        phase: "validating",
        completed: 1,
        total: 2,
        currentFile: "second.xlsx",
      });
    });
    secondValidation.resolve({
      importable: [],
      duplicates: [],
      errors: [],
      validation_fingerprint: "b".repeat(64),
    });
    await validating;

    expect(workspace.importProgress.value).toEqual({
      phase: null,
      completed: 2,
      total: 2,
      currentFile: "",
    });
  });

  it("deletes permanently, clears selection, and exposes Chinese recovery messages", async () => {
    const client = api();
    const workspace = createAssetWorkspace(client, false);
    await workspace.openAsset("autohome:r1");
    await workspace.deleteCurrent("错误数据", "r1");
    expect(client.deleteReviewAsset).toHaveBeenCalledWith(
      "autohome:r1",
      expect.objectContaining({ confirm: true }),
    );
    expect(workspace.detail.value).toBeNull();

    for (const [status, message] of [
      [404, "评论资产不存在"],
      [410, "评论资产已永久删除"],
      [422, "导入数据格式不正确"],
    ] as const) {
      const failed = createAssetWorkspace(
        api({
          getReviewAsset: vi
            .fn()
            .mockRejectedValue(new ApiError(status, message)),
        }),
        false,
      );
      await failed.openAsset("autohome:missing");
      expect(failed.error.value).toBe(message);
      expect(failed.detail.value).toBeNull();
    }
  });

  it("keeps newer list results and ignores details after close or deactivation", async () => {
    const oldList = deferred<Page<ReviewAssetSummary>>();
    const lateDetail = deferred<ReviewAssetDetail>();
    const client = api({
      listReviewAssets: vi
        .fn()
        .mockReturnValueOnce(oldList.promise)
        .mockResolvedValueOnce(resultPage([asset("manual:new")])),
      getReviewAsset: vi.fn().mockReturnValue(lateDetail.promise),
    });
    const workspace = createAssetWorkspace(client, false);
    workspace.filters.keyword = "旧";
    const old = workspace.loadAssets();
    workspace.filters.keyword = "新";
    await workspace.loadAssets();
    oldList.resolve(resultPage([asset("autohome:old")]));
    await old;
    expect(workspace.assets.value.rows[0]?.asset_id).toBe("manual:new");

    const opening = workspace.openAsset("autohome:r1");
    workspace.closeAsset();
    lateDetail.resolve(detail());
    await opening;
    expect(workspace.detail.value).toBeNull();

    const lateSummary = deferred<typeof summary>();
    const stopped = createAssetWorkspace(
      api({
        getReviewAssetSummary: vi.fn().mockReturnValue(lateSummary.promise),
      }),
      false,
    );
    const loading = stopped.loadSummary();
    stopped.deactivate();
    lateSummary.resolve(summary);
    await loading;
    expect(stopped.summary.value).toBeNull();
  });

  it("does not reopen a closed asset when a metadata save finishes late", async () => {
    const saved = deferred<ReviewAssetMetadata>();
    const client = api({
      updateReviewAssetMetadata: vi.fn().mockReturnValue(saved.promise),
    });
    const workspace = createAssetWorkspace(client, false);
    await workspace.openAsset("autohome:r1");

    const saving = workspace.saveMetadata({
      tags: ["重点"],
      note: "稍后完成",
      analysis_enabled: true,
    });
    workspace.closeAsset();
    saved.resolve({
      asset_id: "autohome:r1",
      analysis_enabled: true,
      tags: ["重点"],
      note: "稍后完成",
      revision: 2,
      updated_at: "later",
    });
    await saving;

    expect(workspace.detail.value).toBeNull();
    expect(client.getReviewAsset).toHaveBeenCalledTimes(1);
  });

  it("does not reopen an asset when deactivated during the post-save refresh", async () => {
    const lateList = deferred<Page<ReviewAssetSummary>>();
    const lateSummary = deferred<typeof summary>();
    const client = api({
      listReviewAssets: vi.fn().mockReturnValue(lateList.promise),
      getReviewAssetSummary: vi.fn().mockReturnValue(lateSummary.promise),
    });
    const workspace = createAssetWorkspace(client, false);
    await workspace.openAsset("autohome:r1");

    const saving = workspace.saveMetadata({
      tags: ["重点"],
      note: "保存后离开页面",
      analysis_enabled: true,
    });
    await vi.waitFor(() => {
      expect(client.listReviewAssets).toHaveBeenCalledTimes(1);
      expect(client.getReviewAssetSummary).toHaveBeenCalledTimes(1);
    });
    workspace.deactivate();
    lateList.resolve(resultPage([asset()]));
    lateSummary.resolve(summary);
    await saving;

    expect(client.getReviewAsset).toHaveBeenCalledTimes(1);
    expect(workspace.detailBusy.value).toBe(false);
  });

  it("does not close a newer asset when an older deletion finishes late", async () => {
    const deleted = deferred<ReviewDeletion>();
    const client = api({
      getReviewAsset: vi
        .fn()
        .mockImplementation((assetId: string) =>
          Promise.resolve(detail(assetId)),
        ),
      deleteReviewAsset: vi.fn().mockReturnValue(deleted.promise),
    });
    const workspace = createAssetWorkspace(client, false);
    await workspace.openAsset("autohome:r1");

    const deleting = workspace.deleteCurrent("错误数据", "r1");
    workspace.closeAsset();
    await workspace.openAsset("manual:r2");
    deleted.resolve({
      asset_id: "autohome:r1",
      review_id: "r1",
      content_hash: "a".repeat(64),
      reason: "错误数据",
      deleted_at: "later",
    });
    await deleting;

    expect(workspace.detail.value?.asset_id).toBe("manual:r2");
  });

  it("loads deletion history and explicitly releases a tombstone", async () => {
    const deletion: ReviewDeletion = {
      asset_id: "autohome:r1",
      review_id: "r1",
      content_hash: "a".repeat(64),
      reason: "误采集",
      deleted_at: "now",
      recollection_allowed_at: null,
    };
    const client = api({
      listReviewDeletions: vi.fn().mockResolvedValue({
        rows: [deletion],
        total: 1,
        page: 1,
        page_size: 20,
      }),
    });
    const workspace = createAssetWorkspace(client, false);

    await workspace.loadDeletions();
    expect(workspace.deletions.value.rows).toEqual([deletion]);
    await workspace.allowRecollection("autohome:r1");

    expect(client.allowReviewRecollection).toHaveBeenCalledWith("autohome:r1");
    expect(client.listReviewDeletions).toHaveBeenCalledTimes(2);
  });
});

describe("review asset API", () => {
  it("encodes filters and mutation paths", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({}),
    });
    vi.stubGlobal("fetch", fetchMock);
    await collectionApi.listReviewAssets({
      keyword: "汉 EV",
      analysis_enabled: false,
      page: 2,
      page_size: 20,
    });
    await collectionApi.getReviewAsset("manual:a/b");
    await collectionApi.updateReviewAssetMetadata("manual:a/b", {
      revision: 1,
      tags: [],
      note: "",
      analysis_enabled: true,
    });
    await collectionApi.batchUpdateReviewAssetMetadata({
      asset_ids: ["manual:a/b"],
      analysis_enabled: false,
      add_tags: [],
      remove_tags: [],
    });
    await collectionApi.getReviewAssetSummary();
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/collection/review-assets?keyword=%E6%B1%89%20EV&analysis_enabled=false&page=2&page_size=20",
      "/api/collection/review-assets/manual%3Aa%2Fb",
      "/api/collection/review-assets/manual%3Aa%2Fb/metadata",
      "/api/collection/review-assets/metadata",
      "/api/collection/review-assets/summary",
    ]);
  });
});
