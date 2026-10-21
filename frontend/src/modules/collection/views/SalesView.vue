<script setup lang="ts">
import { computed } from "vue";
import type { SalesPlatform } from "../api";
import type { SalesWorkspace } from "../salesWorkspace";

const props = defineProps<{ workspace: SalesWorkspace }>();

const platformLabel: Record<SalesPlatform, string> = {
  autohome: "汽车之家",
  dongchedi: "懂车帝",
  yiche: "易车",
};

const statusLabel = {
  queued: "等待执行",
  running: "采集中",
  completed: "已完成",
  partial_failed: "部分完成",
  failed: "失败",
};

const stepStatusLabel = {
  queued: "等待",
  running: "采集中",
  completed: "完成",
  failed: "受阻",
};

const activeOrLatest = computed(
  () =>
    props.workspace.overview.value?.active_job ??
    props.workspace.overview.value?.latest_job,
);

function checked(platform: SalesPlatform) {
  return props.workspace.selectedPlatforms.value.includes(platform);
}
</script>

<template>
  <section class="sales-workspace" aria-label="销量数据采集">
    <ol class="sales-stage-rail" aria-label="销量采集流程">
      <li><span>01</span><strong>选择月份与来源</strong></li>
      <li><span>02</span><strong>执行月榜采集</strong></li>
      <li><span>03</span><strong>匹配评论车系</strong></li>
      <li><span>04</span><strong>查询与导出</strong></li>
    </ol>

    <div class="sales-summary" aria-label="销量数据概览">
      <span
        >已入库
        <strong class="mono">{{
          workspace.overview.value?.record_count ?? 0
        }}</strong></span
      >
      <span
        >已匹配
        <strong class="mono">{{
          workspace.overview.value?.matched_count ?? 0
        }}</strong></span
      >
      <span
        >待复核
        <strong class="mono">{{
          workspace.overview.value?.unmatched_count ?? 0
        }}</strong></span
      >
      <span>口径 <strong>全国月度零售量</strong></span>
    </div>

    <div v-if="workspace.error.value" class="notice error" role="alert">
      {{ workspace.error.value }}
    </div>

    <section class="sales-create-panel" aria-labelledby="sales-create-title">
      <header>
        <div>
          <p class="collection-eyebrow">新建销量任务</p>
          <h2 id="sales-create-title">按月抓取完整车系榜单</h2>
        </div>
        <p>一次请求一份月榜，再在本机与评论车型匹配，不逐车型访问详情页。</p>
      </header>

      <form @submit.prevent="workspace.startJob">
        <label
          >开始月份<input
            v-model="workspace.startMonth.value"
            type="month"
            required
        /></label>
        <label
          >结束月份<input
            v-model="workspace.endMonth.value"
            type="month"
            required
        /></label>
        <fieldset class="sales-source-picker">
          <legend>来源平台</legend>
          <label
            v-for="source in workspace.overview.value?.sources ?? []"
            :key="source.platform"
            :class="{
              'source-restricted':
                source.availability === 'verification_required',
            }"
          >
            <input
              type="checkbox"
              :checked="checked(source.platform)"
              @change="workspace.togglePlatform(source.platform)"
            />
            <span
              ><strong>{{ source.label }}</strong
              ><small>{{ source.description }}</small></span
            >
            <em v-if="source.availability === 'verification_required'"
              >需人工验证</em
            >
            <em v-else>可直接采集</em>
          </label>
        </fieldset>
        <p class="sales-compliance-note">
          懂车帝和易车当前为
          <code>verification_required</code
          >：系统不会绕过验证，受阻月份会保留错误记录。
        </p>
        <button
          class="btn primary"
          type="submit"
          :disabled="
            workspace.actionBusy.value ||
            Boolean(workspace.overview.value?.active_job)
          "
        >
          {{ workspace.actionBusy.value ? "正在创建…" : "开始销量采集" }}
        </button>
      </form>
    </section>

    <section
      v-if="activeOrLatest"
      class="sales-job-panel"
      aria-labelledby="sales-job-title"
    >
      <header>
        <div>
          <p class="collection-eyebrow">任务执行</p>
          <h2 id="sales-job-title">
            {{ activeOrLatest.start_month }} 至 {{ activeOrLatest.end_month }}
          </h2>
        </div>
        <strong :data-status="activeOrLatest.status">{{
          statusLabel[activeOrLatest.status]
        }}</strong>
      </header>
      <div
        class="sales-progress"
        role="progressbar"
        :aria-valuemax="activeOrLatest.total_steps"
        :aria-valuenow="
          activeOrLatest.completed_steps + activeOrLatest.failed_steps
        "
      >
        <span
          :style="{
            width: `${((activeOrLatest.completed_steps + activeOrLatest.failed_steps) / activeOrLatest.total_steps) * 100}%`,
          }"
        />
      </div>
      <p>
        已完成 {{ activeOrLatest.completed_steps }} /
        {{ activeOrLatest.total_steps }} 个平台月份， 失败
        {{ activeOrLatest.failed_steps }}，写入
        {{ activeOrLatest.record_count }} 条。
      </p>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>平台</th>
              <th>月份</th>
              <th>状态</th>
              <th>记录数</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="step in workspace.detail.value?.steps ?? []"
              :key="`${step.platform}-${step.month}`"
            >
              <td>{{ platformLabel[step.platform] }}</td>
              <td class="mono">{{ step.month }}</td>
              <td>{{ stepStatusLabel[step.status] }}</td>
              <td class="mono">{{ step.record_count }}</td>
              <td>{{ step.error_message ?? "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="sales-record-panel" aria-labelledby="sales-record-title">
      <header>
        <div>
          <p class="collection-eyebrow">入库结果</p>
          <h2 id="sales-record-title">销量记录与车型匹配</h2>
        </div>
        <a class="btn secondary" :href="workspace.exportUrl.value" download
          >导出 CSV</a
        >
      </header>
      <form class="sales-filters" @submit.prevent="workspace.applyFilters">
        <label
          >平台<select v-model="workspace.filters.platform">
            <option value="">全部平台</option>
            <option value="autohome">汽车之家</option>
            <option value="dongchedi">懂车帝</option>
            <option value="yiche">易车</option>
          </select></label
        >
        <label
          >月份<input v-model="workspace.filters.month" type="month"
        /></label>
        <label
          >车型<input
            v-model="workspace.filters.search"
            type="search"
            placeholder="车系名称或 ID"
        /></label>
        <label
          >匹配状态<select v-model="workspace.filters.match_status">
            <option value="">全部状态</option>
            <option value="matched">已匹配</option>
            <option value="unmatched">未匹配</option>
            <option value="ambiguous">多候选</option>
          </select></label
        >
        <button
          class="btn secondary"
          type="submit"
          :disabled="workspace.recordsBusy.value"
        >
          应用筛选
        </button>
        <button
          class="text-button"
          type="button"
          @click="workspace.resetFilters"
        >
          清空
        </button>
      </form>
      <div class="table-scroll" :aria-busy="workspace.recordsBusy.value">
        <table>
          <thead>
            <tr>
              <th>平台</th>
              <th>月份</th>
              <th>排名</th>
              <th>平台车系</th>
              <th>销量</th>
              <th>评论车系</th>
              <th>匹配状态</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in workspace.records.value.rows"
              :key="`${row.platform}-${row.month}-${row.series_id}`"
            >
              <td>{{ platformLabel[row.platform] }}</td>
              <td class="mono">{{ row.month }}</td>
              <td class="mono">{{ row.rank }}</td>
              <td>
                {{ row.series_name
                }}<small class="mono">{{ row.series_id }}</small>
              </td>
              <td class="mono">
                {{ row.sales_volume.toLocaleString("zh-CN") }}
              </td>
              <td>{{ row.review_series_name ?? "—" }}</td>
              <td>
                {{
                  row.match_status === "matched"
                    ? "已匹配"
                    : row.match_status === "ambiguous"
                      ? "多候选"
                      : "未匹配"
                }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p
        v-if="
          !workspace.recordsBusy.value && !workspace.records.value.rows.length
        "
        class="collection-empty-inline"
      >
        当前筛选下没有销量记录。
      </p>
      <footer class="asset-pagination">
        <span
          >第 {{ workspace.page.value }} 页 · 共
          {{ workspace.records.value.total }} 条</span
        >
        <div>
          <button
            class="text-button"
            :disabled="workspace.page.value <= 1"
            @click="workspace.previousPage"
          >
            上一页</button
          ><button
            class="text-button"
            :disabled="
              workspace.page.value * workspace.pageSize.value >=
              workspace.records.value.total
            "
            @click="workspace.nextPage"
          >
            下一页
          </button>
        </div>
      </footer>
    </section>
  </section>
</template>
