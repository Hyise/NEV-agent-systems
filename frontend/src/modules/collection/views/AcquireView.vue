<script setup lang="ts">
import { computed } from "vue";
import type { AcquisitionAction } from "../acquisitionGuidance";
import type { CatalogFlow } from "../catalogFlow";
import type { CollectionJob } from "../api";
import { useCollectionWorkspace } from "../workspace";

const props = defineProps<{ catalogFlow: CatalogFlow }>();
const emit = defineEmits<{ manage: [] }>();
const workspace = useCollectionWorkspace();
const { overview } = workspace;

const activeJob = computed(() => workspace.overview.value?.active_job ?? null);
const historicalJobs = computed(() =>
  workspace.jobs.value.rows.filter((job) => job.id !== activeJob.value?.id),
);

const statusLabel: Record<CollectionJob["status"], string> = {
  queued: "等待采集",
  discovering: "发现车系",
  collecting: "采集评论",
  paused: "已暂停",
  completed: "已完成",
  stopped: "已停止",
  partial_failed: "部分失败",
};

function dateTime(value: string | null) {
  return value
    ? new Date(value).toLocaleString("zh-CN", { hour12: false })
    : "—";
}

function suggestedAction(action: AcquisitionAction) {
  if (action === "manage") {
    emit("manage");
  } else if (action === "resume" && activeJob.value) {
    void workspace.resume(activeJob.value.id);
  } else if (action === "monitor") {
    document.querySelector<HTMLElement>("#current-collection-job")?.focus();
  } else {
    void props.catalogFlow.open();
  }
}

defineExpose({ suggestedAction });
</script>

<template>
  <section class="acquire-workspace" aria-label="获取评论数据">
    <div class="collection-summary-line">
      <span
        >车系目录
        <strong class="mono">{{ overview?.series_count ?? 0 }}</strong></span
      >
      <span
        >已保存评论
        <strong class="mono">{{ overview?.review_count ?? 0 }}</strong></span
      >
      <span
        >异常记录
        <strong class="mono">{{ overview?.pending_errors ?? 0 }}</strong></span
      >
      <span>来源 <strong>汽车之家新能源汽车口碑</strong></span>
    </div>

    <section
      v-if="activeJob"
      id="current-collection-job"
      class="active-job"
      tabindex="-1"
      aria-labelledby="current-job-title"
    >
      <header>
        <div>
          <p class="collection-eyebrow">当前采集任务</p>
          <h2 id="current-job-title">
            {{ activeJob.mode === "verification" ? "功能验证" : "正式采集" }}
          </h2>
        </div>
        <div class="button-group">
          <button
            v-if="['discovering', 'collecting'].includes(activeJob.status)"
            class="btn secondary"
            :disabled="
              workspace.actionBusy.value || Boolean(activeJob.control_requested)
            "
            @click="workspace.pause(activeJob.id)"
          >
            暂停
          </button>
          <button
            v-if="activeJob.status === 'paused'"
            class="btn primary"
            :disabled="workspace.actionBusy.value"
            @click="workspace.resume(activeJob.id)"
          >
            继续
          </button>
          <button
            class="btn secondary"
            :disabled="
              workspace.actionBusy.value || Boolean(activeJob.control_requested)
            "
            @click="workspace.stop(activeJob.id)"
          >
            停止
          </button>
        </div>
      </header>
      <dl class="active-job__facts">
        <div>
          <dt>当前车系</dt>
          <dd>{{ activeJob.current_series_name || "等待开始" }}</dd>
        </div>
        <div>
          <dt>当前页码</dt>
          <dd class="mono">{{ activeJob.current_page }}</dd>
        </div>
        <div>
          <dt>已保存</dt>
          <dd class="mono">{{ activeJob.saved_count }}</dd>
        </div>
        <div>
          <dt>重复跳过</dt>
          <dd class="mono">{{ activeJob.duplicate_count }}</dd>
        </div>
        <div>
          <dt>人工删除跳过</dt>
          <dd class="mono">{{ activeJob.deleted_review_skip_count ?? 0 }}</dd>
        </div>
        <div>
          <dt>状态</dt>
          <dd>{{ statusLabel[activeJob.status] }}</dd>
        </div>
      </dl>
      <p v-if="activeJob.last_error" class="collection-job-error">
        {{ activeJob.last_error }}
      </p>
    </section>

    <section v-else class="acquire-start" aria-labelledby="acquire-start-title">
      <div>
        <p class="collection-eyebrow">采集准备</p>
        <h2 id="acquire-start-title">发现车系并建立采集任务</h2>
        <p>
          先刷新车系目录，再筛选并选择车系。功能验证最多选择 3 个车系、每车系 2
          页。
        </p>
      </div>
      <button class="btn secondary" type="button" @click="catalogFlow.open()">
        打开车系发现与选择
      </button>
    </section>

    <details class="collection-history">
      <summary>历史采集任务（{{ historicalJobs.length }}）</summary>
      <div v-if="historicalJobs.length" class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>创建时间</th>
              <th>模式</th>
              <th>状态</th>
              <th>保存</th>
              <th>失败</th>
              <th>记录</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="job in historicalJobs" :key="job.id">
              <td>{{ dateTime(job.created_at) }}</td>
              <td>
                {{ job.mode === "verification" ? "功能验证" : "正式采集" }}
              </td>
              <td>{{ statusLabel[job.status] }}</td>
              <td class="mono">{{ job.saved_count }}</td>
              <td class="mono">{{ job.failed_count }}</td>
              <td>
                <button class="text-button" @click="workspace.openJob(job.id)">
                  查看事件
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="collection-empty-inline">尚无历史任务。</p>
    </details>

    <section
      v-if="workspace.selectedJob.value"
      class="collection-event-detail"
      aria-labelledby="job-events-title"
    >
      <header>
        <div>
          <p class="collection-eyebrow">任务记录</p>
          <h2 id="job-events-title">事件与异常</h2>
        </div>
        <button class="text-button" @click="workspace.closeJob">关闭</button>
      </header>
      <ol
        v-if="workspace.selectedJob.value.events.length"
        class="collection-event-list"
      >
        <li v-for="event in workspace.selectedJob.value.events" :key="event.id">
          <strong>{{ event.message }}</strong>
          <p>{{ dateTime(event.created_at) }}</p>
        </li>
      </ol>
      <p v-else class="collection-empty-inline">该任务没有事件记录。</p>
    </section>
  </section>
</template>
