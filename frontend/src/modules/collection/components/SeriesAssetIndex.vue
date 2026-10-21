<script setup lang="ts">
import { computed, ref } from "vue";
import { Search } from "lucide-vue-next";
import type { ReviewAssetSummaryStats } from "../api";

const props = defineProps<{
  series: ReviewAssetSummaryStats["by_series"];
  selectedSeriesId: string;
  totalReviews: number;
  busy: boolean;
}>();

const emit = defineEmits<{
  select: [seriesId: string];
}>();

const query = ref("");
const visibleSeries = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase("zh-CN");
  if (!keyword) return props.series;
  return props.series.filter(
    (series) =>
      series.series_name.toLocaleLowerCase("zh-CN").includes(keyword) ||
      series.series_id.toLocaleLowerCase("zh-CN").includes(keyword),
  );
});
</script>

<template>
  <aside class="series-asset-index" aria-labelledby="series-index-title">
    <header class="series-asset-index__header">
      <div>
        <p class="collection-eyebrow">评论归档索引</p>
        <h2 id="series-index-title">车型列表</h2>
      </div>
      <strong class="mono">{{ series.length }}</strong>
      <span>种车型</span>
    </header>

    <label class="series-asset-index__search">
      <span class="visually-hidden">搜索车型名称或 ID</span>
      <Search :size="14" aria-hidden="true" />
      <input v-model="query" type="search" placeholder="搜索车型名称或 ID" />
    </label>

    <nav class="series-asset-index__list" aria-label="按车型查看评论">
      <button
        type="button"
        :class="['series-index-row', { active: !selectedSeriesId }]"
        :aria-pressed="!selectedSeriesId"
        :disabled="busy"
        @click="emit('select', '')"
      >
        <span><strong>全部车型</strong><small>查看完整评论库</small></span>
        <span class="series-index-row__count mono">{{ totalReviews }}</span>
      </button>
      <button
        v-for="series in visibleSeries"
        :key="series.series_id"
        type="button"
        :class="[
          'series-index-row',
          { active: selectedSeriesId === series.series_id },
        ]"
        :aria-pressed="selectedSeriesId === series.series_id"
        :disabled="busy"
        @click="emit('select', series.series_id)"
      >
        <span
          ><strong>{{ series.series_name }}</strong
          ><small class="mono">ID {{ series.series_id }}</small></span
        >
        <span class="series-index-row__count mono">{{ series.count }}</span>
      </button>
    </nav>

    <p v-if="query && !visibleSeries.length" class="series-index-empty">
      没有匹配的车型，请更换名称或 ID。
    </p>
  </aside>
</template>
