<script setup lang="ts">
import { ChevronLeft, ChevronRight, Search } from "lucide-vue-next";
import { useCollectionWorkspace } from "../workspace";

const workspace = useCollectionWorkspace();
const {
  series,
  seriesQuery,
  seriesPage,
  dataBusy,
  searchSeries,
  selectSeries,
  previousSeriesPage,
  nextSeriesPage,
} = workspace;

function dateTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
</script>

<template>
  <section class="collection-data-table" aria-labelledby="series-table-title">
    <header class="collection-data-toolbar">
      <div>
        <h2 id="series-table-title">已发现车系</h2>
        <p>同一 series_id 的不同年款、改款和配置按一个车系管理。</p>
      </div>
      <label class="search-field">
        <Search :size="16" />
        <span class="visually-hidden">搜索车系名称或 ID</span>
        <input
          v-model="seriesQuery"
          type="search"
          placeholder="搜索车系名称或 ID"
          autocomplete="off"
          @input="searchSeries"
        />
      </label>
    </header>

    <div v-if="series.rows.length" class="table-scroll" :aria-busy="dataBusy">
      <table>
        <thead>
          <tr>
            <th>车系名称</th>
            <th>series_id</th>
            <th class="numeric">评论数</th>
            <th class="numeric">发现顺序</th>
            <th>最近确认</th>
            <th><span class="visually-hidden">操作</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in series.rows" :key="item.series_id">
            <td>
              <strong>{{ item.series_name }}</strong>
            </td>
            <td class="mono">{{ item.series_id }}</td>
            <td class="numeric mono">{{ item.comment_count }}</td>
            <td class="numeric mono">{{ item.discovery_rank }}</td>
            <td>{{ dateTime(item.last_confirmed_at) }}</td>
            <td>
              <button class="text-button" @click="selectSeries(item)">
                查看评论
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="!dataBusy" class="collection-empty-state">
      <h2>尚未发现车系</h2>
      <p>
        先在“采集任务”中运行功能验证，完成后可在这里按名称或 series_id 查询。
      </p>
    </div>

    <footer v-if="series.total" class="pagination">
      <span>第 {{ seriesPage }} 页 · 共 {{ series.total }} 个车系</span>
      <div>
        <button
          class="icon-btn"
          aria-label="上一页"
          :disabled="seriesPage <= 1 || dataBusy"
          @click="previousSeriesPage"
        >
          <ChevronLeft :size="17" />
        </button>
        <button
          class="icon-btn"
          aria-label="下一页"
          :disabled="seriesPage * 20 >= series.total || dataBusy"
          @click="nextSeriesPage"
        >
          <ChevronRight :size="17" />
        </button>
      </div>
    </footer>
  </section>
</template>
