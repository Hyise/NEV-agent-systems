<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { Search, X } from "lucide-vue-next";
import type { CatalogRunStatus, CatalogSeriesRow } from "../api";
import type { CatalogFlow } from "../catalogFlow";

const props = defineProps<{
  flow: CatalogFlow;
  collectionConflict: boolean;
}>();

const {
  isOpen,
  step,
  catalogStatus,
  discoveryRun,
  catalog,
  query,
  page,
  selectedSeriesIds,
  mode,
  busy,
  actionBusy,
  error,
  productionConfirmPending,
  productionConfirmationText,
  removedSelectionCount,
  removedSeriesIds,
} = props.flow;
const dialog = ref<HTMLDialogElement>();
const restoreFocus = ref<HTMLElement | null>(null);
const nonTerminal = new Set<CatalogRunStatus>([
  "queued",
  "discovering",
  "publishing",
  "cancelling",
]);

const activeRun = computed(
  () => discoveryRun.value ?? catalogStatus.value?.active_run ?? null,
);
const externalConflict = computed(
  () =>
    props.collectionConflict ||
    Boolean(activeRun.value && nonTerminal.has(activeRun.value.status)),
);
const runStatusText = computed(() => {
  switch (activeRun.value?.status) {
    case "queued":
    case "discovering":
    case "publishing":
      return "正在生成新目录";
    case "cancelling":
      return "正在取消发现";
    case "completed":
      return "车系发现已完成";
    case "completed_short":
      return "车系发现已完成，数据源不足 1000 个";
    case "cancelled":
      return "车系发现已取消";
    case "failed":
      return "车系发现失败";
    default:
      return "";
  }
});
const selectionInvalid = computed(
  () =>
    selectedSeriesIds.value.length === 0 ||
    (mode.value === "verification" && selectedSeriesIds.value.length > 3),
);
const lastPage = computed(() =>
  Math.max(1, Math.ceil(catalog.value.total / catalog.value.page_size)),
);

function dateTime(value: string | null | undefined) {
  return value
    ? new Date(value).toLocaleString("zh-CN", { hour12: false })
    : "尚未发布";
}

function reviewAvailable(item: CatalogSeriesRow) {
  return item.review_url.startsWith("https://");
}

async function previousPage() {
  if (page.value <= 1) return;
  page.value -= 1;
  await props.flow.loadCatalog();
}

async function nextPage() {
  if (page.value >= lastPage.value) return;
  page.value += 1;
  await props.flow.loadCatalog();
}

function closeDialog() {
  props.flow.close();
}

watch(isOpen, async (open) => {
  if (open) {
    restoreFocus.value = document.activeElement as HTMLElement;
    await nextTick();
    dialog.value?.showModal();
    return;
  }
  dialog.value?.close();
  await nextTick();
  restoreFocus.value?.focus();
  restoreFocus.value = null;
});
</script>

<template>
  <dialog
    ref="dialog"
    class="project-dialog catalog-dialog"
    aria-labelledby="create-collection-job-title"
    @cancel.prevent="closeDialog"
  >
    <div class="dialog-heading catalog-dialog__heading">
      <div>
        <p class="collection-eyebrow">汽车之家新能源口碑</p>
        <h2 id="create-collection-job-title">新建评论采集任务</h2>
      </div>
      <button
        class="icon-btn"
        type="button"
        aria-label="关闭新建任务"
        :disabled="actionBusy"
        @click="closeDialog"
      >
        <X :size="20" />
      </button>
    </div>

    <ol class="catalog-steps" aria-label="任务创建步骤">
      <li :class="{ current: step === 'discovery' }">
        <span class="mono">01</span>
        <strong>发现车系</strong>
      </li>
      <li :class="{ current: step === 'selection' }">
        <span class="mono">02</span>
        <strong>选择并采集</strong>
      </li>
    </ol>

    <div v-if="error" class="notice error" role="alert">{{ error }}</div>

    <section
      v-if="step === 'discovery'"
      class="catalog-discovery"
      aria-labelledby="catalog-discovery-title"
    >
      <header class="catalog-section-heading">
        <div>
          <h3 id="catalog-discovery-title">发现车系</h3>
          <p>先建立可重复使用的车系目录，再选择本次需要采集的对象。</p>
        </div>
        <strong class="catalog-count mono"
          >{{ catalogStatus?.series_count ?? 0 }} / 1000</strong
        >
      </header>

      <dl class="catalog-meta">
        <div>
          <dt>当前目录</dt>
          <dd>{{ catalogStatus?.active_batch_id ? "可用" : "尚未建立" }}</dd>
        </div>
        <div>
          <dt>最近发布</dt>
          <dd>{{ dateTime(catalogStatus?.published_at) }}</dd>
        </div>
        <div>
          <dt>发现结果</dt>
          <dd>
            {{
              catalogStatus?.source_exhausted ? "数据源已耗尽" : "目标 1000 个"
            }}
          </dd>
        </div>
      </dl>

      <div v-if="activeRun" class="catalog-progress" role="status">
        <div class="catalog-progress__title">
          <strong>{{ runStatusText }}</strong>
          <span v-if="nonTerminal.has(activeRun.status)"
            >旧目录在新目录发布前仍可查看</span
          >
        </div>
        <dl>
          <div>
            <dt>当前页</dt>
            <dd class="mono">{{ activeRun.current_page }}</dd>
          </div>
          <div>
            <dt>已扫描</dt>
            <dd class="mono">{{ activeRun.scanned_count }}</dd>
          </div>
          <div>
            <dt>唯一车系</dt>
            <dd class="mono">{{ activeRun.unique_count }}</dd>
          </div>
          <div>
            <dt>已跳过</dt>
            <dd class="mono">{{ activeRun.skipped_count }}</dd>
          </div>
        </dl>
        <p v-if="activeRun.error_message" class="form-error">
          {{ activeRun.error_message }}
        </p>
      </div>

      <p v-if="collectionConflict" class="notice info" role="status">
        评论采集任务正在使用汽车之家数据源，结束或暂停后才能重新发现车系。
      </p>

      <div class="catalog-dialog__actions">
        <button
          v-if="activeRun && nonTerminal.has(activeRun.status)"
          class="btn secondary"
          type="button"
          :disabled="actionBusy || activeRun.status === 'cancelling'"
          @click="flow.cancelDiscovery"
        >
          取消发现
        </button>
        <button
          v-else
          class="btn secondary"
          type="button"
          :disabled="actionBusy || collectionConflict"
          @click="flow.startDiscovery"
        >
          {{ catalogStatus?.active_batch_id ? "重新发现" : "开始发现" }}
        </button>
        <button
          class="btn primary"
          type="button"
          :disabled="busy || !(catalogStatus?.series_count ?? 0)"
          @click="flow.goToSelection"
        >
          选择车系并采集
        </button>
      </div>
    </section>

    <section
      v-else
      class="catalog-selection"
      aria-labelledby="catalog-selection-title"
    >
      <header class="catalog-section-heading">
        <div>
          <button class="text-button" type="button" @click="step = 'discovery'">
            ← 返回目录状态
          </button>
          <h3 id="catalog-selection-title">选择车系并采集</h3>
        </div>
        <strong class="catalog-selection-count mono"
          >已选 {{ selectedSeriesIds.length }}</strong
        >
      </header>

      <p v-if="removedSelectionCount" class="notice info" role="alert">
        目录已更新，已移除 {{ removedSelectionCount }} 个失效车系：
        <span class="mono">{{ removedSeriesIds.join("、") }}</span>
      </p>

      <form class="catalog-search" role="search" @submit.prevent="flow.search">
        <label for="catalog-query">搜索车系名称或 series_id</label>
        <div>
          <input
            id="catalog-query"
            v-model="query"
            type="search"
            autocomplete="off"
            placeholder="例如：汉 或 526"
          />
          <button class="btn secondary" type="submit" :disabled="busy">
            <Search :size="16" />搜索
          </button>
        </div>
      </form>

      <div class="catalog-selection-tools">
        <div class="button-group">
          <button
            class="text-button"
            type="button"
            :disabled="actionBusy || catalog.total === 0"
            @click="flow.selectFiltered"
          >
            全选当前筛选结果
          </button>
          <button
            class="text-button"
            type="button"
            :disabled="selectedSeriesIds.length === 0"
            @click="flow.clearSelection"
          >
            清空已选
          </button>
        </div>
        <span>共 {{ catalog.total }} 个匹配车系</span>
      </div>

      <div class="catalog-series-list" :aria-busy="busy">
        <label
          v-for="item in catalog.rows"
          :key="`${item.batch_id}-${item.series_id}`"
          class="catalog-series-row"
          :class="{ unavailable: !reviewAvailable(item) }"
        >
          <input
            type="checkbox"
            :checked="selectedSeriesIds.includes(item.series_id)"
            :disabled="!reviewAvailable(item)"
            @change="flow.toggleSeries(item.series_id)"
          />
          <span class="catalog-series-row__identity">
            <strong>{{ item.series_name }}</strong>
            <small class="mono">series_id {{ item.series_id }}</small>
          </span>
          <span class="catalog-series-row__rank mono"
            >#{{ item.discovery_rank }}</span
          >
          <span class="catalog-series-row__source">
            {{ reviewAvailable(item) ? "口碑入口可用" : "口碑入口不可用" }}
          </span>
        </label>
        <p
          v-if="!busy && catalog.rows.length === 0"
          class="collection-empty-inline"
        >
          当前条件没有匹配车系，请更换名称或 ID。
        </p>
      </div>

      <div class="catalog-pagination" aria-label="车系目录分页">
        <button
          class="text-button"
          type="button"
          :disabled="busy || page <= 1"
          @click="previousPage"
        >
          上一页
        </button>
        <span class="mono">第 {{ page }} / {{ lastPage }} 页</span>
        <button
          class="text-button"
          type="button"
          :disabled="busy || page >= lastPage"
          @click="nextPage"
        >
          下一页
        </button>
      </div>

      <fieldset class="catalog-mode-options">
        <legend>采集模式</legend>
        <label :class="{ selected: mode === 'verification' }">
          <input
            v-model="mode"
            type="radio"
            name="catalog-mode"
            value="verification"
            @change="productionConfirmPending = false"
          />
          <span
            ><strong>功能验证</strong
            ><small>选择 1～3 个车系，每车系最多 2 页</small></span
          >
        </label>
        <label :class="{ selected: mode === 'production' }">
          <input
            v-model="mode"
            type="radio"
            name="catalog-mode"
            value="production"
            @change="productionConfirmPending = false"
          />
          <span
            ><strong>正式采集</strong
            ><small>选择 1～1000 个车系，每车系采集全部评论</small></span
          >
        </label>
      </fieldset>

      <div class="catalog-submit-summary">
        <p>
          本次选择 <strong>{{ selectedSeriesIds.length }}</strong> 个车系；
          {{ mode === "verification" ? "每车系最多 2 页" : "每车系不限页数" }}。
        </p>
        <p>分页间隔 2～4 秒，车系间隔 5～10 秒。</p>
      </div>
      <p v-if="externalConflict" class="notice info" role="status">
        汽车之家数据源正被其他任务使用，当前不能创建采集任务。
      </p>
      <p v-if="productionConfirmPending" class="notice info" role="status">
        {{ productionConfirmationText }} 请再次确认开始。
      </p>

      <div class="catalog-dialog__actions">
        <button class="btn secondary" type="button" @click="closeDialog">
          取消
        </button>
        <button
          class="btn primary"
          type="button"
          :disabled="actionBusy || selectionInvalid || externalConflict"
          @click="flow.createJob"
        >
          {{
            actionBusy
              ? "正在创建…"
              : productionConfirmPending
                ? "确认并开始正式采集"
                : "创建采集任务"
          }}
        </button>
      </div>
    </section>
  </dialog>
</template>
