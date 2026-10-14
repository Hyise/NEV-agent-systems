import type { CatalogStatus, CollectionOverview } from "./api";

export type AcquisitionAction =
  | "discover"
  | "collect"
  | "resume"
  | "monitor"
  | "manage";

export function resolveAcquisitionGuidance(
  overview: CollectionOverview | null,
  catalog: CatalogStatus | null,
): { action: AcquisitionAction; title: string; description: string } {
  const job = overview?.active_job;
  if (job?.status === "paused") {
    return {
      action: "resume",
      title: "继续已暂停的采集任务",
      description: "任务断点已经保存，可以从当前车系和页码继续。",
    };
  }
  if (job && ["queued", "discovering", "collecting"].includes(job.status)) {
    return {
      action: "monitor",
      title: "查看正在运行的采集任务",
      description: "关注当前车系、页码、保存数和人工删除跳过数。",
    };
  }
  if ((overview?.review_count ?? 0) > 0) {
    return {
      action: "manage",
      title: "整理已经采集的评论",
      description: "检查原始数据，并设置标签和是否进入后续研究。",
    };
  }
  if ((catalog?.series_count ?? overview?.series_count ?? 0) > 0) {
    return {
      action: "collect",
      title: "选择车系并采集评论",
      description: "目录已经就绪，先用少量车系完成功能验证。",
    };
  }
  return {
    action: "discover",
    title: "先发现可采集车系",
    description: "生成当前新能源汽车车系目录，再选择要采集的范围。",
  };
}
