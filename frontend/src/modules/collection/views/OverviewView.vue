<script setup lang="ts">
import { useCollectionWorkspace } from "../workspace";

const workspace = useCollectionWorkspace();
const { overview, navigate } = workspace;
</script>

<template>
  <section v-if="overview" class="collection-overview" aria-label="采集总览">
    <div class="collection-summary-line">
      <span
        >已发现车系
        <strong class="mono">{{ overview.series_count }}</strong></span
      >
      <span
        >已保存评论
        <strong class="mono">{{ overview.review_count }}</strong></span
      >
      <span
        >异常记录
        <strong class="mono">{{ overview.pending_errors }}</strong></span
      >
      <span>数据源 <strong>汽车之家新能源汽车口碑</strong></span>
    </div>

    <section
      v-if="overview.active_job"
      class="active-job"
      aria-labelledby="active-job-title"
    >
      <header>
        <div>
          <p class="collection-eyebrow">当前活动任务</p>
          <h2 id="active-job-title">
            {{
              overview.active_job.mode === "verification"
                ? "功能验证"
                : "正式采集"
            }}
          </h2>
        </div>
        <button class="text-button" @click="navigate('jobs')">
          查看与控制任务
        </button>
      </header>
      <dl class="active-job__facts">
        <div>
          <dt>进度</dt>
          <dd>
            第 {{ overview.active_job.current_series_index + 1 }} /
            {{ overview.active_job.discovered_count }} 个车系
          </dd>
        </div>
        <div>
          <dt>当前车系</dt>
          <dd>
            {{ overview.active_job.current_series_name || "等待开始" }}
            <span v-if="overview.active_job.current_series_id" class="mono"
              >({{ overview.active_job.current_series_id }})</span
            >
          </dd>
        </div>
        <div>
          <dt>页码</dt>
          <dd class="mono">{{ overview.active_job.current_page }}</dd>
        </div>
        <div>
          <dt>已保存</dt>
          <dd class="mono">{{ overview.active_job.saved_count }}</dd>
        </div>
        <div>
          <dt>状态</dt>
          <dd>
            {{
              overview.active_job.control_requested === "pause"
                ? "正在暂停"
                : overview.active_job.control_requested === "stop"
                  ? "正在停止"
                  : overview.active_job.status
            }}
          </dd>
        </div>
      </dl>
    </section>

    <div v-else class="collection-empty-state">
      <h2>当前没有运行中的采集任务</h2>
      <p>
        可先运行最多 3 个车系、每车系 2 页的功能验证，再决定是否开始正式采集。
      </p>
      <button class="btn primary" @click="workspace.openCreate">
        新建采集任务
      </button>
    </div>
  </section>
</template>
