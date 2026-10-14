/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import type { CatalogStatus, CollectionOverview } from "./api";
import { resolveAcquisitionGuidance } from "./acquisitionGuidance";
import shellSource from "./CollectionWorkbench.vue?raw";
import drawerSource from "./components/ReviewAssetDrawer.vue?raw";
import importerSource from "./components/ReviewImportDialog.vue?raw";
import assetsSource from "./views/AssetsView.vue?raw";

const overview = (
  series: number,
  reviews: number,
  status?: "collecting" | "paused",
): CollectionOverview => ({
  series_count: series,
  review_count: reviews,
  pending_errors: 0,
  active_job: status
    ? {
        id: "job-1",
        mode: "verification",
        source_url: "source",
        max_series: 3,
        max_pages_per_series: 2,
        request_delay_min_seconds: 2,
        request_delay_max_seconds: 4,
        series_delay_min_seconds: 5,
        series_delay_max_seconds: 10,
        status,
        resume_status: null,
        control_requested: null,
        current_series_index: 0,
        current_series_id: "5769",
        current_series_name: "Model Y",
        current_page: 1,
        discovered_count: 3,
        saved_count: reviews,
        duplicate_count: 0,
        failed_count: 0,
        skipped_count: 0,
        last_success_at: null,
        last_error: null,
        created_at: "now",
        started_at: "now",
        finished_at: null,
        updated_at: "now",
      }
    : null,
});

const catalog = (count: number): CatalogStatus => ({
  active_batch_id: count ? "batch" : null,
  series_count: count,
  published_at: count ? "now" : null,
  source_url: "source",
  source_exhausted: false,
  active_run: null,
});

describe("guided collection views", () => {
  it("selects exactly one recommended action for each acquisition state", () => {
    expect(resolveAcquisitionGuidance(overview(0, 0), catalog(0)).action).toBe(
      "discover",
    );
    expect(
      resolveAcquisitionGuidance(overview(10, 0), catalog(10)).action,
    ).toBe("collect");
    expect(
      resolveAcquisitionGuidance(overview(10, 3, "paused"), catalog(10)).action,
    ).toBe("resume");
    expect(
      resolveAcquisitionGuidance(overview(10, 3, "collecting"), catalog(10))
        .action,
    ).toBe("monitor");
    expect(
      resolveAcquisitionGuidance(overview(10, 30), catalog(10)).action,
    ).toBe("manage");
  });

  it("keeps asset governance table-first and original JSON read-only", () => {
    for (const label of ["来源", "标签", "分析状态"]) {
      expect(assetsSource).toContain(label);
    }
    expect(assetsSource).not.toContain("批量删除");
    expect(drawerSource).toContain("只读原始数据");
    expect(drawerSource).toContain("JSON.stringify");
    expect(drawerSource).not.toContain('v-model="original_review');
    expect(drawerSource).toContain("删除原因");
    expect(drawerSource).toContain("输入评论 ID");
  });

  it("documents the import steps, line feedback, and dialog accessibility", () => {
    for (const label of [
      "选择文件",
      "校验预览",
      "确认写入",
      "错误行",
      "重复原因",
    ]) {
      expect(importerSource).toContain(label);
    }
    for (const content of [importerSource, drawerSource]) {
      expect(content).toContain("@cancel.prevent");
      expect(content).toContain("restoreFocus");
      expect(content).toContain("focus()");
      expect(content).toContain("aria-labelledby");
    }
  });

  it("assembles one owner for collection, catalog, and asset state", () => {
    expect(shellSource.match(/createCollectionWorkspace\(\)/g)).toHaveLength(1);
    expect(shellSource.match(/createCatalogFlow\(/g)).toHaveLength(1);
    expect(shellSource.match(/createAssetWorkspace\(\)/g)).toHaveLength(1);
    expect(shellSource).toContain("获取数据");
    expect(shellSource).toContain("管理数据");
    expect(shellSource).toContain("用于研究");
  });
});
