<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Activity, Check } from "lucide-vue-next";
import BaseChart from "../../../components/BaseChart.vue";
import { diagnosticCurves } from "../model-experiments/results";
import { useModelExperimentWorkspace } from "../model-experiments/workspace";
import { formatTimePressure } from "../timePressure";
import { reconcileCurveCriteria, scenarioSourceNote } from "../scenario";
import { pct, useWorkspace } from "../workspace";

const palette = [
  "#0f7c82",
  "#c65a3a",
  "#536eaa",
  "#a26481",
  "#4e896c",
  "#648998",
];
const mainWorkspace = useWorkspace();
const {
  overview,
  curveKind,
  curveCriteria,
  selectedCurves,
  toggleCriterion,
  isPreset,
} = mainWorkspace;
const workspace = useModelExperimentWorkspace();
const customCurveCriteria = ref<string[]>([]);

onMounted(() => {
  if (!isPreset.value) void workspace.activate();
});
onBeforeUnmount(workspace.deactivate);

const completedRuns = computed(() =>
  workspace.runs.value.filter((run) => run.status === "completed"),
);
const displayedCurves = computed(() =>
  isPreset.value
    ? selectedCurves.value
    : diagnosticCurves(workspace.selectedRun.value, curveKind.value),
);
const availableCurveCriteria = computed(() => {
  const values = displayedCurves.value[0]?.values;
  return values
    ? Object.keys(values)
    : (overview.value?.schema.criteria.map((criterion) => criterion.name) ??
        []);
});
const activeCurveCriteria = computed(() =>
  isPreset.value ? curveCriteria.value : customCurveCriteria.value,
);
const selectedRunShortId = computed(
  () => workspace.selectedRun.value?.id.slice(0, 8) ?? "—",
);
const sourceNote = computed(() =>
  scenarioSourceNote(isPreset.value, curveKind.value),
);

watch(
  [availableCurveCriteria, isPreset],
  ([available, preset]) => {
    if (preset) {
      curveCriteria.value = reconcileCurveCriteria(
        curveCriteria.value,
        available,
      );
    } else {
      customCurveCriteria.value = reconcileCurveCriteria(
        customCurveCriteria.value,
        available,
      );
    }
  },
  { immediate: true },
);

function selectRun(event: Event) {
  void workspace.selectRun((event.target as HTMLSelectElement).value);
}

function toggleDisplayedCriterion(name: string) {
  if (isPreset.value) {
    toggleCriterion(name);
    return;
  }
  customCurveCriteria.value = customCurveCriteria.value.includes(name)
    ? customCurveCriteria.value.filter((criterion) => criterion !== name)
    : [...customCurveCriteria.value, name];
}

const curveOption = computed(() => ({
  color: palette,
  grid: { left: 56, right: 20, top: 20, bottom: 40 },
  tooltip: {
    trigger: "axis",
    renderMode: "richText",
    valueFormatter: (value: number) => pct(value),
  },
  xAxis: {
    type: "category",
    data: displayedCurves.value.map((row) => row.month),
    axisLine: { lineStyle: { color: "#dce5ea" } },
    axisTick: { show: false },
    axisLabel: { color: "#6b7f8b", hideOverlap: true },
  },
  yAxis: {
    type: "value",
    min: curveKind.value === "rationality" ? 0.2 : undefined,
    max: curveKind.value === "rationality" ? 0.85 : undefined,
    axisLabel: {
      formatter: (value: number) => (value * 100).toFixed(0) + "%",
      color: "#6b7f8b",
    },
    splitLine: { lineStyle: { color: "#edf2f5" } },
  },
  series: activeCurveCriteria.value.map((name) => ({
    name,
    type: "line",
    smooth: false,
    symbolSize: 5,
    showSymbol: false,
    lineStyle: { width: 2.5 },
    data: displayedCurves.value.map((row) => row.values[name]),
  })),
}));
</script>

<template>
  <section
    v-if="overview"
    class="research-surface analysis-document scenario-workspace"
  >
    <header class="analysis-heading">
      <div>
        <h2>时间压力与模型权重</h2>
        <p>
          {{
            isPreset
              ? "沿真实月度观察点展示；2026年起不再施加时间压力。"
              : "读取所选实验的BEAST月度诊断；2026年起有效时间压力固定为0。"
          }}
        </p>
      </div>
      <span class="badge neutral">
        {{ isPreset ? "月度归档" : `实验 ${selectedRunShortId}` }}
      </span>
    </header>

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
      <span class="caption">曲线来自所选实验的不可变结果记录</span>
    </div>

    <div
      v-if="displayedCurves.length"
      class="analysis-control-bar analysis-controls"
    >
      <div class="segmented" aria-label="曲线类型">
        <button
          :class="{ selected: curveKind === 'weights' }"
          @click="curveKind = 'weights'"
        >
          准则权重
        </button>
        <button
          :class="{ selected: curveKind === 'rationality' }"
          @click="curveKind = 'rationality'"
        >
          理性混合权重
        </button>
      </div>
      <div class="curve-filters">
        <button
          v-for="criterion in availableCurveCriteria"
          :key="criterion"
          :class="[
            'filter-chip',
            { selected: activeCurveCriteria.includes(criterion) },
          ]"
          :aria-pressed="activeCurveCriteria.includes(criterion)"
          @click="toggleDisplayedCriterion(criterion)"
        >
          <Check v-if="activeCurveCriteria.includes(criterion)" :size="13" />{{
            criterion
          }}
        </button>
      </div>
    </div>
    <div
      v-if="displayedCurves.length && activeCurveCriteria.length"
      class="line-legend"
      aria-label="曲线图例"
    >
      <span v-for="(name, index) in activeCurveCriteria" :key="name">
        <i :style="{ background: palette[index % palette.length] }" />{{ name }}
      </span>
    </div>
    <template v-if="displayedCurves.length">
      <div class="analysis-evidence">
        <BaseChart
          v-if="activeCurveCriteria.length"
          :option="curveOption"
          :label="
            curveKind === 'weights'
              ? '各月份准则权重变化'
              : '各月份理性混合权重变化'
          "
          height="380px"
        />
        <div v-else class="empty"><p>选择至少一个准则以显示曲线。</p></div>
      </div>
      <div class="notice info source-status">{{ sourceNote }}</div>
      <details class="data-details">
        <summary>查看曲线对应数值</summary>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>月份</th>
                <th>时间压力（2026年前）</th>
                <th v-for="name in activeCurveCriteria" :key="name">
                  {{ name }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in displayedCurves" :key="row.month">
                <td class="mono">{{ row.month }}</td>
                <td class="mono">
                  {{ formatTimePressure(row.month, row.pressure) }}
                </td>
                <td
                  v-for="name in activeCurveCriteria"
                  :key="name"
                  class="mono"
                >
                  {{ pct(row.values[name]!) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </template>
    <div v-else class="empty">
      <Activity :size="34" />
      <h3>
        {{
          isPreset
            ? "当前项目尚无模型运行结果"
            : "此实验没有可用的BEAST月度诊断"
        }}
      </h3>
      <p v-if="isPreset">
        自定义准则不会复用预置研究的权重；新实验的权重不会自动发布为此页的归档情景曲线。
      </p>
      <p v-else-if="workspace.busy.value">正在加载实验详情。</p>
      <p v-else>
        请选择包含BEAST-MCDM的新实验；功能升级前完成的旧实验不会伪造月度曲线。
      </p>
    </div>
  </section>
</template>
