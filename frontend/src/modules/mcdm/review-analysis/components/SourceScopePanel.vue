<script setup lang="ts">
import { useReviewAnalysisWorkspace } from "../workspace";
const workspace = useReviewAnalysisWorkspace();
</script>

<template>
  <section class="review-analysis-section">
    <header><span class="section-kicker">01 · 来源与准则版本</span><h2>选择已采集车系</h2><p>这里只读取评论资产，不会触发新的网页采集。</p></header>
    <div class="source-selector">
      <label v-for="source in workspace.sources.value" :key="source.series_id" class="source-choice">
        <input type="checkbox" :checked="workspace.selectedSeriesIds.value.includes(source.series_id)" @change="workspace.toggleSeries(source.series_id)" />
        <span><strong>{{ source.series_name }}</strong><small>series_id {{ source.series_id }} · {{ source.review_count }} 条完整评论</small></span>
      </label>
    </div>
    <div class="scope-actions">
      <label v-if="workspace.schemaStatus.value === 'draft'">发现样本上限<input v-model.number="workspace.sampleLimit.value" type="number" min="1" max="5000" /></label>
      <label v-else>标注范围<select v-model="workspace.annotationLimit.value"><option :value="20">20 条</option><option :value="100">100 条</option><option :value="500">500 条</option><option :value="null">全部评论</option></select></label>
      <span>已选 {{ workspace.availableReviews.value }} 条可用评论</span>
      <button v-if="workspace.schemaStatus.value === 'draft'" class="btn primary" :disabled="!workspace.selectedSeriesIds.value.length || workspace.busy.value" title="先选择车系，再启动准则发现" @click="workspace.createDiscovery">启动准则发现</button>
      <button v-else class="btn primary" :disabled="!workspace.selectedSeriesIds.value.length || workspace.busy.value" title="冻结版本才可逐条标注" @click="workspace.createAnnotation">启动逐条评论标注</button>
    </div>
  </section>
</template>

