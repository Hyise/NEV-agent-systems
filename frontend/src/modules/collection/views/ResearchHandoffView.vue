<script setup lang="ts">
import { computed } from "vue";
import { RouterLink } from "vue-router";
import type { AssetWorkspace } from "../assetWorkspace";

const props = defineProps<{ workspace: AssetWorkspace }>();
const stats = computed(() => props.workspace.summary.value);
const unavailableReasons = computed(() => {
  const result: string[] = [];
  if (!stats.value?.total)
    result.push("资产库中还没有评论，请先采集或导入数据。");
  if (stats.value?.analysis_disabled) {
    result.push(`${stats.value.analysis_disabled} 条评论已设为暂不参与分析。`);
  }
  if (stats.value?.total && !stats.value.analysis_enabled) {
    result.push("当前没有启用的评论，无法建立新的研究快照。");
  }
  return result;
});
</script>

<template>
  <section class="research-handoff" aria-label="评论数据研究交接">
    <header class="handoff-heading">
      <div>
        <p class="collection-eyebrow">研究准备度</p>
        <h2>确认可分析范围，再进入多准则研究</h2>
        <p>
          这里只读取服务端资产统计。进入研究系统后仍需由你选择车系并点击开始，不会自动创建任务，也不会自动调用大模型。
        </p>
      </div>
      <button
        class="text-button"
        :disabled="workspace.actionBusy.value"
        @click="workspace.loadSummary"
      >
        刷新统计
      </button>
    </header>

    <dl class="handoff-metrics">
      <div>
        <dt>评论资产</dt>
        <dd>{{ stats?.total ?? 0 }}</dd>
      </div>
      <div>
        <dt>可用于分析</dt>
        <dd>{{ stats?.analysis_enabled ?? 0 }}</dd>
      </div>
      <div>
        <dt>暂不分析</dt>
        <dd>{{ stats?.analysis_disabled ?? 0 }}</dd>
      </div>
      <div>
        <dt>来源种类</dt>
        <dd>{{ stats?.by_source.length ?? 0 }}</dd>
      </div>
    </dl>

    <section
      v-if="unavailableReasons.length"
      class="handoff-reasons"
      aria-labelledby="unavailable-title"
    >
      <h3 id="unavailable-title">不可用原因</h3>
      <ul>
        <li v-for="reason in unavailableReasons" :key="reason">{{ reason }}</li>
      </ul>
    </section>

    <section class="handoff-distribution" aria-labelledby="distribution-title">
      <header>
        <h3 id="distribution-title">可分析车系分布</h3>
        <span>按服务端当前资产统计</span>
      </header>
      <div v-if="stats?.by_series.length" class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>车系</th>
              <th>series_id</th>
              <th class="numeric">资产数</th>
              <th class="numeric">可分析</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="series in stats.by_series" :key="series.series_id">
              <td>{{ series.series_name }}</td>
              <td class="mono">{{ series.series_id }}</td>
              <td class="numeric mono">{{ series.count }}</td>
              <td class="numeric mono">{{ series.analysis_enabled }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="collection-empty-inline">尚无可交接的车系数据。</p>
    </section>

    <section class="handoff-actions" aria-labelledby="handoff-actions-title">
      <header>
        <p class="collection-eyebrow">下一阶段</p>
        <h3 id="handoff-actions-title">选择研究目的</h3>
      </header>
      <div>
        <article>
          <span class="mono">A</span>
          <h4>从评论发现评价准则</h4>
          <p>适用于自定义准则草稿，先从完整评论中归纳候选准则，再人工审核。</p>
          <RouterLink
            class="btn primary"
            :class="{ disabled: !stats?.analysis_enabled }"
            :aria-disabled="!stats?.analysis_enabled"
            :to="{ name: 'mcdm', query: { intent: 'criteria-discovery' } }"
            >进入准则发现</RouterLink
          >
        </article>
        <article>
          <span class="mono">B</span>
          <h4>按冻结准则逐条标注</h4>
          <p>适用于已经冻结的准则版本，提取每条评论的准则、等级与原文证据。</p>
          <RouterLink
            class="btn secondary"
            :class="{ disabled: !stats?.analysis_enabled }"
            :aria-disabled="!stats?.analysis_enabled"
            :to="{ name: 'mcdm', query: { intent: 'review-annotation' } }"
            >进入评论标注</RouterLink
          >
        </article>
      </div>
    </section>
  </section>
</template>
