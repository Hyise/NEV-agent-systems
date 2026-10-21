<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from "vue";
import AnnotationResults from "../review-analysis/components/AnnotationResults.vue";
import CriteriaProposalEditor from "../review-analysis/components/CriteriaProposalEditor.vue";
import MatrixHandoff from "../review-analysis/components/MatrixHandoff.vue";
import SourceScopePanel from "../review-analysis/components/SourceScopePanel.vue";
import { useReviewAnalysisWorkspace } from "../review-analysis/workspace";

const workspace = useReviewAnalysisWorkspace();
const statusLabel = (status?: string) =>
  ({
    queued: "等待执行",
    running: "正在分析",
    paused: "已暂停",
    completed: "已完成",
    partial_failed: "部分失败",
    failed: "失败",
    cancelled: "已取消",
  })[status ?? ""] ??
  status ??
  "未知";
const progress = computed(() => {
  const job = workspace.selectedJob.value;
  if (!job?.total_count) return 0;
  return Math.min(
    100,
    Math.round(((job.processed_count ?? 0) / job.total_count) * 100),
  );
});
onMounted(() => void workspace.activate());
onBeforeUnmount(workspace.deactivate);
</script>

<template>
  <section
    class="research-surface review-analysis-workspace"
    aria-label="评论语义分析工作区"
  >
    <div class="notice info">
      选中的公开评论原文将发送到 DeepSeek
      API。模型结果是研究辅助材料，不代表已经人工核验。
    </div>
    <SourceScopePanel />
    <section class="analysis-task-strip" aria-live="polite">
      <div>
        <span class="section-kicker">02 · 分析任务</span>
        <h2>任务状态与用量</h2>
      </div>
      <label v-if="workspace.jobs.value.length" class="job-history-select">
        历史任务
        <select v-model="workspace.selectedJobId.value">
          <option
            v-for="job in workspace.jobs.value"
            :key="job.id"
            :value="job.id"
          >
            {{
              job.job_type === "criteria_discovery" ? "准则发现" : "评论标注"
            }}
            · {{ job.status }} · {{ job.id.slice(0, 8) }}
          </option>
        </select>
      </label>
      <div v-if="workspace.selectedJob.value" class="analysis-job-progress">
        <div class="analysis-job-progress__heading">
          <strong>{{ statusLabel(workspace.selectedJob.value.status) }}</strong>
          <span class="mono">{{ progress }}%</span>
        </div>
        <div class="run-progress" aria-hidden="true">
          <span :style="{ width: progress + '%' }" />
        </div>
        <p>
          已处理 {{ workspace.selectedJob.value.processed_count ?? 0 }}/{{
            workspace.selectedJob.value.total_count ?? 0
          }}
          条 · 成功 {{ workspace.selectedJob.value.success_count ?? 0 }} · 失败
          {{ workspace.selectedJob.value.failed_count ?? 0 }} · 输入
          {{ workspace.selectedJob.value.input_tokens ?? 0 }} / 输出
          {{ workspace.selectedJob.value.output_tokens ?? 0 }} tokens
        </p>
      </div>
      <p v-else>尚无分析任务。</p>
      <div
        v-if="
          workspace.activeJob.value &&
          workspace.selectedJobId.value === workspace.activeJob.value.id
        "
        class="button-group"
      >
        <button
          v-if="workspace.selectedJob.value?.status !== 'paused'"
          class="btn secondary"
          @click="workspace.control('pause')"
        >
          暂停
        </button>
        <button
          v-else
          class="btn secondary"
          @click="workspace.control('resume')"
        >
          继续
        </button>
        <button class="text-button" @click="workspace.control('cancel')">
          取消
        </button>
      </div>
      <button
        v-if="workspace.selectedJob.value?.status === 'partial_failed'"
        class="btn secondary"
        @click="workspace.control('retry-failures')"
      >
        重试失败评论
      </button>
    </section>
    <CriteriaProposalEditor v-if="workspace.schemaStatus.value === 'draft'" />
    <template v-else>
      <AnnotationResults />
      <MatrixHandoff
        v-if="
          workspace.selectedJob.value?.job_type === 'review_annotation' &&
          ['completed', 'partial_failed'].includes(
            workspace.selectedJob.value?.status,
          )
        "
      />
    </template>
    <p v-if="workspace.error.value" class="notice error" role="alert">
      {{ workspace.error.value }}
    </p>
  </section>
</template>
