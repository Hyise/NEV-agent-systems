<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { BarChart3, Search } from "lucide-vue-next";
import BaseChart from "../../../components/BaseChart.vue";
import {
  defaultPredictionModelKey,
  predictionModels,
  predictionMonths,
  predictionsFor,
} from "../model-experiments/results";
import { useModelExperimentWorkspace } from "../model-experiments/workspace";
import { pct, useWorkspace } from "../workspace";

const { month, predictions, query, isPreset, changeMonth } = useWorkspace();
const workspace = useModelExperimentWorkspace();
const selectedModelKey = ref("");
const selectedExperimentMonth = ref("");

onMounted(() => {
  if (!isPreset.value) void workspace.activate();
});
onBeforeUnmount(workspace.deactivate);

const completedRuns = computed(() =>
  workspace.runs.value.filter((run) => run.status === "completed"),
);
const modelOptions = computed(() =>
  predictionModels(workspace.selectedRun.value),
);
const monthOptions = computed(() =>
  predictionMonths(workspace.selectedRun.value, selectedModelKey.value),
);
const selectedModel = computed(() =>
  modelOptions.value.find((model) => model.key === selectedModelKey.value),
);

function synchronizeSelection() {
  if (
    !modelOptions.value.some((model) => model.key === selectedModelKey.value)
  ) {
    selectedModelKey.value = defaultPredictionModelKey(
      workspace.selectedRun.value,
    );
  }
  const months = predictionMonths(
    workspace.selectedRun.value,
    selectedModelKey.value,
  );
  if (!months.includes(selectedExperimentMonth.value)) {
    selectedExperimentMonth.value = months.at(-1) ?? "";
  }
}

watch(
  [() => workspace.selectedRun.value, modelOptions, selectedModelKey],
  synchronizeSelection,
  { immediate: true },
);

const analysisPredictions = computed(() =>
  isPreset.value
    ? predictions.value
    : predictionsFor(
        workspace.selectedRun.value,
        selectedModelKey.value,
        selectedExperimentMonth.value,
      ),
);
const visibleAnalysisPredictions = computed(() =>
  analysisPredictions.value.filter((row) =>
    row.model.toLowerCase().includes(query.value.toLowerCase()),
  ),
);
const displayedMonth = computed(() =>
  isPreset.value ? month.value : selectedExperimentMonth.value,
);

function selectRun(event: Event) {
  void workspace.selectRun((event.target as HTMLSelectElement).value);
}

const shareOption = computed(() => ({
  color: ["#0f7c82", "#c65a3a"],
  legend: { bottom: 0, icon: "roundRect", itemWidth: 12 },
  grid: { left: 105, right: 30, top: 8, bottom: 40 },
  tooltip: {
    trigger: "axis",
    renderMode: "richText",
    valueFormatter: (value: number) => pct(value),
  },
  xAxis: {
    type: "value",
    axisLabel: { formatter: (value: number) => (value * 100).toFixed(0) + "%" },
    splitLine: { lineStyle: { color: "#edf2f5" } },
  },
  yAxis: {
    type: "category",
    inverse: true,
    data: visibleAnalysisPredictions.value.slice(0, 10).map((row) => row.model),
    axisLine: { show: false },
    axisTick: { show: false },
  },
  series: [
    {
      name: "真实样本份额",
      type: "bar",
      barWidth: 8,
      data: visibleAnalysisPredictions.value
        .slice(0, 10)
        .map((row) => row.actual),
    },
    {
      name: isPreset.value
        ? "归档模型估计"
        : selectedModel.value?.label || "模型估计",
      type: "bar",
      barWidth: 8,
      data: visibleAnalysisPredictions.value
        .slice(0, 10)
        .map((row) => row.predicted),
    },
  ],
}));

function showLatestArchive() {
  month.value = "2025-12";
  changeMonth();
}
</script>

<template>
  <section class="research-surface shares-workspace">
    <div
      v-if="!isPreset"
      class="analysis-control-bar experiment-result-controls"
    >
      <label class="result-control">
        <span>实验记录</span>
        <select
          :value="workspace.selectedRunId.value"
          :disabled="workspace.busy.value || !completedRuns.length"
          @change="selectRun"
        >
          <option v-for="run in completedRuns" :key="run.id" :value="run.id">
            已完成 · {{ run.id.slice(0, 8) }}
          </option>
        </select>
      </label>
      <label class="result-control">
        <span>预测模型</span>
        <select v-model="selectedModelKey" :disabled="!modelOptions.length">
          <option
            v-for="model in modelOptions"
            :key="model.key"
            :value="model.key"
          >
            {{ model.label }}
          </option>
        </select>
      </label>
      <label class="result-control">
        <span>测试月份</span>
        <select
          v-model="selectedExperimentMonth"
          :disabled="!monthOptions.length"
        >
          <option v-for="value in monthOptions" :key="value" :value="value">
            {{ value }}
          </option>
        </select>
      </label>
      <span class="caption">候选集和份额分母保持所选实验的原始口径</span>
    </div>

    <div class="notice info source-status">
      {{
        analysisPredictions.length
          ? isPreset
            ? "归档模型在训练时见过评估月份；此页用于研究复核，不作为独立测试成绩或未来销量承诺。"
            : "当前结果来自所选实验的测试集；只用于同一快照、模型与月份内的研究复核。"
          : isPreset
            ? "所选月份没有归档预测。预置研究仅提供2025年11月和12月结果；新运行的测试结果请在模型实验中复核。"
            : "所选实验、模型或测试月份没有预测明细。"
      }}
    </div>
    <div
      v-if="analysisPredictions.length"
      class="analysis-document share-evidence"
    >
      <header class="analysis-heading">
        <div>
          <h2>车型选择份额对照</h2>
          <p>
            {{ displayedMonth }} · {{ analysisPredictions.length }}款入选车型 ·
            图表展示真实份额前10款
          </p>
        </div>
        <span :class="['badge', isPreset ? 'amber' : 'success']">
          {{ isPreset ? "历史条件份额估计" : selectedModel?.label }}
        </span>
      </header>
      <div class="analysis-control-bar">
        <label class="search-field">
          <Search :size="17" />
          <input
            v-model="query"
            name="prediction-search"
            autocomplete="off"
            aria-label="搜索预测车型"
            placeholder="搜索车型名称…"
          />
        </label>
        <span class="caption">筛选仅影响显示，不重新归一化</span>
      </div>
      <div class="analysis-evidence">
        <BaseChart
          v-if="visibleAnalysisPredictions.length"
          :option="shareOption"
          label="各车型真实份额与模型估计比较"
          height="410px"
        />
        <div v-else class="empty"><p>没有匹配的车型，请修改搜索条件。</p></div>
      </div>
      <details class="analysis-details">
        <summary>
          查看全部份额明细（{{ visibleAnalysisPredictions.length }}款）
        </summary>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>车型</th>
                <th class="numeric">真实份额</th>
                <th class="numeric">估计份额</th>
                <th class="numeric">差值 / 百分点</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in visibleAnalysisPredictions" :key="row.model">
                <td>{{ row.model }}</td>
                <td class="numeric mono">{{ pct(row.actual) }}</td>
                <td class="numeric mono">{{ pct(row.predicted) }}</td>
                <td
                  class="numeric mono"
                  :class="row.predicted > row.actual ? 'positive' : 'negative'"
                >
                  <span class="delta-label">{{
                    row.predicted > row.actual ? "高估" : "低估"
                  }}</span>
                  {{ row.predicted > row.actual ? "+" : ""
                  }}{{ ((row.predicted - row.actual) * 100).toFixed(2) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </div>
    <div v-else class="analysis-document empty">
      <BarChart3 :size="36" />
      <h3>暂无对应预测结果</h3>
      <p v-if="isPreset">请选择2025-11或2025-12查看归档。</p>
      <p v-else-if="workspace.busy.value">正在加载实验详情。</p>
      <p v-else>请选择一个已完成且包含预测明细的模型实验。</p>
      <button v-if="isPreset" class="btn secondary" @click="showLatestArchive">
        查看2025年12月
      </button>
    </div>
  </section>
</template>
