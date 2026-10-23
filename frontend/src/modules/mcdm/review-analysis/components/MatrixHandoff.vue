<script setup lang="ts">
import { computed, nextTick, ref } from "vue";
import {
  ArrowRight,
  Check,
  CircleAlert,
  RefreshCw,
  TableProperties,
} from "lucide-vue-next";
import { RouterLink } from "vue-router";
import type { MatrixBlocker } from "../api";
import { useWorkspace } from "../../workspace";
import { useReviewAnalysisWorkspace } from "../workspace";

const main = useWorkspace();
const workspace = useReviewAnalysisWorkspace();
const preview = computed(() => workspace.matrixPreview.value);
const scopePrepared = ref(false);
const canMaterialize = computed(
  () =>
    Boolean(preview.value?.stats.records) &&
    !preview.value?.blockers.length &&
    !preview.value?.stats.missing_date_reviews &&
    !preview.value?.failed_reviews &&
    workspace.handoff.value?.state !== "materialized" &&
    !workspace.busy.value,
);

function hasIssue(item: MatrixBlocker, codes: string[]) {
  return item.issues.some((issue) => codes.includes(issue.code));
}

function salesTarget(item: MatrixBlocker) {
  return {
    name: "collection",
    query: {
      intent: "sales-gap",
      month: item.month,
      series_id: item.series_id,
      series_name: item.series_name,
    },
  };
}

const missingDateTarget = computed(() => {
  const item = preview.value?.missing_date_items[0];
  if (!item) return null;
  return {
    name: "collection",
    query: {
      intent: "review-date-gap",
      review_id: item.review_id,
      series_id: item.series_id,
      series_name: item.series_name,
    },
  };
});

async function preparePost2026Rerun() {
  workspace.reviewDateFrom.value = "2026-01-01";
  if (
    workspace.reviewDateTo.value &&
    workspace.reviewDateTo.value < "2026-01-01"
  )
    workspace.reviewDateTo.value = "";
  scopePrepared.value = true;
  await nextTick();
  document
    .querySelector<HTMLElement>("#review-analysis-source-scope")
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
  document.querySelector<HTMLInputElement>("#review-date-from")?.focus();
}

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

    <section
      v-if="
        preview &&
        (preview.failed_reviews ||
          preview.stats.missing_date_reviews ||
          preview.blockers.length)
      "
      class="matrix-resolution-board"
      aria-labelledby="matrix-resolution-title"
    >
      <header>
        <CircleAlert :size="19" aria-hidden="true" />
        <div>
          <h3 id="matrix-resolution-title">生成前需要处理</h3>
          <p>每项问题都提供对应入口；处理后返回这里重新读取预览。</p>
        </div>
      </header>

      <article v-if="preview.failed_reviews" class="matrix-resolution-item">
        <div>
          <strong>{{ preview.failed_reviews }} 条评论处理失败</strong>
          <span>重试只处理失败项，已成功的评论不会重复调用模型。</span>
        </div>
        <button
          class="btn secondary"
          type="button"
          :disabled="workspace.busy.value"
          @click="workspace.control('retry-failures')"
        >
          重试失败评论
        </button>
      </article>

      <article
        v-if="preview.stats.missing_date_reviews"
        class="matrix-resolution-item"
      >
        <div>
          <strong
            >{{ preview.stats.missing_date_reviews }} 条评论缺少日期</strong
          >
          <span>原始评论不可改写；请定位原记录，删除后重新导入或采集。</span>
        </div>
        <RouterLink
          v-if="missingDateTarget"
          class="btn secondary"
          :to="missingDateTarget"
          >定位第一条评论</RouterLink
        >
      </article>

      <article
        v-for="item in preview.blockers"
        :key="item.month + ':' + item.series_id"
        class="matrix-resolution-item"
      >
        <div>
          <strong>{{ item.month }} · {{ item.series_name }}</strong>
          <span>{{ item.reasons.join("；") }}</span>
        </div>
        <div class="matrix-resolution-actions">
          <RouterLink
            v-if="
              hasIssue(item, [
                'missing_sales',
                'invalid_sales',
                'duplicate_sales',
              ])
            "
            class="btn secondary"
            :to="salesTarget(item)"
            >检查并补采销量</RouterLink
          >
          <button
            v-if="hasIssue(item, ['historical_pressure'])"
            class="btn secondary"
            type="button"
            @click="preparePost2026Rerun"
          >
            改用 2026 年后范围重跑
          </button>
        </div>
      </article>
    </section>

    <div v-if="scopePrepared" class="notice info" role="status">
      已把新任务的开始日期设为
      2026-01-01。请在页面上方确认范围并重新启动评论标注。
    </div>

    <details v-if="preview?.warnings.length" class="matrix-coverage-note">
      <summary>
        {{ preview.stats.unmentioned_criterion_groups }}
        个分组存在未提及准则，不阻止生成
      </summary>
      <p>
        未提及不等于负面评价。系统使用中性均匀分布，并在数据集中保存每项准则的评论覆盖率。
      </p>
      <ul>
        <li
          v-for="item in preview.warnings.slice(0, 5)"
          :key="item.month + ':' + item.series_id"
        >
          <strong>{{ item.month }} · {{ item.series_name }}</strong>
          <span>{{ item.message }}</span>
        </li>
      </ul>
      <p v-if="preview.warnings.length > 5">
        其余 {{ preview.warnings.length - 5 }} 个分组已按相同规则记录。
      </p>
    </details>

    <div class="matrix-actions">
      <div class="button-group">
        <button
          class="btn primary"
          :disabled="!canMaterialize"
          @click="materialize"
        >
          生成评价矩阵快照
        </button>
        <button
          class="btn secondary"
          type="button"
          :disabled="workspace.busy.value"
          @click="workspace.loadMatrixPreview()"
        >
          <RefreshCw :size="15" />重新检查数据
        </button>
      </div>
      <span v-if="workspace.handoff.value?.state === 'materialized'"
        >当前准则已有权威数据集，不会重复生成或替换。</span
      >
      <span v-else-if="preview && !canMaterialize"
        >请按“生成前需要处理”中的入口完成必要数据</span
      >
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
