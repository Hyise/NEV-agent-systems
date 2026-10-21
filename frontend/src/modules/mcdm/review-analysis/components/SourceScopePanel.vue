<script setup lang="ts">
import { useWorkspace } from "../../workspace";
import { useReviewAnalysisWorkspace } from "../workspace";
const main = useWorkspace();
const workspace = useReviewAnalysisWorkspace();
</script>

<template>
  <section class="review-analysis-section">
    <header>
      <span class="section-kicker">01 · 来源与准则版本</span>
      <h2>选择已采集车系</h2>
      <p>这里只读取评论资产，不会触发新的网页采集。</p>
    </header>
    <div v-if="main.isPreset.value" class="notice info">
      预置研究归档保持只读。请新建自定义准则研究，再使用准则发现或逐条评论标注。
      <button class="text-button" @click="main.openCreate('custom')">
        新建自定义研究
      </button>
    </div>
    <div v-else class="source-selector">
      <form class="source-search" @submit.prevent="workspace.loadSources(1)">
        <label>
          搜索车系名称或 ID
          <input
            v-model="workspace.sourceQuery.value"
            placeholder="例如：Model Y 或 5769"
          />
        </label>
        <button class="btn secondary" type="submit">搜索</button>
      </form>
      <label
        v-for="source in workspace.sources.value"
        :key="source.series_id"
        class="source-choice"
      >
        <input
          type="checkbox"
          :checked="
            workspace.selectedSeriesIds.value.includes(source.series_id)
          "
          @change="workspace.toggleSeries(source.series_id)"
        />
        <span
          ><strong>{{ source.series_name }}</strong
          ><small
            >series_id {{ source.series_id }} ·
            {{ source.review_count }} 条完整评论</small
          ></span
        >
      </label>
      <div v-if="!workspace.sources.value.length" class="empty">
        没有匹配的已采集车系。
      </div>
    </div>
    <nav
      v-if="!main.isPreset.value && workspace.sourceTotal.value"
      class="pager"
      aria-label="车系列表分页"
    >
      <button
        class="text-button"
        :disabled="workspace.sourcePage.value <= 1"
        @click="workspace.loadSources(workspace.sourcePage.value - 1)"
      >
        上一页
      </button>
      <span
        >第 {{ workspace.sourcePage.value }} 页 · 共
        {{ workspace.sourceTotal.value }} 个车系</span
      >
      <button
        class="text-button"
        :disabled="
          workspace.sourcePage.value * 20 >= workspace.sourceTotal.value
        "
        @click="workspace.loadSources(workspace.sourcePage.value + 1)"
      >
        下一页
      </button>
    </nav>
    <div v-if="!main.isPreset.value" class="scope-actions">
      <label v-if="workspace.schemaStatus.value === 'draft'"
        >发现样本上限<input
          v-model.number="workspace.sampleLimit.value"
          type="number"
          min="1"
          max="5000"
      /></label>
      <label v-else
        >标注范围<select v-model="workspace.annotationLimit.value">
          <option :value="20">20 条</option>
          <option :value="100">100 条</option>
          <option :value="500">500 条</option>
          <option :value="null">全部评论</option>
        </select></label
      >
      <template v-if="workspace.schemaStatus.value === 'frozen'">
        <label
          >开始日期<input
            v-model="workspace.reviewDateFrom.value"
            type="date"
            aria-label="评论开始日期"
        /></label>
        <label
          >结束日期<input
            v-model="workspace.reviewDateTo.value"
            type="date"
            aria-label="评论结束日期"
        /></label>
        <label
          >抽样口径<select v-model="workspace.annotationSampling.value">
            <option value="series">车系均衡</option>
            <option value="month_series">月份与车系均衡</option>
          </select></label
        >
      </template>
      <span>已选 {{ workspace.availableReviews.value }} 条可用评论</span>
      <button
        v-if="workspace.schemaStatus.value === 'draft'"
        class="btn primary"
        :disabled="
          !workspace.selectedSeriesIds.value.length || workspace.busy.value
        "
        title="先选择车系，再启动准则发现"
        @click="workspace.createDiscovery"
      >
        启动准则发现
      </button>
      <button
        v-else
        class="btn primary"
        :disabled="
          !workspace.selectedSeriesIds.value.length || workspace.busy.value
        "
        title="冻结版本才可逐条标注"
        @click="workspace.createAnnotation"
      >
        启动逐条评论标注
      </button>
    </div>
  </section>
</template>
