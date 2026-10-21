<script setup lang="ts">
import { computed } from "vue";
import { ArrowRight, Check, RefreshCw, TableProperties } from "lucide-vue-next";
import { useWorkspace } from "../../workspace";
import { useReviewAnalysisWorkspace } from "../workspace";

const main = useWorkspace();
const workspace = useReviewAnalysisWorkspace();
const preview = computed(() => workspace.matrixPreview.value);
const canMaterialize = computed(
  () =>
    Boolean(preview.value?.stats.records) &&
    !preview.value?.blockers.length &&
    !preview.value?.stats.missing_date_reviews &&
    !workspace.busy.value,
);

async function materialize() {
  if (!(await workspace.materializeMatrix())) return;
  await main.loadWorkspace();
}

async function enterExperiments() {
  await main.loadWorkspace();
  main.navigate("experiments");
}
</script>

<template>
  <section class="review-analysis-section matrix-handoff">
    <header>
      <span class="section-kicker">04 · 形成评价矩阵</span>
      <h2>把本次评论判定用于模型实验</h2>
      <p>先复核聚合范围与缺失项，再生成不可变数据快照。</p>
    </header>

    <div v-if="preview" class="matrix-preview-grid" aria-label="评价矩阵预览">
      <div>
        <strong>{{ preview.stats.source_reviews }}</strong
        ><span>去重评论</span>
      </div>
      <div>
        <strong>{{ preview.stats.groups }}</strong
        ><span>月份 × 车系</span>
      </div>
      <div>
        <strong>{{ preview.stats.records }}</strong
        ><span>可生成记录</span>
      </div>
      <div>
        <strong>{{ preview.stats.blocked_groups }}</strong
        ><span>阻塞分组</span>
      </div>
    </div>
    <div v-else class="empty compact">
      <TableProperties :size="28" />
      <p>任务完成后将自动计算评价矩阵预览。</p>
      <button class="text-button" @click="workspace.loadMatrixPreview()">
        <RefreshCw :size="15" />重新读取
      </button>
    </div>

    <div
      v-if="preview?.stats.missing_date_reviews"
      class="notice warning"
      role="status"
    >
      有
      {{ preview.stats.missing_date_reviews }}
      条评论缺少评论日期，需补齐后才能生成。
    </div>
    <div v-if="preview?.failed_reviews" class="notice warning" role="status">
      本次任务仍有
      {{ preview.failed_reviews }} 条失败评论；可先重试失败项再生成矩阵。
    </div>
    <ul v-if="preview?.blockers.length" class="matrix-blockers">
      <li
        v-for="item in preview.blockers"
        :key="item.month + ':' + item.series_id"
      >
        <strong>{{ item.month }} · {{ item.series_name }}</strong>
        <span>{{ item.reasons.join("；") }}</span>
      </li>
    </ul>

    <div class="matrix-actions">
      <button
        class="btn primary"
        :disabled="!canMaterialize"
        @click="materialize"
      >
        生成评价矩阵快照
      </button>
      <span v-if="preview && !canMaterialize">处理完上方阻塞项后即可生成</span>
    </div>

    <div
      v-if="workspace.generatedDataset.value"
      class="dataset-success"
      role="status"
    >
      <Check :size="18" />
      <div>
        <strong>{{ workspace.generatedDataset.value.name }}</strong>
        <span
          >{{ workspace.generatedDataset.value.records }} 条记录 · 快照
          {{ workspace.generatedDataset.value.sha256.slice(0, 10) }}</span
        >
      </div>
      <button class="btn secondary" @click="enterExperiments">
        进入模型实验 <ArrowRight :size="15" />
      </button>
    </div>
  </section>
</template>
