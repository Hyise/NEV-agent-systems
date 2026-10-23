/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import type { CatalogStatus, CollectionOverview } from "./api";
import { resolveAcquisitionGuidance } from "./acquisitionGuidance";
import shellSource from "./CollectionWorkbench.vue?raw";
import stageSource from "./components/GuidedStageBar.vue?raw";
import drawerSource from "./components/ReviewAssetDrawer.vue?raw";
import importerSource from "./components/ReviewImportDialog.vue?raw";
import seriesIndexSource from "./components/SeriesAssetIndex.vue?raw";
import assetsSource from "./views/AssetsView.vue?raw";
import researchSource from "./views/ResearchHandoffView.vue?raw";
import salesSource from "./views/SalesView.vue?raw";
import mcdmSource from "../mcdm/McdmWorkbench.vue?raw";
import annotationSource from "../mcdm/review-analysis/components/AnnotationResults.vue?raw";
import proposalSource from "../mcdm/review-analysis/components/CriteriaProposalEditor.vue?raw";
import matrixHandoffSource from "../mcdm/review-analysis/components/MatrixHandoff.vue?raw";

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
  it("provides direct handling actions for every matrix blocker category", () => {
    expect(matrixHandoffSource).toContain('intent: "sales-gap"');
    expect(matrixHandoffSource).toContain('intent: "review-date-gap"');
    expect(matrixHandoffSource).toContain("重试失败评论");
    expect(matrixHandoffSource).toContain("改用 2026 年后范围重跑");
    expect(matrixHandoffSource).toContain("中性均匀分布");
    expect(matrixHandoffSource).not.toContain("处理完上方阻塞项后即可生成");
  });
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

  it("keeps asset governance table-first and makes original reviews explicit and read-only", () => {
    for (const label of ["来源", "标签", "分析状态"]) {
      expect(assetsSource).toContain(label);
    }
    expect(assetsSource).not.toContain("批量删除");
    expect(assetsSource).toContain("查看原文");
    expect(drawerSource).toContain("原始评论内容");
    expect(drawerSource).toContain("全部原始结构化字段");
    expect(drawerSource).toContain("buildReadableReview");
    expect(drawerSource).toContain("JSON.stringify");
    expect(drawerSource).not.toContain('v-model="original_review');
    expect(drawerSource).toContain("删除原因");
    expect(drawerSource).toContain("输入评论 ID");
    expect(drawerSource).toContain('role="alert"');
    expect(drawerSource).toContain("refreshCurrentDetail");
    expect(assetsSource).toContain("删除记录");
    expect(assetsSource).toContain("允许未来重新采集");
  });

  it("provides a vehicle-series index that opens the matching review list", () => {
    expect(assetsSource).toContain("SeriesAssetIndex");
    expect(assetsSource).toContain("workspace.selectSeries");
    expect(seriesIndexSource).toContain("车型列表");
    expect(seriesIndexSource).toContain("种车型");
    expect(seriesIndexSource).toContain("series.count");
    expect(seriesIndexSource).toContain("emit('select', series.series_id)");
    expect(seriesIndexSource).toContain(
      ':aria-pressed="selectedSeriesId === series.series_id"',
    );
  });

  it("filters and displays the original review date separately from collection time", () => {
    expect(assetsSource).toContain('type="date"');
    expect(assetsSource).toContain("review_date_from");
    expect(assetsSource).toContain("review_date_to");
    expect(assetsSource).toContain("评论时间");
    expect(assetsSource).toContain('item.review_date ?? "未记录"');
    expect(assetsSource).toContain("采集 / 导入时间");
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
    expect(importerSource).toContain("JSON / JSONL / CSV / XLSX");
    expect(importerSource).toContain("multiple");
    expect(importerSource).toContain(".csv,.xlsx");
    expect(importerSource).toContain("workspace.importFilePreviews.value");
    expect(importerSource).toContain("文件校验结果");
  });

  it("assembles one owner for collection, catalog, and asset state", () => {
    expect(shellSource.match(/createCollectionWorkspace\(\)/g)).toHaveLength(1);
    expect(shellSource.match(/createCatalogFlow\(/g)).toHaveLength(1);
    expect(shellSource.match(/createAssetWorkspace\(\)/g)).toHaveLength(1);
    expect(shellSource).toContain("获取数据");
    expect(shellSource).toContain("管理数据");
    expect(shellSource).toContain("用于研究");
    expect(shellSource).toContain("销量数据");
    expect(shellSource.match(/createSalesWorkspace\(\)/g)).toHaveLength(1);
    expect(shellSource).toContain("assetWorkspace.refresh()");
    for (const source of [shellSource, mcdmSource]) {
      expect(source).toContain(':is="item.icon"');
      expect(source).toContain('class="nav-item__icon"');
    }
  });

  it("integrates a guided monthly sales flow without claiming blocked sources succeeded", () => {
    for (const label of [
      "选择月份与来源",
      "执行月榜采集",
      "匹配评论车系",
      "汽车之家",
      "懂车帝",
      "易车",
      "全国月度零售量",
      "导出 CSV",
    ]) {
      expect(salesSource).toContain(label);
    }
    expect(salesSource).toContain("verification_required");
    expect(salesSource).toContain("系统不会绕过验证");
  });

  it("hands server summary to two explicit research intents without creating tasks", () => {
    expect(researchSource).toContain("workspace.summary.value");
    expect(researchSource).toContain("intent: 'criteria-discovery'");
    expect(researchSource).toContain("intent: 'review-annotation'");
    expect(researchSource).toContain("不可用原因");
    expect(researchSource).toContain("不会自动调用大模型");
    expect(mcdmSource).toContain("parseMcdmIntent");
    expect(mcdmSource).toContain("请确认本次研究的车系来源范围");
    expect(mcdmSource).toContain("当前是准则草稿");
    expect(mcdmSource).toContain("当前是冻结准则版本");
    expect(mcdmSource).not.toContain(
      "handoffIntent.value === 'criteria-discovery' ? reviewAnalysisWorkspace.createDiscovery",
    );
    expect(mcdmSource).not.toContain(
      "handoffIntent.value === 'review-annotation' ? reviewAnalysisWorkspace.createAnnotation",
    );
  });

  it("shows a continuous acquisition path with real catalog and review counts", () => {
    expect(stageSource).toContain('class="guided-stage__status"');
    expect(stageSource).toContain("catalog?.series_count");
    expect(stageSource).toContain("overview?.review_count");
    expect(stageSource).toContain("确认研究范围");
  });

  it("shows deleted-source traceability in historical research", () => {
    expect(annotationSource).toContain("源评论已删除");
    expect(annotationSource).toContain("source_deleted");
    expect(proposalSource).toContain("source_deleted_count");
    expect(proposalSource).toContain("不可变快照证据");
  });
});
