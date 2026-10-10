<script setup lang="ts">
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  X,
} from "lucide-vue-next";
import { computed } from "vue";
import { useCollectionWorkspace } from "../workspace";

const workspace = useCollectionWorkspace();
const {
  reviews,
  selectedSeries,
  reviewDetail,
  reviewPage,
  dataBusy,
  selectedSeriesExportUrl,
  navigate,
  openReview,
  closeReview,
  previousReviewPage,
  nextReviewPage,
} = workspace;

const formattedReview = computed(() =>
  reviewDetail.value
    ? JSON.stringify(reviewDetail.value.original_review, null, 2)
    : "",
);

function dateTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
</script>

<template>
  <section v-if="selectedSeries" class="collection-reviews">
    <header class="collection-data-toolbar">
      <div>
        <p class="collection-eyebrow">当前车系</p>
        <h2>
          {{ selectedSeries.series_name }}
          <span class="mono">{{ selectedSeries.series_id }}</span>
        </h2>
        <p>列表仅显示索引信息；打开详情后读取完整原始评论对象。</p>
      </div>
      <a
        class="btn secondary"
        :href="selectedSeriesExportUrl"
        :download="`autohome-${selectedSeries.series_id}.jsonl`"
      >
        <Download :size="16" />导出该车系 JSONL
      </a>
    </header>

    <div v-if="reviews.rows.length" class="table-scroll" :aria-busy="dataBusy">
      <table>
        <thead>
          <tr>
            <th>评论 ID</th>
            <th>车系</th>
            <th>首次采集</th>
            <th>最近确认</th>
            <th><span class="visually-hidden">操作</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in reviews.rows" :key="item.review_id">
            <td class="mono">{{ item.review_id }}</td>
            <td>{{ item.series_name }}</td>
            <td>{{ dateTime(item.first_collected_at) }}</td>
            <td>{{ dateTime(item.last_confirmed_at) }}</td>
            <td>
              <button class="text-button" @click="openReview(item.review_id)">
                查看完整 JSON
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="!dataBusy" class="collection-empty-state">
      <h2>该车系尚无评论</h2>
      <p>可返回“采集任务”继续采集；已保存数据不会因停止任务而删除。</p>
    </div>

    <footer v-if="reviews.total" class="pagination">
      <span>第 {{ reviewPage }} 页 · 共 {{ reviews.total }} 条评论</span>
      <div>
        <button
          class="icon-btn"
          aria-label="上一页"
          :disabled="reviewPage <= 1 || dataBusy"
          @click="previousReviewPage"
        >
          <ChevronLeft :size="17" />
        </button>
        <button
          class="icon-btn"
          aria-label="下一页"
          :disabled="reviewPage * 20 >= reviews.total || dataBusy"
          @click="nextReviewPage"
        >
          <ChevronRight :size="17" />
        </button>
      </div>
    </footer>

    <aside
      v-if="reviewDetail"
      class="review-detail"
      aria-labelledby="review-detail-title"
    >
      <header>
        <div>
          <p class="collection-eyebrow">完整原始对象</p>
          <h2 id="review-detail-title" class="mono">
            {{ reviewDetail.review_id }}
          </h2>
        </div>
        <div class="button-group">
          <a
            class="text-button"
            :href="reviewDetail.source_url"
            target="_blank"
            rel="noreferrer"
            ><ExternalLink :size="15" />查看来源</a
          >
          <button
            class="icon-btn"
            aria-label="关闭评论详情"
            @click="closeReview"
          >
            <X :size="18" />
          </button>
        </div>
      </header>
      <pre>{{ formattedReview }}</pre>
    </aside>
  </section>

  <div v-else class="collection-empty-state">
    <h2>先选择一个车系</h2>
    <p>评论按车系查询和导出。请前往车系列表选择已发现的车系。</p>
    <button class="btn primary" @click="navigate('series')">前往车系</button>
  </div>
</template>
