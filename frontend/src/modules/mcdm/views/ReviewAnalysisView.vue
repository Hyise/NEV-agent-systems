<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";
import AnnotationResults from "../review-analysis/components/AnnotationResults.vue";
import CriteriaProposalEditor from "../review-analysis/components/CriteriaProposalEditor.vue";
import SourceScopePanel from "../review-analysis/components/SourceScopePanel.vue";
import { useReviewAnalysisWorkspace } from "../review-analysis/workspace";

const workspace = useReviewAnalysisWorkspace();
onMounted(() => void workspace.activate());
onBeforeUnmount(workspace.deactivate);
</script>

<template>
  <section class="review-analysis-workspace" aria-label="评论语义分析工作区">
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
      <p v-if="workspace.activeJob.value">
        状态：{{ workspace.activeJob.value.status }} ·
        {{ workspace.activeJob.value.processed_count ?? 0 }}/{{
          workspace.activeJob.value.total_count ?? 0
        }}
        条
      </p>
      <p v-else>当前没有活动任务。</p>
      <div v-if="workspace.activeJob.value" class="button-group">
        <button class="btn secondary" @click="workspace.control('pause')">
          暂停
        </button>
        <button class="btn secondary" @click="workspace.control('resume')">
          继续
        </button>
        <button class="text-button" @click="workspace.control('cancel')">
          取消
        </button>
      </div>
    </section>
    <CriteriaProposalEditor v-if="workspace.schemaStatus.value === 'draft'" />
    <AnnotationResults v-else />
    <p v-if="workspace.error.value" class="notice error" role="alert">
      {{ workspace.error.value }}
    </p>
  </section>
</template>
