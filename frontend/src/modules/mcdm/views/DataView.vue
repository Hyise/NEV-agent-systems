<script setup lang="ts">
import {
  ArrowDownToLine,
  ChevronLeft,
  ChevronRight,
  Database,
  Plus,
  Search,
} from "lucide-vue-next";
import { count, pct, useWorkspace } from "../workspace";

const {
  overview,
  month,
  data,
  isPreset,
  saving,
  busy,
  fileInput,
  query,
  pageNumber,
  download,
  importFile,
  searchData,
  previousPage,
  nextPage,
} = useWorkspace();
</script>

<template>
  <section v-if="overview" class="data-workspace">
    <header class="data-command-bar">
      <div>
        <h2>{{ overview.dataset?.name || "项目数据集" }}</h2>
        <p>
          {{ month || "当前准则版本" }} · {{ count(data.month_models) }}款车型 ·
          样本总销量
          {{ count(data.month_total_sales) }}
        </p>
      </div>
      <div class="button-group">
        <button
          v-if="!isPreset"
          class="btn secondary"
          @click="download('template')"
        >
          CSV表头模板
        </button>
        <button
          v-if="!isPreset"
          class="btn primary"
          :disabled="overview.schema.status !== 'frozen' || saving"
          @click="fileInput?.click()"
        >
          <Plus :size="16" />导入加工数据
        </button>
        <button
          class="btn secondary"
          :disabled="!overview.dataset"
          @click="download('dataset')"
        >
          <ArrowDownToLine :size="16" />导出CSV
        </button>
      </div>
    </header>
    <input
      ref="fileInput"
      name="dataset-csv"
      type="file"
      accept=".csv"
      hidden
      tabindex="-1"
      :disabled="isPreset || overview.schema.status !== 'frozen' || saving"
      aria-label="导入加工CSV"
      @change="importFile"
    />
    <div v-if="!isPreset" class="notice info">
      {{
        overview.schema.status === "draft"
          ? "先在准则工作台保存并冻结版本，再导入数据。"
          : '上传UTF-8 CSV；列含产品型号、观察区间、时间压力、Real_Sales及各准则。准则单元格为 {"L0":0.7,"L1":0.3} 形式的概率对象，等级数需匹配当前版本。'
      }}
    </div>
    <div class="dataset-toolbar">
      <div class="dataset-filter-bar">
        <label class="search-field">
          <Search :size="17" />
          <input
            v-model="query"
            name="dataset-search"
            autocomplete="off"
            aria-label="搜索车型"
            placeholder="搜索车型名称…"
            @input="searchData"
          />
        </label>
        <span class="caption">份额分母固定为当月全部入选车型</span>
      </div>
    </div>
    <div class="data-table-region">
      <div v-if="data.rows.length" class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>车型</th>
              <th>观察月份</th>
              <th class="numeric">销量 / 辆</th>
              <th class="numeric">样本内份额</th>
              <th class="numeric">时间压力</th>
              <th class="numeric">准则覆盖</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in data.rows" :key="row.model">
              <td>
                <strong>{{ row.model }}</strong>
              </td>
              <td class="mono">{{ row.month }}</td>
              <td class="numeric mono">{{ count(row.sales) }}</td>
              <td class="numeric mono">{{ pct(row.share) }}</td>
              <td class="numeric mono">{{ row.pressure.toFixed(3) }}</td>
              <td class="numeric">
                <span class="badge teal"
                  >{{ Object.keys(row.probabilities).length }} /
                  {{ overview.stats.criteria }}</span
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty">
        <Database :size="34" />
        <h3>{{ query ? "没有匹配的车型" : "此版本还没有数据" }}</h3>
        <p>
          {{
            query
              ? "换一个车型名称，或清空搜索条件。"
              : "冻结准则后，导入与它匹配的加工数据。"
          }}
        </p>
      </div>
      <div class="pagination">
        <span
          >共 {{ count(data.total) }} 条 · 第 {{ pageNumber }} /
          {{ Math.max(1, Math.ceil(data.total / 15)) }} 页</span
        >
        <div>
          <button
            class="icon-btn"
            aria-label="上一页"
            :disabled="pageNumber <= 1 || busy"
            @click="previousPage"
          >
            <ChevronLeft :size="18" />
          </button>
          <button
            class="icon-btn"
            aria-label="下一页"
            :disabled="pageNumber * 15 >= data.total || busy"
            @click="nextPage"
          >
            <ChevronRight :size="18" />
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
