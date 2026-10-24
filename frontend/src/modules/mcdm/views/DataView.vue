<script setup lang="ts">
import { computed } from "vue";
import {
  ArrowDownToLine,
  ArrowRight,
  CircleAlert,
  ChevronLeft,
  ChevronRight,
  Database,
  Plus,
  Search,
} from "lucide-vue-next";
import { formatTimePressure } from "../timePressure";
import { count, pct, useWorkspace } from "../workspace";

const {
  overview,
  matrixHandoff,
  month,
  data,
  isPreset,
  saving,
  busy,
  fileInput,
  query,
  pageNumber,
  download,
  materializeHandoff,
  navigate,
  importFile,
  searchData,
  previousPage,
  nextPage,
} = useWorkspace();

const handoffState = computed(() => {
  const labels = {
    not_frozen: "待冻结",
    no_job: "尚未开始",
    processing: "正在处理",
    failed: "处理失败",
    blocked: "需要处理",
    ready: "可以生成",
    materialized: "已生成",
  };
  return matrixHandoff.value ? labels[matrixHandoff.value.state] : "读取中";
});

const handoffAction = computed(() => {
  if (matrixHandoff.value?.state === "not_frozen") return "前往准则工作台";
  if (matrixHandoff.value?.state === "ready") return "生成评价矩阵快照";
  if (
    matrixHandoff.value?.state === "blocked" &&
    matrixHandoff.value.matrix?.exclusion_eligible
  )
    return "排除销量缺口并生成快照";
  if (matrixHandoff.value?.state === "blocked") return "处理阻塞项";
  if (matrixHandoff.value?.state === "processing") return "查看处理进度";
  if (matrixHandoff.value?.state === "failed") return "查看失败任务";
  if (matrixHandoff.value?.state === "materialized") return "进入模型实验";
  return "开始评论分析";
});

function continueHandoff() {
  if (matrixHandoff.value?.state === "not_frozen") {
    navigate("criteria");
    return;
  }
  if (matrixHandoff.value?.state === "ready") {
    void materializeHandoff();
    return;
  }
  if (
    matrixHandoff.value?.state === "blocked" &&
    matrixHandoff.value.matrix?.exclusion_eligible
  ) {
    const matrix = matrixHandoff.value.matrix;
    const coverage = (
      (matrix.stats.records / matrix.stats.groups) *
      100
    ).toFixed(2);
    const confirmed = window.confirm(
      `来源分组 ${matrix.stats.groups} 个；将保留 ${matrix.stats.records} 个可用分组，排除 ${matrix.stats.blocked_groups} 个仅缺少销量的分组，覆盖率 ${coverage}%。排除名单会随快照保存，是否继续？`,
    );
    if (confirmed) void materializeHandoff("exclude_missing_sales");
    return;
  }
  if (matrixHandoff.value?.state === "materialized") {
    navigate("experiments");
    return;
  }
  navigate("review-analysis");
}
</script>

<template>
  <section v-if="overview" class="research-surface data-workspace">
    <header class="data-command-bar">
      <div>
        <h2>{{ overview.dataset?.name || "项目数据集" }}</h2>
        <p>
          {{ month || "当前准则版本" }} · {{ count(data.month_models) }}款车型 ·
          样本总销量
          {{ count(data.month_total_sales) }}
        </p>
      </div>
      <div class="button-group">
        <button
          v-if="!isPreset"
          class="btn secondary"
          @click="download('template')"
        >
          CSV表头模板
        </button>
        <button
          v-if="!isPreset"
          class="btn primary"
          :disabled="overview.schema.status !== 'frozen' || saving"
          @click="fileInput?.click()"
        >
          <Plus :size="16" />导入加工数据
        </button>
        <button
          class="btn secondary"
          :disabled="!overview.dataset"
          @click="download('dataset')"
        >
          <ArrowDownToLine :size="16" />导出CSV
        </button>
      </div>
    </header>
    <input
      ref="fileInput"
      name="dataset-csv"
      type="file"
      accept=".csv"
      hidden
      tabindex="-1"
      :disabled="isPreset || overview.schema.status !== 'frozen' || saving"
      aria-label="导入加工CSV"
      @change="importFile"
    />
    <div v-if="!isPreset" class="notice info">
      {{
        overview.schema.status === "draft"
          ? "先在准则工作台保存并冻结版本，再导入数据。"
          : '上传UTF-8 CSV；列含产品型号、观察区间、时间压力、Real_Sales及各准则。2026年起时间压力可留空并统一按无压力处理。准则单元格为 {"L0":0.7,"L1":0.3} 形式的概率对象，等级数需匹配当前版本。'
      }}
    </div>
    <section
      v-if="!isPreset && matrixHandoff"
      class="dataset-handoff"
      aria-labelledby="dataset-handoff-title"
    >
      <header class="dataset-handoff__heading">
        <div>
          <span class="section-kicker">内部研究结果</span>
          <h3 id="dataset-handoff-title">评论研究交接</h3>
          <p>
            评论判定先按月份与车系聚合，再与同期销量匹配；无法取得销量时可显式排除，并保留审计记录。
          </p>
        </div>
        <span
          :class="[
            'badge',
            matrixHandoff.state === 'blocked' ? 'amber' : 'teal',
          ]"
          >{{ handoffState }}</span
        >
      </header>

      <div
        v-if="matrixHandoff.state === 'materialized' && matrixHandoff.dataset"
        class="dataset-handoff__track"
      >
        <div>
          <span>来源分组</span>
          <strong>{{ count(matrixHandoff.dataset.source_group_count) }}</strong>
          <small>生成前总量</small>
        </div>
        <div>
          <span>纳入快照</span>
          <strong>{{ count(matrixHandoff.dataset.included_count) }}</strong>
          <small>可用于模型</small>
        </div>
        <div :class="{ blocked: matrixHandoff.dataset.excluded_count }">
          <span>审计排除</span>
          <strong>{{ count(matrixHandoff.dataset.excluded_count) }}</strong>
          <small>原始数据仍保留</small>
        </div>
        <div>
          <span>样本覆盖</span>
          <strong>{{ pct(matrixHandoff.dataset.coverage_rate) }}</strong>
          <small>纳入 / 来源</small>
        </div>
      </div>
      <div v-else-if="matrixHandoff.matrix" class="dataset-handoff__track">
        <div>
          <span>评论快照</span>
          <strong>{{
            count(matrixHandoff.matrix.stats.source_reviews)
          }}</strong>
          <small>去重评论</small>
        </div>
        <div>
          <span>聚合范围</span>
          <strong>{{ count(matrixHandoff.matrix.stats.groups) }}</strong>
          <small>月份 × 车系</small>
        </div>
        <div>
          <span>当前可用</span>
          <strong>{{ count(matrixHandoff.matrix.stats.records) }}</strong>
          <small>待写入记录</small>
        </div>
        <div :class="{ blocked: matrixHandoff.matrix.stats.blocked_groups }">
          <span>生成检查</span>
          <strong>{{
            count(matrixHandoff.matrix.stats.blocked_groups)
          }}</strong>
          <small>阻塞分组</small>
        </div>
      </div>

      <div v-else class="dataset-handoff__pending">
        <Database :size="24" aria-hidden="true" />
        <span v-if="matrixHandoff.state === 'processing'"
          >评论任务仍在运行，完成后会自动形成矩阵预览。</span
        >
        <span v-else-if="matrixHandoff.state === 'not_frozen'"
          >当前准则仍是草稿；冻结后才能创建逐条评论标注任务。</span
        >
        <span v-else-if="matrixHandoff.state === 'failed'"
          >最近的评论任务未完成，请进入评论语义分析查看失败原因。</span
        >
        <span v-else>当前版本还没有可交接的评论标注任务。</span>
      </div>

      <details
        v-if="matrixHandoff.dataset?.excluded_count"
        class="matrix-coverage-note"
      >
        <summary>
          查看 {{ count(matrixHandoff.dataset.excluded_count) }} 个排除分组
        </summary>
        <p>这些分组仅因缺少销量而未进入模型矩阵，评论与排除原因均未被删除。</p>
        <ul>
          <li
            v-for="item in matrixHandoff.dataset.exclusions"
            :key="item.month + ':' + item.series_id"
          >
            {{ item.month }} · {{ item.series_name }} ·
            {{ item.issues.map((issue) => issue.message).join("；") }}
          </li>
        </ul>
      </details>

      <div
        v-if="matrixHandoff.compatibility === 'fingerprint'"
        class="dataset-handoff__lineage"
      >
        <span>复用 V{{ matrixHandoff.job?.source_schema_version }} 标注</span>
        <p>
          当前 V{{ matrixHandoff.target_schema_version }}
          的准则内容完全一致；生成时仍会创建独立快照并记录来源，不会再次调用大模型。
        </p>
      </div>

      <footer class="dataset-handoff__actions">
        <div v-if="matrixHandoff.state === 'blocked'">
          <CircleAlert :size="17" aria-hidden="true" />
          <span v-if="matrixHandoff.matrix?.exclusion_eligible"
            >有
            {{ count(matrixHandoff.matrix?.stats.blocked_groups ?? 0) }}
            个分组仅缺少销量；确认后可审计排除，剩余分组的月内份额会重新归一化。</span
          >
          <span v-else
            >还有
            {{ count(matrixHandoff.matrix?.stats.blocked_groups ?? 0) }}
            个不可自动排除的分组，请进入评论分析处理。</span
          >
        </div>
        <div v-else-if="matrixHandoff.state === 'materialized'">
          <span>该准则版本已有不可变权威快照，可直接进入模型实验。</span>
        </div>
        <div v-else>
          <span>所有操作都绑定当前准则 V{{ overview.schema.version }}。</span>
        </div>
        <button
          class="btn primary"
          type="button"
          :disabled="busy || saving"
          @click="continueHandoff"
        >
          {{ handoffAction }} <ArrowRight :size="15" />
        </button>
      </footer>
    </section>
    <div class="dataset-toolbar">
      <div class="dataset-filter-bar">
        <label class="search-field">
          <Search :size="17" />
          <input
            v-model="query"
            name="dataset-search"
            autocomplete="off"
            aria-label="搜索车型"
            placeholder="搜索车型名称…"
            @input="searchData"
          />
        </label>
        <span class="caption">份额分母固定为当月全部入选车型</span>
      </div>
    </div>
    <div class="data-table-region">
      <div v-if="data.rows.length" class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>车型</th>
              <th>观察月份</th>
              <th class="numeric">销量 / 辆</th>
              <th class="numeric">样本内份额</th>
              <th class="numeric">时间压力（2026年前）</th>
              <th class="numeric">准则覆盖</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in data.rows" :key="row.model">
              <td>
                <strong>{{ row.model }}</strong>
              </td>
              <td class="mono">{{ row.month }}</td>
              <td class="numeric mono">{{ count(row.sales) }}</td>
              <td class="numeric mono">{{ pct(row.share) }}</td>
              <td class="numeric mono">
                {{ formatTimePressure(row.month, row.pressure) }}
              </td>
              <td class="numeric">
                <span class="badge teal"
                  >{{ Object.keys(row.probabilities).length }} /
                  {{ overview.stats.criteria }}</span
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty">
        <Database :size="34" />
        <h3>{{ query ? "没有匹配的车型" : "此版本还没有数据" }}</h3>
        <p>
          {{
            query
              ? "换一个车型名称，或清空搜索条件。"
              : matrixHandoff?.state === "blocked"
                ? "评论矩阵已形成预览，请先处理上方阻塞项。"
                : matrixHandoff?.state === "ready"
                  ? "评论矩阵已通过检查，请在上方生成正式快照。"
                  : "冻结准则后，可导入加工数据或启动评论分析。"
          }}
        </p>
      </div>
      <div class="pagination">
        <span
          >共 {{ count(data.total) }} 条 · 第 {{ pageNumber }} /
          {{ Math.max(1, Math.ceil(data.total / 15)) }} 页</span
        >
        <div>
          <button
            class="icon-btn"
            aria-label="上一页"
            :disabled="pageNumber <= 1 || busy"
            @click="previousPage"
          >
            <ChevronLeft :size="18" />
          </button>
          <button
            class="icon-btn"
            aria-label="下一页"
            :disabled="pageNumber * 15 >= data.total || busy"
            @click="nextPage"
          >
            <ChevronRight :size="18" />
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
