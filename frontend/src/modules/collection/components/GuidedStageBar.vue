<script setup lang="ts">
import { computed } from "vue";
import {
  resolveAcquisitionGuidance,
  type AcquisitionAction,
} from "../acquisitionGuidance";
import type { CatalogStatus, CollectionOverview } from "../api";
import type { CollectionPage } from "../workspace";

const props = defineProps<{
  current: CollectionPage;
  overview: CollectionOverview | null;
  catalog: CatalogStatus | null;
}>();

const emit = defineEmits<{
  navigate: [page: CollectionPage];
  action: [action: AcquisitionAction];
}>();

const guidance = computed(() =>
  resolveAcquisitionGuidance(props.overview, props.catalog),
);
const stages: Array<{ id: CollectionPage; number: string; label: string }> = [
  { id: "acquire", number: "01", label: "获取数据" },
  { id: "assets", number: "02", label: "管理数据" },
  { id: "research", number: "03", label: "用于研究" },
];

const actionLabel: Record<AcquisitionAction, string> = {
  discover: "发现车系",
  collect: "选择车系",
  resume: "继续采集",
  monitor: "查看任务",
  manage: "管理评论",
};

function stageDetail(stage: CollectionPage) {
  if (stage === "acquire") {
    return `${props.catalog?.series_count ?? 0} 个车系`;
  }
  if (stage === "assets") {
    return `${props.overview?.review_count ?? 0} 条原始评论`;
  }
  return "确认研究范围";
}
</script>

<template>
  <section class="guided-stage" aria-label="评论数据研究流程">
    <ol class="guided-stage__rail">
      <li v-for="stage in stages" :key="stage.id">
        <button
          type="button"
          :class="{ current: current === stage.id }"
          :aria-current="current === stage.id ? 'step' : undefined"
          @click="emit('navigate', stage.id)"
        >
          <span class="mono">{{ stage.number }}</span>
          <strong>{{ stage.label }}</strong>
          <small class="guided-stage__status">{{
            stageDetail(stage.id)
          }}</small>
        </button>
      </li>
    </ol>
    <div v-if="current === 'acquire'" class="guided-stage__next">
      <div>
        <span>建议下一步</span>
        <strong>{{ guidance.title }}</strong>
        <p>{{ guidance.description }}</p>
      </div>
      <button
        type="button"
        class="btn primary"
        @click="emit('action', guidance.action)"
      >
        {{ actionLabel[guidance.action] }}
      </button>
    </div>
  </section>
</template>
