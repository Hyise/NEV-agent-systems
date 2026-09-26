<script setup lang="ts">
import { computed } from "vue";
import { Activity, Check } from "lucide-vue-next";
import Chart from "../Chart.vue";
import { pct, useWorkspace } from "../workspace";

const palette = [
  "#087f8c",
  "#d58b3d",
  "#536eaa",
  "#a26481",
  "#4e896c",
  "#648998",
];
const { overview, curveKind, curveCriteria, selectedCurves, toggleCriterion } =
  useWorkspace();

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
    data: selectedCurves.value.map((row) => row.month),
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
  series: curveCriteria.value.map((name) => ({
    name,
    type: "line",
    smooth: false,
    symbolSize: 5,
    showSymbol: false,
    lineStyle: { width: 2.5 },
    data: selectedCurves.value.map((row) => row.values[name]),
  })),
}));
</script>

<template>
  <section v-if="overview" class="panel">
    <div class="panel-heading">
      <div>
        <h2>时间压力与模型权重</h2>
        <p>沿真实月度观察点展示，不补造新情景下的计算结果。</p>
      </div>
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
    </div>
    <div
      v-if="selectedCurves.length && curveCriteria.length"
      class="line-legend"
      aria-label="曲线图例"
    >
      <span v-for="(name, index) in curveCriteria" :key="name">
        <i :style="{ background: palette[index % palette.length] }" />{{ name }}
      </span>
    </div>
    <template v-if="selectedCurves.length">
      <div class="curve-filters">
        <button
          v-for="criterion in overview.schema.criteria"
          :key="criterion.name"
          :class="[
            'filter-chip',
            { selected: curveCriteria.includes(criterion.name) },
          ]"
          :aria-pressed="curveCriteria.includes(criterion.name)"
          @click="toggleCriterion(criterion.name)"
        >
          <Check v-if="curveCriteria.includes(criterion.name)" :size="13" />{{
            criterion.name
          }}
        </button>
      </div>
      <Chart
        v-if="curveCriteria.length"
        :option="curveOption"
        :label="
          curveKind === 'weights'
            ? '各月份准则权重变化'
            : '各月份理性混合权重变化'
        "
        height="380px"
      />
      <div v-else class="empty"><p>选择至少一个准则以显示曲线。</p></div>
      <div class="notice info">
        {{
          curveKind === "weights"
            ? "准则权重由各准则效用范围归一化得到。"
            : "理性混合权重是BEV与心理抽样之间的混合系数，不是对真实消费者理性的直接测量。"
        }}
        此处使用原研究后处理报表，不能据此单独判断政策因果效应。
      </div>
      <details class="data-details">
        <summary>查看曲线对应数值</summary>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>月份</th>
                <th>时间压力</th>
                <th v-for="name in curveCriteria" :key="name">{{ name }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in selectedCurves" :key="row.month">
                <td class="mono">{{ row.month }}</td>
                <td class="mono">{{ row.pressure.toFixed(3) }}</td>
                <td v-for="name in curveCriteria" :key="name" class="mono">
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
      <h3>当前项目尚无模型运行结果</h3>
      <p>自定义准则不会复用预置研究的权重。新训练将在算法接入阶段开放。</p>
    </div>
  </section>
</template>
