<script setup lang="ts">
import { computed } from "vue";
import { BarChart3, Search } from "lucide-vue-next";
import BaseChart from "../../../components/BaseChart.vue";
import { pct, useWorkspace } from "../workspace";

const { month, predictions, visiblePredictions, query, isPreset, changeMonth } =
  useWorkspace();

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
    data: visiblePredictions.value.slice(0, 10).map((row) => row.model),
    axisLine: { show: false },
    axisTick: { show: false },
  },
  series: [
    {
      name: "真实样本份额",
      type: "bar",
      barWidth: 8,
      data: visiblePredictions.value.slice(0, 10).map((row) => row.actual),
    },
    {
      name: "归档模型估计",
      type: "bar",
      barWidth: 8,
      data: visiblePredictions.value.slice(0, 10).map((row) => row.predicted),
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
    <div class="notice info source-status">
      {{
        predictions.length
          ? "归档模型在训练时见过评估月份；此页用于研究复核，不作为独立测试成绩或未来销量承诺。"
          : "所选月份没有归档预测。预置研究仅提供2025年11月和12月结果，自定义项目需后续训练。"
      }}
    </div>
    <div v-if="predictions.length" class="analysis-document share-evidence">
      <header class="analysis-heading">
        <div>
          <h2>车型选择份额对照</h2>
          <p>
            {{ month }} · {{ predictions.length }}款入选车型 ·
            图表展示真实份额前10款
          </p>
        </div>
        <span class="badge amber">历史条件份额估计</span>
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
          v-if="visiblePredictions.length"
          :option="shareOption"
          label="各车型真实份额与归档模型估计比较"
          height="410px"
        />
        <div v-else class="empty"><p>没有匹配的车型，请修改搜索条件。</p></div>
      </div>
      <details class="analysis-details">
        <summary>查看全部份额明细（{{ visiblePredictions.length }}款）</summary>
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
              <tr v-for="row in visiblePredictions" :key="row.model">
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
      <p v-else>当前可完成准则定义和加工数据导入。</p>
      <button v-if="isPreset" class="btn secondary" @click="showLatestArchive">
        查看2025年12月
      </button>
    </div>
  </section>
</template>
