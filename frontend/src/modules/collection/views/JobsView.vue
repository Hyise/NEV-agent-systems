<script setup lang="ts">
import type { CollectionJob } from "../api";
import { useCollectionWorkspace } from "../workspace";

const workspace = useCollectionWorkspace();
const {
  overview,
  jobs,
  actionBusy,
  selectedJob,
  jobDetailBusy,
  pause,
  resume,
  stop,
  openJob,
  closeJob,
} = workspace;

const labels: Record<CollectionJob["status"], string> = {
  queued: "等待启动",
  discovering: "发现车系",
  collecting: "采集评论",
  paused: "已暂停",
  completed: "已完成",
  stopped: "已停止",
  partial_failed: "部分失败",
};

function displayStatus(job: CollectionJob) {
  if (job.control_requested === "pause") return "正在暂停";
  if (job.control_requested === "stop") return "正在停止";
  return labels[job.status];
}

function dateTime(value: string | null) {
  return value
    ? new Date(value).toLocaleString("zh-CN", { hour12: false })
    : "—";
}
</script>

<template>
  <section class="collection-jobs">
    <div class="collection-summary-line">
      <span
        >任务总数 <strong class="mono">{{ jobs.total }}</strong></span
      >
      <span
        >车系
        <strong class="mono">{{ overview?.series_count ?? 0 }}</strong></span
      >
      <span
        >评论
        <strong class="mono">{{ overview?.review_count ?? 0 }}</strong></span
      >
      <span>来源 <strong>汽车之家</strong></span>
    </div>

    <section
      v-if="overview?.active_job"
      class="active-job"
      aria-labelledby="job-progress-title"
    >
      <header>
        <div>
          <p class="collection-eyebrow">活动任务</p>
          <h2 id="job-progress-title">
            {{
              overview.active_job.mode === "verification"
                ? "功能验证"
                : "正式采集"
            }}
          </h2>
        </div>
        <div class="button-group">
          <button
            v-if="
              ['discovering', 'collecting'].includes(overview.active_job.status)
            "
            class="btn secondary"
            :disabled="
              actionBusy || Boolean(overview.active_job.control_requested)
            "
            @click="pause(overview.active_job.id)"
          >
            暂停
          </button>
          <button
            v-if="overview.active_job.status === 'paused'"
            class="btn secondary"
            :disabled="actionBusy"
            @click="resume(overview.active_job.id)"
          >
            继续
          </button>
          <button
            class="btn secondary"
            :disabled="
              actionBusy || Boolean(overview.active_job.control_requested)
            "
            @click="stop(overview.active_job.id)"
          >
            停止
          </button>
        </div>
      </header>
      <dl class="active-job__facts">
        <div>
          <dt>车系进度</dt>
          <dd>
            {{ overview.active_job.current_series_index + 1 }} /
            {{
              overview.active_job.discovered_count ||
              overview.active_job.max_series
            }}
          </dd>
        </div>
        <div>
          <dt>当前车系</dt>
          <dd>
            {{ overview.active_job.current_series_name || "等待发现" }}
            <span v-if="overview.active_job.current_series_id" class="mono"
              >({{ overview.active_job.current_series_id }})</span
            >
          </dd>
        </div>
        <div>
          <dt>当前页</dt>
          <dd class="mono">{{ overview.active_job.current_page }}</dd>
        </div>
        <div>
          <dt>已保存</dt>
          <dd class="mono">{{ overview.active_job.saved_count }}</dd>
        </div>
        <div>
          <dt>最后更新</dt>
          <dd>{{ dateTime(overview.active_job.updated_at) }}</dd>
        </div>
        <div>
          <dt>状态</dt>
          <dd>{{ displayStatus(overview.active_job) }}</dd>
        </div>
      </dl>
      <p v-if="overview.active_job.last_error" class="collection-job-error">
        {{ overview.active_job.last_error }}
      </p>
    </section>

    <section class="collection-ledger" aria-labelledby="job-ledger-title">
      <header><h2 id="job-ledger-title">最近任务</h2></header>
      <div v-if="jobs.rows.length" class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>创建时间</th>
              <th>模式</th>
              <th>状态</th>
              <th class="numeric">车系</th>
              <th class="numeric">已保存</th>
              <th class="numeric">失败</th>
              <th><span class="visually-hidden">操作</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in jobs.rows" :key="item.id">
              <td>{{ dateTime(item.created_at) }}</td>
              <td>
                {{ item.mode === "verification" ? "功能验证" : "正式采集" }}
              </td>
              <td>{{ displayStatus(item) }}</td>
              <td class="numeric mono">{{ item.discovered_count }}</td>
              <td class="numeric mono">{{ item.saved_count }}</td>
              <td class="numeric mono">{{ item.failed_count }}</td>
              <td>
                <button
                  class="text-button"
                  :disabled="jobDetailBusy"
                  @click="openJob(item.id)"
                >
                  查看事件
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="collection-empty-inline">尚无采集任务。</div>
    </section>

    <section
      v-if="selectedJob"
      class="collection-event-detail"
      aria-labelledby="job-event-title"
    >
      <header>
        <div>
          <p class="collection-eyebrow">任务记录</p>
          <h2 id="job-event-title">事件与异常</h2>
          <p class="mono">{{ selectedJob.id }}</p>
        </div>
        <button class="text-button" @click="closeJob">关闭</button>
      </header>
      <ol v-if="selectedJob.events.length" class="collection-event-list">
        <li v-for="event in selectedJob.events" :key="event.id">
          <div>
            <strong>{{ event.message }}</strong>
            <span class="mono">{{ event.event_type }}</span>
          </div>
          <p>
            {{ dateTime(event.created_at) }}
            <span v-if="event.series_id" class="mono"
              >· series_id {{ event.series_id }}</span
            >
          </p>
        </li>
      </ol>
      <p v-else class="collection-empty-inline">该任务没有事件记录。</p>
    </section>
  </section>
</template>
