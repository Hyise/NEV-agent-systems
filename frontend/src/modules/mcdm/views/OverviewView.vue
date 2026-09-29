<script setup lang="ts">
import { computed } from "vue";
import {
  ArrowDownToLine,
  ArrowRight,
  CircleHelp,
  FileCheck2,
  Layers3,
} from "lucide-vue-next";
import BaseChart from "../../../components/BaseChart.vue";
import { count, pct, useWorkspace } from "../workspace";

const {
  overview,
  month,
  isPreset,
  sortedWeights,
  topCriteria,
  navigate,
  download,
} = useWorkspace();

const weightOption = computed(() => ({
  grid: { left: 176, right: 56, top: 6, bottom: 15 },
  tooltip: {
    trigger: "axis",
    valueFormatter: (value: number) => pct(value),
    renderMode: "richText",
  },
  xAxis: { type: "value", show: false },
  yAxis: {
    type: "category",
    inverse: true,
    data: sortedWeights.value.map((criterion) => criterion[0]),
    axisTick: { show: false },
    axisLine: { show: false },
    axisLabel: {
      color: "#435b68",
      fontSize: 12,
      fontFamily: 'SimSun, "宋体", STSong, "Songti SC", serif',
    },
  },
  series: [
    {
      type: "bar",
      barWidth: 13,
      data: sortedWeights.value.map((criterion, index) => ({
        value: criterion[1],
        itemStyle: {
          color: index < 3 ? "#0f7c82" : "#c5dcde",
          borderRadius: [0, 2, 2, 0],
        },
      })),
      label: {
        show: true,
        position: "right",
        formatter: (params: { value: number }) => pct(params.value),
        color: "#385564",
        fontFamily: 'SimSun, "宋体", STSong, "Songti SC", serif',
      },
    },
  ],
}));
</script>

<template>
  <section v-if="overview">
    <div class="metric-strip" aria-label="研究数据概览">
      <div class="metric-strip__item">
        <span>车型月份记录</span>
        <strong class="metric-strip__value mono"
          >{{ count(overview.stats.records) }}<small>条</small></strong
        >
      </div>
      <div class="metric-strip__item">
        <span>覆盖车型</span>
        <strong class="metric-strip__value mono"
          >{{ count(overview.stats.models) }}<small>款</small></strong
        >
      </div>
      <div class="metric-strip__item">
        <span>观察窗口</span>
        <strong class="metric-strip__value mono"
          >{{ overview.stats.months }}<small>个月</small></strong
        >
      </div>
      <div class="metric-strip__item">
        <span>评价准则</span>
        <strong class="metric-strip__value mono"
          >{{ overview.stats.criteria }}<small>项</small></strong
        >
      </div>
    </div>
    <section class="overview-evidence">
      <header class="overview-evidence__heading">
        <div>
          <h2>消费者关注什么</h2>
          <p>准则相对权重 · {{ month || "等待数据" }}</p>
        </div>
        <span class="badge neutral">{{
          isPreset ? "研究归档" : "等待运行"
        }}</span>
      </header>
      <div class="overview-evidence__body">
        <div class="overview-evidence__chart">
          <BaseChart
            v-if="sortedWeights.length"
            :option="weightOption"
            label="十项准则的归档相对权重比较"
            height="338px"
          />
          <div v-else class="empty">
            <Layers3 :size="32" />
            <h3>从定义评价准则开始</h3>
            <p>冻结准则、导入数据后，后续模型运行将生成权重结果。</p>
            <button class="btn secondary" @click="navigate('criteria')">
              打开准则工作台<ArrowRight :size="16" />
            </button>
          </div>
        </div>
        <aside class="overview-evidence__summary">
          <p class="summary-label">权重摘要</p>
          <h2>{{ isPreset ? "本月观察" : "建立你的研究" }}</h2>
          <template v-if="topCriteria.length">
            <p class="insight-lead">当前权重最高的三个准则</p>
            <div
              v-for="([name, value], index) in topCriteria"
              :key="name"
              class="rank-item"
            >
              <span class="rank-number mono">0{{ index + 1 }}</span>
              <div>
                <strong>{{ name }}</strong>
                <div class="small-bar">
                  <span
                    :style="{
                      width: (value / topCriteria[0]![1]) * 100 + '%',
                    }"
                  />
                </div>
              </div>
              <span class="mono">{{ pct(value) }}</span>
            </div>
            <p class="caption">
              权重反映当前模型下的相对效用范围，不等于提及该属性的评论占比。
            </p>
          </template>
          <template v-else>
            <p class="summary-copy">
              自定义项目已与预置研究数据分离。按自己的研究问题定义评价准则和等级。
            </p>
            <p class="caption">
              等级按由优到劣排列；冻结后可派生新版本继续修改。
            </p>
          </template>
          <div class="evidence-trace">
            <FileCheck2 :size="18" />
            <div>
              <strong>数据与结论可追溯</strong>
              <p>导出包含来源、准则版本及指标口径。</p>
            </div>
          </div>
          <button class="btn secondary full-width" @click="download('report')">
            <ArrowDownToLine :size="16" />导出研究快照 JSON
          </button>
        </aside>
      </div>
      <footer v-if="sortedWeights.length" class="overview-evidence__footer">
        <span><span class="dot teal-dot" />数值来自原研究平滑报表</span>
        <button class="text-button" @click="navigate('scenario')">
          查看时间变化 <ArrowRight :size="14" />
        </button>
      </footer>
    </section>
    <section class="research-process">
      <header class="research-process__heading">
        <div>
          <h2>研究流程</h2>
          <p>本阶段已接入真实归档，下一阶段开放新的算法运行。</p>
        </div>
      </header>
      <div class="workflow">
        <div
          v-for="(step, index) in [
            '数据准备',
            '准则确认',
            '评论标注',
            '模型训练',
            '决策分析',
          ]"
          :key="step"
          :class="[
            'workflow-step',
            { available: index < 2 || (index === 4 && isPreset) },
          ]"
        >
          <span class="step-number mono">{{ index + 1 }}</span>
          <strong>{{ step }}</strong>
          <small>{{
            index < 2
              ? "已开放"
              : index === 4 && isPreset
                ? "可查看归档"
                : "后续接入"
          }}</small>
        </div>
      </div>
    </section>
    <div class="source-note">
      <CircleHelp :size="17" />
      <span>
        {{ overview.notes[0] }}
        {{ isPreset ? "归档实验存在训练测试重叠，指标仅供查阅。" : "" }}
      </span>
    </div>
  </section>
</template>
