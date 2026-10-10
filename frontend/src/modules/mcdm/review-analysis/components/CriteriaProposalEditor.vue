<script setup lang="ts">
import { useWorkspace } from "../../workspace";
import { useReviewAnalysisWorkspace } from "../workspace";
const main = useWorkspace();
const workspace = useReviewAnalysisWorkspace();
async function apply() {
  if (!main.overview.value) return;
  const applied = await workspace.applyProposal(
    main.overview.value.schema.revision,
  );
  if (!applied) return;
  main.navigate("criteria");
  await main.loadWorkspace();
}
</script>

<template>
  <section class="review-analysis-section">
    <header>
      <span class="section-kicker">03 · 方案审核</span>
      <h2>准则发现候选方案</h2>
      <p>候选方案不会自动冻结。请逐项审核名称、等级、依据和代表证据。</p>
    </header>
    <button
      v-if="
        workspace.selectedJob.value?.job_type === 'criteria_discovery' &&
        workspace.selectedJob.value?.status === 'completed' &&
        !workspace.proposal.value
      "
      class="btn secondary"
      @click="workspace.loadProposal(workspace.selectedJob.value!.id)"
    >
      读取候选方案
    </button>
    <div v-if="workspace.proposalDraft.value.length" class="proposal-list">
      <article
        v-for="(criterion, index) in workspace.proposalDraft.value"
        :key="index"
        class="proposal-card"
      >
        <label>准则名称<input v-model="criterion.name" maxlength="50" /></label>
        <label
          >有序等级（由优到劣）<input
            :value="criterion.labels.join(' | ')"
            @input="
              criterion.labels = ($event.target as HTMLInputElement).value
                .split('|')
                .map((v) => v.trim())
                .filter(Boolean)
            "
        /></label>
        <p><strong>归并依据：</strong>{{ criterion.basis }}</p>
        <p>
          <strong>代表性原文证据：</strong
          >{{ criterion.evidence.join("；") || "无" }}
        </p>
        <div class="button-group">
          <button
            class="text-button"
            :disabled="index === 0"
            @click="
              workspace.proposalDraft.value.splice(
                index - 1,
                0,
                ...workspace.proposalDraft.value.splice(index, 1),
              )
            "
          >
            上移</button
          ><button
            class="text-button"
            :disabled="workspace.proposalDraft.value.length <= 1"
            @click="workspace.proposalDraft.value.splice(index, 1)"
          >
            删除
          </button>
        </div>
      </article>
      <button class="btn primary" @click="apply">应用到准则草稿</button>
    </div>
    <div v-else class="empty">完成准则发现后，可在这里审核候选方案。</div>
  </section>
</template>
