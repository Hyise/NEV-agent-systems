<script setup lang="ts">
import { useReviewAnalysisWorkspace } from "../workspace";
const workspace = useReviewAnalysisWorkspace();
</script>

<template>
  <section class="review-analysis-section">
    <header>
      <span class="section-kicker">03 · 评论级结果</span>
      <h2>逐条评论标注</h2>
      <p>筛选只改变当前显示，不会重新调用模型。</p>
    </header>
    <div class="analysis-summary" aria-label="标注汇总">
      <strong>{{ workspace.summary.value.annotated_reviews }}</strong>
      <span>条已完成标注</span>
      <span
        v-for="(count, name) in workspace.summary.value.criteria"
        :key="name"
      >
        {{ name }} {{ count }} 次
      </span>
    </div>
    <div class="annotation-filters">
      <label
        >任务<select v-model="workspace.filters.value.job_id">
          <option value="">全部标注任务</option>
          <option
            v-for="job in workspace.jobs.value.filter(
              (item) => item.job_type === 'review_annotation',
            )"
            :key="job.id"
            :value="job.id"
          >
            {{ job.id.slice(0, 8) }} · {{ job.status }}
          </option>
        </select></label
      ><label
        >车系 ID<input
          v-model="workspace.filters.value.series_id"
          placeholder="留空表示全部" /></label
      ><label>准则<input v-model="workspace.filters.value.criterion" /></label
      ><label>等级<input v-model="workspace.filters.value.label" /></label
      ><label
        >状态<select v-model="workspace.filters.value.status">
          <option value="">全部</option>
          <option value="succeeded">成功</option>
          <option value="failed">失败</option>
          <option value="cached">缓存复用</option>
        </select></label
      ><button class="btn secondary" @click="workspace.loadAnnotations()">
        查询结果
      </button>
    </div>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>车系</th>
            <th>评论 ID</th>
            <th>状态</th>
            <th>命中准则</th>
            <th>标注时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in workspace.annotations.value" :key="row.review_id">
            <td>{{ row.series_name }}</td>
            <td class="mono">{{ row.review_id }}</td>
            <td>{{ row.status }}</td>
            <td>{{ row.annotation_count }}</td>
            <td>{{ row.annotated_at ?? "—" }}</td>
            <td>
              <button
                v-if="row.annotation_id"
                class="text-button"
                @click="workspace.openAnnotation(row.annotation_id)"
              >
                查看详情
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <nav
      v-if="workspace.annotationTotal.value"
      class="pager"
      aria-label="标注结果分页"
    >
      <button
        class="text-button"
        :disabled="workspace.annotationPage.value <= 1"
        @click="workspace.loadAnnotations(workspace.annotationPage.value - 1)"
      >
        上一页
      </button>
      <span
        >第 {{ workspace.annotationPage.value }} 页 · 共
        {{ workspace.annotationTotal.value }} 条</span
      >
      <button
        class="text-button"
        :disabled="
          workspace.annotationPage.value * 20 >= workspace.annotationTotal.value
        "
        @click="workspace.loadAnnotations(workspace.annotationPage.value + 1)"
      >
        下一页
      </button>
    </nav>
    <article
      v-if="workspace.selectedAnnotation.value"
      class="annotation-detail"
    >
      <h3>完整评论与模型判定</h3>
      <pre>{{ workspace.selectedAnnotation.value.analysis_text }}</pre>
      <div
        v-for="item in workspace.selectedAnnotation.value.result?.annotations"
        :key="item.criterion"
      >
        <strong>{{ item.criterion }} · {{ item.label }}</strong>
        <p>原文证据：{{ item.evidence.join("；") }}</p>
        <p>判定依据：{{ item.basis }}</p>
      </div>
      <h4>待补充线索</h4>
      <p>
        {{
          workspace.selectedAnnotation.value.result?.unmatched_evidence.join(
            "；",
          ) || "无"
        }}
      </p>
    </article>
  </section>
</template>
